"""Kamuya açık metni veri olarak ayrıştırır, ham metni veya hesap kimliğini taşımaz."""
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from nexora.olcum import sayi, zaman

from .providers import MAX_AGE, SOCIAL_SOURCES

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ADDRESS = re.compile(r"(?<!\w)[" + BASE58 + r"]{32,44}(?!\w)")
METRICS = ("likes", "reposts", "replies", "views")


def identifier(value):
    return value if isinstance(value, str) and 0 < len(value) <= 256 and value.strip() else None


def digest(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode("ascii")).hexdigest()


def author_key(source, author):
    return digest("author", source, author)


def flag(value):
    return value if type(value) is bool else None


def valid_address(value):
    if not isinstance(value, str) or ADDRESS.fullmatch(value) is None:
        return False
    number = 0
    for char in value:
        number = number * 58 + BASE58.index(char)
    leading_zeroes = len(value) - len(value.lstrip("1"))
    return leading_zeroes + (number.bit_length() + 7) // 8 == 32 and number != 0


def evidence_ref(source, reference):
    return f"fixture://{source}/{digest(source, reference)}"


def _source_url(source, source_id, raw):
    if source == "x" and re.fullmatch(r"[0-9]{1,22}", source_id):
        return f"https://x.com/i/status/{source_id}"
    if source == "telegram" and isinstance(raw, str):
        try:
            url = urlsplit(raw)
        except ValueError:
            return None
        if url.scheme == "https" and url.netloc == "t.me":
            match = re.fullmatch(r"/([A-Za-z][A-Za-z0-9_]{4,31})/([0-9]{1,22})", url.path)
            if match and match[1].lower() not in {"joinchat", "proxy", "share", "socks"} and match[2] == source_id:
                return "https://t.me" + url.path
    return None


@dataclass(frozen=True)
class Event:
    event_id: str
    source: str
    source_id: str
    source_url: str | None
    author_id: str
    published_at: float
    observed_at: float
    text_hash: str | None
    mint_candidates: tuple[str, ...]
    metrics: dict
    fetched_at: float
    provenance: str
    paid: bool | None
    misleading: bool | None
    impersonation: bool | None
    claimed_role: str | None
    author_group: str | None


def normalize(source, row, as_of):
    if source == "telegram" and row.get("authorized") is not True:
        return None, "KANAL_IZNI_UNKNOWN"
    source_id, author = identifier(row.get("source_id")), identifier(row.get("author_id"))
    channel = identifier(row.get("channel_id")) if source == "telegram" else None
    if not source_id or not author or (source == "telegram" and channel is None):
        return None, "KIMLIK_EKSIK"
    source_key = (channel, source_id) if channel else source_id
    published, observed, fetched = (zaman(row.get(k)) for k in ("published_at", "observed_at", "fetched_at"))
    if None in (published, observed, fetched) or not published <= fetched <= observed <= as_of:
        return None, "GECERSIZ_ZAMAN"
    if observed - published > MAX_AGE:
        return None, "ESKI_PAYLASIM"
    text = row.get("text")
    text = text if isinstance(text, str) and len(text) <= 16_384 else ""
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    mints = {x for x in ADDRESS.findall(text) if valid_address(x)}
    explicit = row.get("token_mint")
    if explicit is not None:
        if valid_address(explicit):
            mints.add(explicit)
        else:
            mints.clear()
    metrics = row.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    metrics = {key: v for key in METRICS if (v := sayi(metrics.get(key))) is not None and 0 <= v <= 1e15}
    role = row.get("claimed_role")
    group = identifier(row.get("author_group"))
    event_id = digest("event", source, source_key)
    public = source != "telegram" or row.get("public") is True
    url = _source_url(source, source_id, row.get("source_url")) if public else None
    return Event(
        event_id, source, digest("source", source, source_key), url,
        author_key(source, author), published, observed, digest("text", normalized) if normalized else None,
        tuple(sorted(mints)), metrics, fetched, evidence_ref(source, source_key),
        flag(row.get("paid")), flag(row.get("misleading")), flag(row.get("impersonation")),
        role if role in ("none", "project", "influencer") else None, digest("group", group) if group else None,
    ), None


def events_at(batches, as_of):
    candidates = {}
    rejected = {}
    for source in SOCIAL_SOURCES:
        for row in batches[source].items:
            if source == "token_profile" and row.get("kind") != "event":
                continue
            event, error = normalize(source, row, as_of)
            if error:
                rejected[error] = rejected.get(error, 0) + 1
                continue
            old = candidates.get(event.event_id)
            if old is None or event.observed_at < old[0].observed_at:
                candidates[event.event_id] = (event, False)
            elif event.observed_at == old[0].observed_at and event != old[0]:
                candidates[event.event_id] = (old[0], True)
    events = []
    for event, conflict in candidates.values():
        if conflict:
            rejected["CELISKILI_OLAY"] = rejected.get("CELISKILI_OLAY", 0) + 1
        else:
            events.append(event)
    return sorted(events, key=lambda e: (e.observed_at, e.event_id)), rejected

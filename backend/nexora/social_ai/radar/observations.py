"""Sağlayıcı kayıtlarını ham metni saklamadan kaynak gözlemlerine çevirir."""
import re
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urlsplit

from nexora.olcum import zaman

from ..events import ADDRESS, BASE58, Event, digest, evidence_ref, normalize, valid_address

_POST_ID = re.compile(r"[0-9]{1,19}")
_CHAT_ID = re.compile(r"-[0-9]{1,19}")
_HANDLE = re.compile(r"[A-Za-z0-9_]{1,32}")
_TYPED_ADDRESS = r"\s*[:=]\s*`?([" + BASE58 + r"]{32,44})(?!\w)"
_MINT_LABEL = r"(?<!\w)(?i:token mint|mint|ca)"
_MINT_FIELD = re.compile(_MINT_LABEL + _TYPED_ADDRESS)
_MINT_MARKER = re.compile(_MINT_LABEL + r"\s*[:=]")
_WALLET_FIELD = re.compile(r"(?<!\w)(?i:wallet|cüzdan)" + _TYPED_ADDRESS)


def obj(value):
    return value if isinstance(value, dict) else {}


def post_id(value):
    return value if isinstance(value, str) and _POST_ID.fullmatch(value) and int(value) else None


def chat_id(value):
    value = str(value) if type(value) is int else value
    return value if isinstance(value, str) and _CHAT_ID.fullmatch(value) else None


def handle_matches(value, expected):
    return isinstance(value, str) and _HANDLE.fullmatch(value) and value.casefold() == expected[1:].casefold()


def api_time(value):
    if isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return zaman(date.timestamp()) if date.tzinfo is not None else None
        except (ValueError, OverflowError, OSError):
            return None
    return zaman(value)


def origin_key(platform, post, channel=None):
    post = post_id(str(post) if type(post) is int else post)
    channel = chat_id(channel) if platform == "telegram" else None
    if post and (platform == "x" or platform == "telegram" and channel):
        return digest("radar-post", platform, channel, post)
    return None


def x_post_link(value):
    if not isinstance(value, str) or len(value) > 512:
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme == "https" and url.netloc.lower() in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        match = re.fullmatch(r"/(?:i/web|[A-Za-z0-9_]{1,32})/status/([0-9]{1,19})/?", url.path)
        if match:
            return origin_key("x", match[1])
    return None


def telegram_links(message):
    """Bot API entity konumları UTF-16 kod birimi cinsindendir."""
    for field, entity_field in (("text", "entities"), ("caption", "caption_entities")):
        value, entities = message.get(field), message.get(entity_field)
        if not isinstance(value, str) or len(value) > 16_384 or not isinstance(entities, list):
            continue
        encoded = value.encode("utf-16-le", errors="surrogatepass")
        for entry in entities[:100]:
            entry = obj(entry)
            if entry.get("type") == "text_link":
                yield entry.get("url")
            elif entry.get("type") == "url":
                start, length = entry.get("offset"), entry.get("length")
                if type(start) is int and type(length) is int and start >= 0 and 0 < length <= 512:
                    yield encoded[start * 2:(start + length) * 2].decode("utf-16-le", errors="replace")


@dataclass(frozen=True)
class Observation:
    source_id: str
    fingerprint: str
    origins: tuple[str, ...]
    relay: bool
    event: Event
    origin_published_at: float | None = None
    wallet_claims: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


def observation(source, row, as_of, *, identity, controller, origins=(), relay=False,
                origin_published_at=None, fixture=False):
    platform = source.platform
    key = origin_key(platform, row.get("source_id"), row.get("channel_id"))
    if key is None:
        return None, "KIMLIK_EKSIK"
    # Only catalog/authorization metadata can assign a controller. Neither text nor a post field can do so.
    flags = dict(impersonation=False, claimed_role="none", author_group=controller if not relay else None)
    if fixture:
        for name in ("paid", "misleading"):
            flags[name] = row.get(name)
    text = row.get("text")
    text = text if isinstance(text, str) and len(text) <= 16_384 else ""
    wallets = tuple(sorted({digest("radar-wallet", x) for x in _WALLET_FIELD.findall(text) if valid_address(x)}))
    explicit = _MINT_FIELD.findall(text)
    markers = _MINT_MARKER.findall(text)
    if markers:
        candidates = explicit if len(markers) == len(explicit) and all(map(valid_address, explicit)) else ()
    else:
        candidates = ADDRESS.findall(_WALLET_FIELD.sub("", text))
    event, error = normalize(platform, {**row, **flags, "author_id": identity}, as_of, max_age=None,
                             public_links=not fixture, address_candidates=candidates)
    if error:
        return None, error
    if origin_published_at is not None and origin_published_at > event.published_at:
        return None, "GECERSIZ_ZAMAN"
    return Observation(source.source_id, key, origins, relay, event, origin_published_at, wallets), None


def native_telegram(source, post, fetched_at, observed_at, *, identity, controller, fixture=False):
    post = obj(post)
    chat = obj(post.get("chat"))
    if chat_id(chat.get("id")) != identity or chat.get("type") != "channel" or not handle_matches(
        chat.get("username"), source.handle
    ):
        return None, "HESAP_KIMLIGI_UYUSMUYOR"
    sender = obj(post.get("sender_chat"))
    if sender and chat_id(sender.get("id")) != identity:
        return None, "HESAP_KIMLIGI_UYUSMUYOR"
    origins = set()
    forward = obj(post.get("forward_origin"))
    if forward.get("type") == "channel":
        origin = origin_key("telegram", forward.get("message_id"), obj(forward.get("chat")).get("id"))
        if origin:
            origins.add(origin)
    if source.category == "kol_relay":
        links = {link for url in telegram_links(post) if (link := x_post_link(url))}
        if len(links) == 1:
            origins.update(links)
    message_id = post.get("message_id")
    row = dict(source_id=str(message_id) if type(message_id) is int else message_id, channel_id=identity,
               published_at=post.get("date"), observed_at=observed_at, fetched_at=fetched_at,
               text=post.get("text", post.get("caption")), authorized=True, public=False,
               paid=post.get("is_paid_post") if not fixture else post.get("paid"),
               misleading=post.get("misleading") if fixture else None)
    return observation(source, row, observed_at, identity=identity, controller=controller,
                       origins=tuple(sorted(origins)), relay=bool(forward) or source.category == "kol_relay",
                       origin_published_at=zaman(forward.get("date")), fixture=fixture)


def native_x(source, post, fetched_at, observed_at, *, identity, controller, fixture=False):
    post = obj(post)
    if post_id(post.get("author_id")) != identity:
        return None, "HESAP_KIMLIGI_UYUSMUYOR"
    references = post.get("referenced_posts", post.get("referenced_tweets", []))
    if not isinstance(references, list) or not all(isinstance(ref, dict) for ref in references):
        return None, "GECERSIZ_PAYLASIM"
    reposts = [ref for ref in references if ref.get("type") in ("retweeted", "reposted", "quoted")]
    origin = None
    if reposts:
        if len(reposts) != 1 or (origin := origin_key("x", reposts[0].get("id"))) is None:
            return None, "GECERSIZ_PAYLASIM"
    # X edits share the original id. A retry or later edit cannot become a second original.
    edits = post.get("edit_history_post_ids", post.get("edit_history_tweet_ids", []))
    if not isinstance(edits, list) or any(post_id(item) is None for item in edits):
        return None, "GECERSIZ_PAYLASIM"
    public = obj(post.get("public_metrics"))
    metrics = {key: public.get(field) for key, field in (
        ("likes", "like_count"), ("reposts", "repost_count"), ("replies", "reply_count"), ("views", "impression_count")
    )}
    if metrics["reposts"] is None:
        metrics["reposts"] = public.get("retweet_count")
    text = post.get("text")
    relay = bool(reposts) or (isinstance(text, str) and text.startswith("RT @"))
    row = dict(source_id=post.get("id"), published_at=api_time(post.get("created_at")),
               observed_at=observed_at, fetched_at=fetched_at, text=text, metrics=metrics,
               paid=post.get("paid") if fixture else post.get("paid_partnership"),
               misleading=post.get("misleading") if fixture else None)
    item, error = observation(source, row, observed_at, identity=identity, controller=controller,
                              origins=(origin,) if origin else (), relay=relay, fixture=fixture)
    if item and edits:
        keys = tuple(dict.fromkeys(origin_key("x", pid) for pid in (*edits, post["id"])))
        item = replace(item, fingerprint=keys[0], aliases=keys[1:])
    return item, error


def fixture_ref(item):
    return evidence_ref(item.event.source, item.fingerprint)

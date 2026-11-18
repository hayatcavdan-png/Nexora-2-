"""Salt okunur Android Sosyal Radar görünümü.

Dış sosyal ağlara, Helius'a veya üretim veritabanına dokunmaz.
Yalnızca operatör tarafından açıkça tanımlanmış bir snapshot dosyasını okur.
Sentetik, geçersiz, eski veya doğrulanmamış veri canlı gibi sunulmaz.
HTTP rol doğrulaması server.py H._izin içinde uygulanır.
"""
import json
import time
from .sources import CATALOG, LIVE, OK, SourceBatch
from ..events import valid_address

MAX_SNAPSHOT_BYTES = 2_000_000
MAX_SNAPSHOT_AGE_SECONDS = 900
ALLOWED_CLASSES = frozenset({
    "SOSYAL_ERKEN_UYARI", "GOLGE_IZLE", "RISK_VETOSU_ADAYI", "BELIRSIZ"
})


def _empty(now, status):
    return dict(
        schema_version=1, read_only=True, live_enabled=False,
        snapshot_status=status,
        sources=[dict(SourceBatch().describe(source, now),
                      access_status="ERISIM_YOK", live_verified=False)
                 for source in CATALOG.values()],
        alerts=[]
    )


def _read_snapshot(path):
    with open(path, "rb") as handle:
        data = handle.read(MAX_SNAPSHOT_BYTES + 1)
    if len(data) > MAX_SNAPSHOT_BYTES:
        return None
    parsed = json.loads(data)
    return parsed if isinstance(parsed, dict) else None


def _verified_source(raw, expected):
    return (isinstance(raw, dict)
            and raw.get("source_id") == expected
            and raw.get("live_verified") is True
            and raw.get("access_mode") == LIVE
            and raw.get("status") == OK
            and raw.get("trust_status") == "verified"
            and raw.get("enabled") is True)


def dashboard(snapshot_path="", *, now=None):
    """En fazla 20 yeni olayı içeren, yalnızca kanıt alanlarını dönen API cevabı."""
    now = float(now if now is not None else time.time())
    if not snapshot_path:
        return _empty(now, "BAGLANTI_BEKLENIYOR")
    try:
        raw = _read_snapshot(snapshot_path)
    except (OSError, ValueError, UnicodeError):
        return _empty(now, "SNAPSHOT_OKUNAMADI")
    if raw is None or raw.get("schema_version") != 1:
        return _empty(now, "SNAPSHOT_GECERSIZ")
    if raw.get("mod") != "GOZLEM" or raw.get("read_only") is not True:
        return _empty(now, "CANLI_KANIT_YOK")
    as_of = raw.get("as_of")
    if (not isinstance(as_of, (int, float)) or isinstance(as_of, bool)
            or not 0 <= now - as_of <= MAX_SNAPSHOT_AGE_SECONDS):
        return _empty(now, "SNAPSHOT_ESKI")
    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, list):
        return _empty(now, "SNAPSHOT_GECERSIZ")
    by_id = {source.get("source_id"): source for source in raw_sources
             if isinstance(source, dict) and isinstance(source.get("source_id"), str)}
    sources, verified = [], set()
    for source_id, source in CATALOG.items():
        row = by_id.get(source_id)
        good = _verified_source(row, source_id)
        if good:
            verified.add(source_id)
        sources.append(dict(
            source_id=source_id, platform=source.platform, handle=source.handle,
            url=source.url, category=source.category,
            status="OK" if good else "UNKNOWN",
            access_status="LIVE_AUTHORIZED" if good else "ERISIM_YOK",
            live_verified=good,
            last_seen=row.get("last_seen") if good else None,
            lag_seconds=row.get("lag_seconds") if good else None,
        ))
    events = raw.get("olaylar", [])
    if not isinstance(events, list):
        events = []
    alerts = []
    for result in events:
        if not isinstance(result, dict):
            continue
        event, decision = result.get("olay"), result.get("karar")
        if not isinstance(event, dict) or not isinstance(decision, dict):
            continue
        source_id, mint = event.get("first_source"), event.get("token_mint")
        observed, verdict = event.get("observed_at"), decision.get("sinif")
        if (source_id not in verified
                or event.get("mint_status") != "VERIFIED"
                or verdict not in ALLOWED_CLASSES
                or result.get("timely") is not True
                or not isinstance(observed, (int, float)) or isinstance(observed, bool)
                or not 0 <= now - observed <= MAX_SNAPSHOT_AGE_SECONDS
                or not valid_address(mint)):
            continue
        why = decision.get("gerekce")
        alerts.append(dict(
            source_id=source_id, token_mint=mint, mint=mint,
            classification=verdict, observed_at=observed,
            reason_codes=why[:10] if isinstance(why, list) else []
        ))
        if len(alerts) >= 20:
            break
    return dict(
        schema_version=1, read_only=True, live_enabled=bool(verified),
        snapshot_status="GOZLEM" if verified else "ERISIM_DOGRULANMADI",
        sources=sources, alerts=alerts
    )

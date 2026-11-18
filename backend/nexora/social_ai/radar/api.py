"""Salt okunur Android Sosyal Radar görünümü.

Dış sosyal ağlara, Helius'a veya üretim veritabanına dokunmaz.
Yalnızca operatör tarafından açıkça tanımlanmış bir snapshot dosyasını okur.
Sentetik, geçersiz, eski veya doğrulanmamış veri canlı gibi sunulmaz.
HTTP rol doğrulaması server.py H._izin içinde uygulanır.
"""
import json
import os
import stat
import time

from nexora.olcum import sayi

from ..events import valid_address
from ..shadow import HORIZONS
from .sources import CATALOG, DELAYED, LIVE, NO_ACCESS, OK, QUOTA, UNKNOWN

MAX_SNAPSHOT_BYTES = 2_000_000
MAX_SNAPSHOT_AGE_SECONDS = 900
MAX_ALERT_AGE_SECONDS = 24 * 60 * 60
ALLOWED_CLASSES = frozenset({
    "SOSYAL_ERKEN_UYARI", "GOLGE_IZLE", "RISK_VETOSU_ADAYI", "BELIRSIZ"
})
REASON_CODES = frozenset({
    "UCRETLI_GORUNURLUK", "YANILTICI_PAYLASIM", "SAHTE_HESAP", "SAHTE_PROJE_HESABI",
    "SAHTE_INFLUENCER", "HESAP_TEYIDI_UNKNOWN", "METIN_UNKNOWN", "TEKRAR_EDEN_METIN",
    "BOT_BENZERI_KOORDINASYON", "TOPLULUK_BAGIMSIZLIGI_UNKNOWN", "SOSYAL_SAGLAYICI_UNKNOWN",
    "MINT_YETKILERI_UNKNOWN", "MINT_YETKISI", "MINT_YETKISI_UNKNOWN", "FREEZE_YETKISI",
    "FREEZE_YETKISI_UNKNOWN", "TOKEN_2022_RISKI", "TOKEN_2022_UNKNOWN", "JUPITER_LIKIDITE_UNKNOWN",
    "DEX_LIKIDITE_UNKNOWN", "JUPITER_YETERSIZ_LIKIDITE", "DEX_YETERSIZ_LIKIDITE",
    "ILISKILI_CUZDAN", "ZINCIR_TEYIDI", "ZINCIR_TEYIDI_UNKNOWN", "BAGIMSIZ_SOSYAL_VE_ZINCIR_TEYIDI",
    "TEYIT_ESIGI_ALTINDA", "ORIJINAL_HESAP_TEYIDI_UNKNOWN", "CUZDAN_IDDIASI_UNKNOWN",
})
OUTCOME_REASONS = frozenset({
    "MINT_VEYA_TEKLIF_UNKNOWN", "GIRIS_TEKLIFI_UNKNOWN", "CIKIS_YOLU_YOK",
    "CIKIS_TEKLIFI_UNKNOWN", "TEKLIF_TUTARSIZ",
})


def _source_row(source, status=NO_ACCESS, *, verified=False, seen=None, lag=None):
    return dict(
        source_id=source.source_id, platform=source.platform, handle=source.handle,
        url=source.url, category=source.category, status=status,
        access_status=LIVE if verified else NO_ACCESS, live_verified=verified,
        last_seen=seen, lag_seconds=lag,
    )


def _empty(status):
    return dict(
        schema_version=1, read_only=True, live_enabled=False, snapshot_status=status,
        sources=[_source_row(source) for source in CATALOG.values()], alerts=[],
    )


def _read_snapshot(path):
    def open_regular(name, flags):
        fd = os.open(name, flags | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Snapshot normal dosya olmalı.")
        except (OSError, ValueError):
            os.close(fd)
            raise
        return fd

    with open(path, "rb", opener=open_regular) as handle:
        data = handle.read(MAX_SNAPSHOT_BYTES + 1)
    if len(data) > MAX_SNAPSHOT_BYTES:
        return None
    parsed = json.loads(data)
    return parsed if isinstance(parsed, dict) else None


def _verified_source(raw, as_of, now):
    checked = raw.get("last_checked")
    return (raw.get("live_verified") is True
            and raw.get("access_mode") == LIVE
            and raw.get("status") == OK
            and raw.get("trust_status") == "verified"
            and raw.get("enabled") is True
            and _recent(checked, now) and checked <= as_of)


def _recent(value, now):
    return type(value) in (int, float) and now - MAX_SNAPSHOT_AGE_SECONDS <= value <= now


def _number(value):
    return sayi(value) if type(value) in (int, float) else None


def _shadow_results(result, observed, as_of):
    raw = result.get("golge_sonuclari")
    rows = raw if isinstance(raw, dict) else {}
    outcomes = {}
    for minutes in HORIZONS:
        key = f"{minutes}dk"
        due = observed + minutes * 60
        row = rows.get(key)
        status, reason, net, pct = UNKNOWN, "OLCUM_YOK", None, None
        if as_of < due:
            status, reason = "PENDING", "UFUK_BEKLIYOR"
        elif isinstance(row, dict) and row.get("vade") == due:
            value, percent = _number(row.get("net_usdc")), _number(row.get("getiri_pct"))
            code = row.get("gerekce")
            if row.get("durum") == OK and value is not None and percent is not None:
                status, reason, net, pct = OK, "MALIYET_DAHIL_TEKLIF", value, percent
            elif row.get("durum") == UNKNOWN and isinstance(code, str) and code in OUTCOME_REASONS:
                reason = code
        outcomes[key] = dict(status=status, reason_code=reason, due_at=due,
                             net_usdc=net, return_pct=pct)
    return outcomes


def dashboard(snapshot_path="", *, now=None, live_enabled=False):
    """En fazla 20 yeni olayı içeren, yalnızca kanıt alanlarını dönen API cevabı."""
    now = float(now if now is not None else time.time())
    if not snapshot_path:
        return _empty("BAGLANTI_BEKLENIYOR")
    if live_enabled is not True:
        return _empty("CANLI_IZLEME_KAPALI")
    try:
        raw = _read_snapshot(snapshot_path)
    except (OSError, ValueError, RecursionError):
        return _empty("SNAPSHOT_OKUNAMADI")
    if raw is None or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        return _empty("SNAPSHOT_GECERSIZ")
    if raw.get("mod") != "GOZLEM" or raw.get("read_only") is not True:
        return _empty("CANLI_KANIT_YOK")
    as_of = raw.get("as_of")
    if not _recent(as_of, now):
        return _empty("SNAPSHOT_ESKI")
    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, list):
        return _empty("SNAPSHOT_GECERSIZ")
    by_id = {}
    for row in raw_sources:
        source_id = row.get("source_id") if isinstance(row, dict) else None
        if isinstance(source_id, str) and source_id in CATALOG:
            by_id[source_id] = {} if source_id in by_id else row
    sources, verified = [], set()
    for source_id, source in CATALOG.items():
        row = by_id.get(source_id, {})
        good = _verified_source(row, as_of, now)
        if good:
            verified.add(source_id)
        seen = _number(row.get("last_seen")) if good else None
        lag = _number(row.get("lag_seconds")) if good else None
        status = row.get("status", UNKNOWN)
        sources.append(_source_row(
            source, OK if good else status if status in (DELAYED, NO_ACCESS, QUOTA) else UNKNOWN,
            verified=good, seen=seen if seen is not None and 0 < seen <= as_of else None,
            lag=lag if lag is not None and lag >= 0 else None,
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
        if (not isinstance(source_id, str) or source_id not in verified
                or event.get("mint_status") != "VERIFIED"
                or not isinstance(verdict, str) or verdict not in ALLOWED_CLASSES
                or result.get("timely") is not True
                or type(observed) not in (int, float) or not now - MAX_ALERT_AGE_SECONDS <= observed <= as_of
                or not valid_address(mint)):
            continue
        why = decision.get("gerekce")
        alerts.append(dict(
            source_id=source_id, token_mint=mint, mint=mint, mint_status="VERIFIED",
            classification=verdict, observed_at=observed,
            reason_codes=[code for code in why[:10] if isinstance(code, str)
                          and code in REASON_CODES] if isinstance(why, list) else [],
            shadow_results=_shadow_results(result, observed, as_of),
        ))
    alerts.sort(key=lambda alert: alert["observed_at"], reverse=True)
    return dict(
        schema_version=1, read_only=True, live_enabled=bool(verified),
        snapshot_status="GOZLEM" if verified else "ERISIM_DOGRULANMADI",
        sources=sources, alerts=alerts[:20],
    )

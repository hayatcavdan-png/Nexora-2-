"""Pilot kaynak kataloğu ve sağlayıcı sonuç sözleşmesi."""
from dataclasses import dataclass

from ..providers import MAX_AGE

OK = "OK"
NO_ACCESS = "ERISIM_YOK"
DELAYED = "VERI_GECIKTI"
QUOTA = "KOTA"
UNKNOWN = "UNKNOWN"
MOCK = "MOCK"
UNAVAILABLE = "UNAVAILABLE"
LIVE = "LIVE_AUTHORIZED"


@dataclass(frozen=True)
class Source:
    source_id: str
    platform: str
    handle: str
    url: str
    category: str
    consent_scope: str
    enabled: bool = False
    rate_budget: int = 48


_TELEGRAM_SCOPE = "ONAYLI_KANAL_YONETICISI_VE_BOT_VEYA_IZINLI_EXPORT"
_X_SCOPE = "RESMI_X_API_V2_PUBLIC_READ"

CATALOG = {
    source.source_id: source for source in (
        Source("solana_early_trending", "telegram", "@solearlytrending", "https://t.me/solearlytrending",
               "trend_discovery", _TELEGRAM_SCOPE),
        Source("kolscope", "telegram", "@KOLscope", "https://t.me/KOLscope", "kol_relay", _TELEGRAM_SCOPE),
        Source("ansem", "x", "@blknoiz06", "https://x.com/blknoiz06", "influencer", _X_SCOPE),
        Source("lookonchain", "x", "@lookonchain", "https://x.com/lookonchain", "chain_reporting", _X_SCOPE),
        Source("bubblemaps", "x", "@bubblemaps", "https://x.com/bubblemaps", "wallet_risk", _X_SCOPE),
    )
}


@dataclass(frozen=True)
class SourceBatch:
    status: str = UNKNOWN
    access_mode: str = UNAVAILABLE
    trust_status: str = "unverified"
    items: tuple = ()
    last_checked: float | None = None
    failure_count: int = 0
    requests_used: int = 0
    retry_at: float | None = None
    cost_microusd: int = 0
    rejected: tuple[str, ...] = ()
    enabled: bool = False
    coverage_from: float | None = None
    coverage_until: float | None = None
    live_verified: bool = False
    last_seen: float | None = None
    lag_seconds: float | None = None

    def describe(self, source, as_of):
        last = max((item for item in self.items if item.event.observed_at <= as_of),
                   key=lambda item: (item.event.observed_at, item.event.event_id), default=None)
        seen = self.last_seen if self.last_seen is not None and self.last_seen <= as_of else None
        lag = self.lag_seconds if seen is not None else None
        if last:
            seen = last.event.observed_at
            lag = seen - (last.origin_published_at or last.event.published_at)
        delayed_check = self.last_checked is not None and as_of - self.last_checked > MAX_AGE
        status = DELAYED if self.status == OK and (delayed_check or (lag is not None and lag > MAX_AGE)) else self.status
        return dict(
            source_id=source.source_id, platform=source.platform, handle=source.handle, url=source.url,
            category=source.category, enabled=self.enabled, trust_status=self.trust_status,
            access_mode=self.access_mode, consent_scope=source.consent_scope, status=status,
            live_verified=self.live_verified, last_checked=self.last_checked, coverage_from=self.coverage_from,
            coverage_until=self.coverage_until, last_seen=seen, lag_seconds=lag, failure_count=self.failure_count,
            rate_budget=source.rate_budget, requests_used=self.requests_used, retry_at=self.retry_at,
            estimated_cost_usd=self.cost_microusd / 1_000_000
            if self.access_mode == LIVE or self.requests_used else None,
        )

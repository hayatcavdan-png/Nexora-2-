"""Sağlayıcı sınırı. V1 yükleyicisi yalnızca bellek içindeki fixture'ları okur."""
from dataclasses import dataclass
from typing import Protocol

from nexora.olcum import zaman

SOCIAL_SOURCES = ("x", "telegram", "token_profile")
SOURCES = (*SOCIAL_SOURCES, "helius", "jupiter", "dex", "quotes", "n16")
MAX_AGE = 900


@dataclass(frozen=True)
class Batch:
    status: str = "UNKNOWN"
    items: tuple[dict, ...] = ()


class Provider(Protocol):
    def read(self, source: str) -> Batch:
        """Sağlayıcının normalize edilmiş durumunu ve fixture kayıtlarını döndürür."""


class FixtureProvider:
    def __init__(self, data: dict):
        self.data = data

    def read(self, source: str) -> Batch:
        raw = self.data.get(source)
        if not isinstance(raw, dict):
            return Batch()
        status = raw.get("status")
        if status == "RATE_LIMITED":
            return Batch("RATE_LIMITED")
        items = raw.get("items")
        if status != "OK" or not isinstance(items, list) or not all(isinstance(r, dict) for r in items):
            return Batch()
        return Batch("OK", tuple(items))


def known_times(row, at, *, earliest, field, strict=True):
    occurred, fetched = zaman(row.get(field)), zaman(row.get("fetched_at"))
    if occurred is None or fetched is None or not earliest <= occurred <= fetched <= at:
        return None
    return (occurred, fetched) if not strict or fetched < at else None


def snapshot(batch, mint, t0):
    """Son geçerli zamanlı ölçüm. Aynı zamanda çelişen ölçümler bilinmeyen kalır."""
    candidates = {}
    for row in batch.items:
        if row.get("mint") == mint:
            clocks = known_times(row, t0, earliest=t0 - MAX_AGE, field="measured_at")
            if clocks:
                candidates.setdefault(clocks, []).append(row)
    rows = candidates[max(candidates)] if candidates else []
    return rows[0] if rows and all(row == rows[0] for row in rows) else None

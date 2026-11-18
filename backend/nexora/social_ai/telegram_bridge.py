"""Termux Telegram bridge contract: local, metadata-only and fail closed.

Never open a Telegram session, messages, network, API credentials or an AI model.
Inputs can ONLY be the local T10 status summary; output is constrained to the
two channel IDs, harmless counters and three worker-alive booleans.

This is not a token detector and is never Social Radar LIVE_AUTHORIZED proof.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import stat

CHANNELS = {
    "solana_early_trending": "@solearlytrending",
    "kolscope": "@KOLscope",
}
MAX_JSON_BYTES = 100_000
MAX_AGE_SECONDS = 90


class BridgeUnavailable(ValueError):
    """No valid current metadata; do not report Telegram channels as live."""


def _stamp(value):
    if not isinstance(value, str):
        raise BridgeUnavailable("timestamp not string")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise BridgeUnavailable("timestamp malformed") from exc
    if stamp.tzinfo is None:
        raise BridgeUnavailable("timestamp missing zone")
    return stamp.timestamp()


def _count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise BridgeUnavailable("invalid metadata count")
    return value


def from_t10(data, *, now=None, worker_status=None):
    """Strictly sanitize the local T10 JSON, discarding all unknown fields.

    Worker checker maps the three known session IDs to booleans. It must be
    supplied by the *local* server, not by an arbitrary JSON field.
    """
    if now is None:
        now = datetime.now(timezone.utc).timestamp()
    if type(now) not in (float, int) or not math.isfinite(now):
        raise BridgeUnavailable("invalid current time")
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise BridgeUnavailable("invalid schema")
    if data.get("mode") != "LOCAL_METADATA_ONLY" or data.get("social_ai_transfer") is not False:
        raise BridgeUnavailable("metadata-only requirement failed")
    updated = data.get("updated_at")
    age = now - _stamp(updated)
    if not -5 <= age <= MAX_AGE_SECONDS:
        raise BridgeUnavailable("stale status")
    sources = data.get("source_status")
    if not isinstance(sources, list) or len(sources) != 2:
        raise BridgeUnavailable("expected two metadata sources")

    clean, seen = [], set()
    for item in sources:
        if not isinstance(item, dict):
            raise BridgeUnavailable("invalid source record")
        source_id = item.get("source_id")
        if source_id not in CHANNELS or source_id in seen:
            raise BridgeUnavailable("invalid or repeated source")
        handle = item.get("handle")
        if not isinstance(handle, str) or handle.lower() != CHANNELS[source_id].lower():
            raise BridgeUnavailable("source handle mismatch")
        if item.get("platform") != "telegram" or item.get("bridge_status") != "LOCAL_METADATA_ONLY":
            raise BridgeUnavailable("invalid source state")
        if item.get("social_ai_transfer") is not False:
            raise BridgeUnavailable("content transfer unexpectedly enabled")
        if item.get("live_verified") not in (None, False):
            raise BridgeUnavailable("incorrect live verification")
        seen.add(source_id)
        clean.append({
            "source_id": source_id,
            "platform": "telegram",
            "handle": CHANNELS[source_id],
            "metadata_count": _count(item.get("metadata_count")),
            "live_verified": False,
            "social_ai_transfer": False,
        })
    clean.sort(key=lambda row: row["source_id"])
    worker_status = worker_status if isinstance(worker_status, dict) else {}
    return {
        "schema_version": 1,
        "mode": "LOCAL_METADATA_ONLY",
        "updated_at": updated,
        "social_ai_transfer": False,
        "source_status": clean,
        "listener_running": worker_status.get("nexora_tg_bridge") is True,
        "updater_running": worker_status.get("nexora_tg_status") is True,
        "sync_running": worker_status.get("nexora_tg_t10") is True,
    }


def read_t10(path, *, now=None, worker_status=None):
    """Regular file only; no symlink following when platform supports it."""
    import os
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BridgeUnavailable("not regular file")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            raw = handle.read(MAX_JSON_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if len(raw) > MAX_JSON_BYTES:
        raise BridgeUnavailable("metadata too large")
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise BridgeUnavailable("metadata invalid JSON") from exc
    return from_t10(data, now=now, worker_status=worker_status)

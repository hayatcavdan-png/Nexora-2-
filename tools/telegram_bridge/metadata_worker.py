"""Reproducible, metadata-only T8 + T10 compatible worker.

Do NOT start alongside the phone's existing T8/T10 processes: both would
write the same local status files. Never opens Telegram messages.
"""
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import time

SOURCES = {
    "solana_early_trending": "@solearlytrending",
    "kolscope": "@KOLscope",
}
EVENT = re.compile(r"^YENI PAYLASIM \| (@[A-Za-z0-9_]+) \| ID: ([0-9]+) \| ([0-9]{2}:[0-9]{2}:[0-9]{2})$")
MAX_LOG_BYTES = 10_000_000


def summarize(log):
    """No message text or token CA is accepted from the log."""
    rows = {
        source_id: {"handle": handle, "count": 0, "last_id": None}
        for source_id, handle in SOURCES.items()
    }
    seen = set()
    for line in log.splitlines():
        m = EVENT.fullmatch(line.strip())
        if not m:
            continue
        handle, mid, hour = m.groups()
        for source_id, row in rows.items():
            if row["handle"].lower() != handle.lower() or len(mid) > 22:
                continue
            key = (source_id, mid)
            if key in seen:
                continue
            seen.add(key)
            row["count"] += 1
            row["last_id"] = mid
            row["last_local_time"] = hour
    return rows


def atomic_json(path, value):
    """Private atomic update of sanitized file; never write credentials."""
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    temp = path.with_name("." + path.name + ".tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def update(directory):
    log = directory / "t6_events.log"
    if not log.is_file() or log.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("T6 log missing or too large")
    event_rows = summarize(log.read_text(encoding="utf-8", errors="replace"))
    created = datetime.now(timezone.utc).isoformat()
    t7 = {
        "schema_version": 1,
        "mode": "METADATA_ONLY",
        "social_ai_transfer": False,
        "created_at": created,
        "sources": event_rows,
    }
    t10 = {
        "schema_version": 1,
        "mode": "LOCAL_METADATA_ONLY",
        "social_ai_transfer": False,
        "updated_at": created,
        "source_status": [{
            "source_id": source_id,
            "platform": "telegram",
            "handle": row["handle"],
            "metadata_count": row["count"],
            "last_local_time": row.get("last_local_time"),
            "bridge_status": "LOCAL_METADATA_ONLY",
            "live_verified": False,
            "social_ai_transfer": False,
        } for source_id, row in event_rows.items()]
    }
    atomic_json(directory / "t7_status.json", t7)
    atomic_json(directory / "t9_nexora_bridge.json", t10)
    return sum(row["count"] for row in event_rows.values())


def main():
    parser = argparse.ArgumentParser(description="T8/T10 metadata-only local worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dir", type=Path,
                        default=Path.home() / ".nexora_telegram_bridge")
    options = parser.parse_args()
    os.umask(0o077)
    if not options.dir.is_dir():
        raise SystemExit("Bridge directory missing: do not create a new Telegram session")
    while True:
        try:
            count = update(options.dir)
            print(f"METADATA ONLY | KAYNAK: 2 | BILDIRIM: {count}", flush=True)
        except (OSError, ValueError, TypeError):
            print("T8/T10: KAYNAK DOSYASI GECERSIZ", flush=True)
            if options.once:
                raise SystemExit(1)
        if options.once:
            return
        time.sleep(20)


if __name__ == "__main__":
    main()

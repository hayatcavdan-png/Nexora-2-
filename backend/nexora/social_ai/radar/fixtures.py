"""Kayıtlı X yanıtları ve açıkça onaylanmış yerel Telegram kanal dışa aktarımları."""
from dataclasses import replace

from nexora.olcum import zaman

from ..events import identifier
from .observations import chat_id, handle_matches, native_telegram, native_x, obj, post_id
from .sources import CATALOG, DELAYED, MOCK, NO_ACCESS, OK, QUOTA, UNKNOWN, SourceBatch


def recorded_source(source, record, as_of):
    """Manifestteki izin ve sabit kimlik, tekil paylaşımın içeriğinden bağımsızdır."""
    if not isinstance(record, dict):
        return SourceBatch()
    status = record.get("status")
    checked = zaman(record.get("last_checked"))
    checked = checked if checked is not None and checked <= as_of else None
    if record.get("authorized") is not True:
        return SourceBatch(NO_ACCESS, MOCK, "blocked", last_checked=checked, failure_count=1)
    if status not in (OK, DELAYED):
        status = status if status in (NO_ACCESS, QUOTA) else UNKNOWN
        return SourceBatch(status, MOCK, "blocked" if status == NO_ACCESS else "unverified",
                           last_checked=checked, failure_count=1)

    account = obj(record.get("account"))
    if source.platform == "telegram":
        identity = chat_id(account.get("id"))
        expected = chat_id(record.get("expected_account_id"))
        read_post = native_telegram
    else:
        identity = post_id(account.get("id"))
        expected = post_id(record.get("expected_account_id"))
        read_post = native_x
    if identity is None or identity != expected or not handle_matches(account.get("username"), source.handle):
        return SourceBatch(NO_ACCESS, MOCK, "blocked", last_checked=checked, failure_count=1,
                           rejected=("HESAP_KIMLIGI_UYUSMUYOR",))

    entries = record.get("items")
    if checked is None or not isinstance(entries, list):
        return SourceBatch(UNKNOWN, MOCK, "unverified", last_checked=checked, failure_count=1)
    start = zaman(record.get("coverage_from"))
    if start is not None and start > checked:
        start = None
    controller = identifier(record.get("controller"))
    # Unknown affiliation stays unknown, including for catalog sources without a reviewed controller.
    candidates, rejected = {}, []
    for entry in entries:
        entry = obj(entry)
        fetched, observed = zaman(entry.get("fetched_at")), zaman(entry.get("observed_at"))
        if fetched is None or observed is None or not fetched <= observed <= checked:
            rejected.append("GECERSIZ_ZAMAN")
            continue
        item, error = read_post(source, entry.get("post"), fetched, observed, identity=identity,
                                controller=controller, fixture=True)
        if error:
            rejected.append(error)
            continue
        key = item.event.event_id
        original, conflict = candidates.get(key, (None, False))
        if original is None or observed < original.event.observed_at:
            candidates[key] = (item, False)
        elif observed == original.event.observed_at:
            # Engagement counters can change in a cache replay without changing what was said.
            comparable = replace(item, event=replace(item.event, metrics=original.event.metrics))
            candidates[key] = (original, conflict or comparable != original)
    items = []
    for item, conflict in candidates.values():
        if conflict:
            rejected.append("CELISKILI_OLAY")
        else:
            items.append(item)
    if entries and not items:
        status = UNKNOWN
    return SourceBatch(status, MOCK, "verified", tuple(items), last_checked=checked, rejected=tuple(rejected),
                       coverage_from=start if status == OK else None,
                       coverage_until=checked if start is not None and status == OK else None)


class RecordedSources:
    def __init__(self, records, as_of):
        self.batches = {source_id: recorded_source(source, records.get(source_id), as_of)
                        for source_id, source in CATALOG.items()}

    def read(self, source_id):
        return self.batches[source_id]

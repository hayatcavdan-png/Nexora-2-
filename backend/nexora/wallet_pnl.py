"""İşlem listesi -> swap'lar -> FIFO. Salt okunur; veritabanı/emir yok."""
from nexora.swap_decoder import decode_swap
from nexora.wallet_fifo_adapter import behavior_to_fifo_events
from nexora.fifo_matcher import match_fifo

def _decode_with_meta(tx, wallet):
    rec = decode_swap(tx, wallet)
    if rec.get("event_type") not in ("BUY", "SELL"):
        return None
    sigs = (tx.get("transaction") or {}).get("signatures") or []
    if not sigs or not tx.get("blockTime"):
        return None
    rec["signature"] = sigs[0]
    rec["timestamp_ms"] = int(tx["blockTime"]) * 1000
    if isinstance(tx.get("slot"), int): rec["slot"] = tx["slot"]
    return rec

def compute_wallet_pnl(transactions, wallet):
    records = [r for r in (_decode_with_meta(t, wallet) for t in transactions) if r]
    conv = behavior_to_fifo_events({"wallet": wallet, "classifications": records})
    result = match_fifo(conv["events"], verified_only=False)   # veri 'partial' kalitesinde
    result.update(
        swaps_decoded=len(records), transactions_seen=len(transactions),
        adapter_skipped=conv["skipped"], data_quality="partial",
        copy_eligible=False,   # eksik/doğrulanmamış veriyle otomatik kopyalama yetkisi verilmez
    )
    return result

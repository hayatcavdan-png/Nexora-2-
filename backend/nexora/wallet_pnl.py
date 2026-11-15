"""İşlem listesi -> swap'lar -> FIFO. Salt okunur; veritabanı/emir yok."""
from nexora.swap_decoder import decode_swap
from nexora.wallet_fifo_adapter import behavior_to_fifo_events
from nexora.fifo_matcher import match_fifo

def compute_wallet_pnl(transactions, wallet):
    records = [r for r in (decode_swap(t, wallet) for t in transactions) if r]
    conv = behavior_to_fifo_events({"wallet": wallet, "classifications": records})
    result = match_fifo(conv["events"], verified_only=False)   # veri 'partial' kalitesinde
    result.update(
        swaps_decoded=len(records), transactions_seen=len(transactions),
        adapter_skipped=conv["skipped"], data_quality="partial",
        copy_eligible=False,   # eksik/doğrulanmamış veriyle otomatik kopyalama yetkisi verilmez
    )
    return result

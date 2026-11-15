"""Muhafazakâr swap çözücü (v0). Cüzdanın token bakiye değişimlerinden BUY/SELL çıkarır.
Yalnızca tek token <-> tek quote (USDC / WSOL / yerel SOL) takaslarını tanır; çok adımlı,
belirsiz ya da başarısız işlemler None döner. Gerçek işlem örnekleriyle doğrulanmalıdır."""
from collections import defaultdict
from nexora.constants import USDC_MINT, WSOL_MINT

def _addr(a): return a.get("pubkey") if isinstance(a, dict) else a

def _token_deltas(meta, wallet):
    pre, post, dec = defaultdict(int), defaultdict(int), {}
    for side, bucket in (("preTokenBalances", pre), ("postTokenBalances", post)):
        for b in meta.get(side) or []:
            if not isinstance(b, dict) or b.get("owner") != wallet: continue
            ui = b.get("uiTokenAmount") or {}
            amt = ui.get("amount")
            if not (isinstance(amt, str) and amt.isdigit()) or not isinstance(ui.get("decimals"), int): continue
            bucket[b["mint"]] += int(amt); dec[b["mint"]] = ui["decimals"]
    return {m: post[m] - pre[m] for m in set(pre) | set(post) if post[m] != pre[m]}, dec

def decode_swap(tx, wallet):
    if not isinstance(tx, dict) or not isinstance(wallet, str): return None
    meta = tx.get("meta") or {}
    if meta.get("err") is not None: return None
    msg = (tx.get("transaction") or {}).get("message") or {}
    keys = [_addr(k) for k in msg.get("accountKeys") or []]
    sigs = (tx.get("transaction") or {}).get("signatures") or []
    if not sigs or wallet not in keys: return None
    deltas, dec = _token_deltas(meta, wallet)

    sol = 0
    i = keys.index(wallet)
    pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
    if i < len(pre) and i < len(post):
        sol = post[i] - pre[i]
        fee = meta.get("fee")
        if keys[0] == wallet and isinstance(fee, int) and fee >= 0: sol += fee

    present = [m for m in (USDC_MINT, WSOL_MINT) if m in deltas]
    if len(present) > 1: return None                      # belirsiz quote
    others = [m for m in deltas if m not in (USDC_MINT, WSOL_MINT)]
    if len(others) != 1: return None                      # çok adımlı / token yok
    token = others[0]; tdelta = deltas[token]

    rec = {"signature": sigs[0], "token_mint": token, "token_decimals": dec[token],
           "token_delta_raw": tdelta, "slot": tx.get("slot")}
    if tx.get("blockTime"): rec["timestamp_ms"] = int(tx["blockTime"]) * 1000
    if present:
        q = present[0]; qdelta = deltas[q]
        rec["quote_mint"], rec["quote_delta_raw"] = q, qdelta
    else:
        qdelta = sol; rec["sol_delta_lamports"] = sol
    if tdelta > 0 and qdelta < 0: rec["event_type"] = "BUY"
    elif tdelta < 0 and qdelta > 0: rec["event_type"] = "SELL"
    else: return None
    if keys[0] == wallet and isinstance(meta.get("fee"), int) and meta["fee"] > 0:
        rec.update(fee_amount_raw=str(meta["fee"]), fee_mint=WSOL_MINT, fee_decimals=9,
                   fee_source="solana_transaction_meta_fee")
    return rec

import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from decimal import Decimal
from nexora.fifo_matcher import match_fifo
from nexora.amounts import raw_to_decimal
from nexora.swap_decoder import decode_swap
from nexora.wallet_pnl import compute_wallet_pnl
from nexora.constants import USDC_MINT

W, TOK = "WALLET1", "TOKMINT1"

def ev(sig, side, tok_raw, q_raw, ts, quality="verified"):
    return dict(wallet=W, signature=sig, event_index=0, token_mint=TOK, side=side, timestamp_ms=ts,
                token_amount_raw=str(tok_raw), token_decimals=6, quote_mint=USDC_MINT,
                quote_amount_raw=str(q_raw), quote_decimals=6, data_quality=quality)

def tx(sig, tok_pre, tok_post, usdc_pre, usdc_post, t=1000):
    def bal(mint, amt, dec): return dict(accountIndex=1, mint=mint, owner=W, uiTokenAmount=dict(amount=str(amt), decimals=dec))
    return dict(slot=5, blockTime=t, transaction=dict(signatures=[sig], message=dict(accountKeys=[W, "x"])),
        meta=dict(err=None, fee=5000, preBalances=[10**9, 0], postBalances=[10**9 - 5000, 0],
                  preTokenBalances=[bal(TOK, tok_pre, 6), bal(USDC_MINT, usdc_pre, 6)],
                  postTokenBalances=[bal(TOK, tok_post, 6), bal(USDC_MINT, usdc_post, 6)]))

class T(unittest.TestCase):
    def test_fifo_partial_sell(self):
        r = match_fifo([ev("b", "BUY", 100_000_000, 10_000_000, 1), ev("s", "SELL", 40_000_000, 8_000_000, 2)])
        self.assertEqual(Decimal(r["realized_pnl_by_quote"][USDC_MINT]), Decimal("4"))
        self.assertEqual(Decimal(r["open_positions"][0]["remaining_quantity"]), Decimal("60"))
    def test_fifo_unmatched_sell_and_order(self):
        r = match_fifo([ev("s", "SELL", 5_000_000, 1_000_000, 1)])
        self.assertEqual(len(r["unmatched_sells"]), 1); self.assertEqual(r["matches"], [])
    def test_verified_only_skips_partial(self):
        r = match_fifo([ev("b", "BUY", 1_000_000, 1_000_000, 1, "partial")])
        self.assertEqual(r["skipped_events"][0]["reason"], "data_quality_not_verified")
    def test_raw_to_decimal_strict(self):
        self.assertEqual(raw_to_decimal("1500000", 6), Decimal("1.5"))
        for bad in (0, -1, True, "1.5", "abc"):
            with self.assertRaises((ValueError, TypeError)): raw_to_decimal(bad, 6)
    def test_decoder_buy_sell_and_rejects(self):
        b = decode_swap(tx("b", 0, 100_000_000, 50_000_000, 40_000_000), W)
        self.assertEqual((b["event_type"], b["token_delta_raw"], b["quote_delta_raw"]), ("BUY", 100_000_000, -10_000_000))
        s = decode_swap(tx("s", 100_000_000, 60_000_000, 40_000_000, 48_000_000), W)
        self.assertEqual(s["event_type"], "SELL")
        failed = tx("f", 0, 1, 5, 4); failed["meta"]["err"] = {"x": 1}
        self.assertIsNone(decode_swap(failed, W))
        self.assertIsNone(decode_swap(tx("n", 5, 5, 5, 5), W))          # değişim yok
        self.assertIsNone(decode_swap(tx("w", 0, 10, 5, 6), W))         # token+ ve quote+ (swap değil)
    def test_pipeline_pnl(self):
        txs = [tx("b", 0, 100_000_000, 50_000_000, 40_000_000, 1000), tx("s", 100_000_000, 60_000_000, 40_000_000, 48_000_000, 2000)]
        r = compute_wallet_pnl(txs, W)
        self.assertEqual(r["swaps_decoded"], 2)
        self.assertEqual(Decimal(r["realized_pnl_by_quote"][USDC_MINT]) > 0, True)
        self.assertFalse(r["copy_eligible"]); self.assertEqual(r["data_quality"], "partial")

if __name__ == "__main__": unittest.main()

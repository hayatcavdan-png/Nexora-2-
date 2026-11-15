import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from nexora.swap_decoder import decode_swap
from nexora.constants import USDC_MINT, WSOL_MINT
from nexora.wallet_analysis import analyze

W, ATA, JUP, TOK = "WaLLet1111111111111111111111111111111", "AtaAcct111111111111111111111111111111", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "MEMEmint11111111111111111111111111111"
RENT, FEE, L = 2_039_280, 5000, 10**9

def bal(i, mint, amt, dec=6): return dict(accountIndex=i, mint=mint, owner=W, uiTokenAmount=dict(amount=str(amt), decimals=dec))

def tx(sig, t, pre_tok, post_tok, sol_pre, sol_post, ata_pre, ata_post, ins=(), quote=None, loaded=False, mint=TOK):
    """Yerel SOL (veya quote=USDC) ile swap. Token hesabı ATA (index 1, loaded=True ise adres tablosunda index 3)."""
    keys = [W, ATA, "Pool111111111111111111111111111111"] if not loaded else [W, "Pool111111111111111111111111111111", "Prog111111111111111111111111111111"]
    i = 1 if not loaded else 3
    pre_b, post_b = [sol_pre, ata_pre, 0], [sol_post, ata_post, 0]
    if loaded: pre_b, post_b = [sol_pre, 0, 0, ata_pre], [sol_post, 0, 0, ata_post]
    pre, post = ([bal(i, mint, pre_tok)] if pre_tok is not None else []), ([bal(i, mint, post_tok)] if post_tok is not None else [])
    if quote:
        pre.append(bal(4, quote, 100 * 10**6)); post.append(bal(4, quote, (100 - 10) * 10**6 if post_tok else 110 * 10**6))
    meta = dict(err=None, fee=FEE, logMessages=[f"Program {JUP} invoke [1]"], preBalances=pre_b, postBalances=post_b,
                preTokenBalances=pre, postTokenBalances=post,
                innerInstructions=[dict(index=0, instructions=[dict(parsed=p) for p in ins])])
    if loaded: meta["loadedAddresses"] = dict(writable=[ATA], readonly=[])
    return dict(slot=t, blockTime=t, meta=meta, transaction=dict(signatures=[sig], message=dict(
        accountKeys=keys, instructions=[dict(programId=JUP)])))

CREATE = dict(type="createIdempotent", info=dict(source=W, account=ATA, wallet=W, mint=TOK))
CLOSE = dict(type="closeAccount", info=dict(account=ATA, destination=W, owner=W))

class LifecycleTests(unittest.TestCase):
    def test_first_buy_with_account_creation_rent_removed(self):
        t = tx("b", 1000, None, 10**9, 10 * L, 10 * L - L - RENT - FEE, 0, RENT, ins=[CREATE])
        r = decode_swap(t, W)
        self.assertEqual(r["event_type"], "BUY"); self.assertEqual(r["sol_delta_lamports"], -L)   # kira hariç tam 1 SOL
        self.assertIn("token_account_lifecycle_verified", r["evidence"])
    def test_final_sell_with_account_close_refund_removed(self):
        t = tx("s", 2000, 10**9, None, 9 * L, 9 * L + 2 * L + RENT - FEE, RENT, 0, ins=[CLOSE])
        r = decode_swap(t, W)
        self.assertEqual(r["event_type"], "SELL"); self.assertEqual(r["sol_delta_lamports"], 2 * L)
    def test_rent_paid_by_someone_else_stays_unknown(self):
        other = dict(type="createIdempotent", info=dict(source="Baska11111111111111111111111111111", account=ATA))
        r = decode_swap(tx("b", 1000, None, 10**9, 10 * L, 9 * L - FEE, 0, RENT, ins=[other]), W)
        self.assertEqual(r["evidence"], ["token_account_created_or_closed"])
    def test_close_refund_to_someone_else_stays_unknown(self):
        bad = dict(type="closeAccount", info=dict(account=ATA, destination="Baska11111111111111111111111111111"))
        r = decode_swap(tx("s", 2000, 10**9, None, 9 * L, 11 * L - FEE, RENT, 0, ins=[bad]), W)
        self.assertEqual(r["event_type"], "UNKNOWN")
    def test_no_instruction_evidence_stays_unknown(self):
        self.assertEqual(decode_swap(tx("b", 1000, None, 10**9, 10 * L, 9 * L - RENT - FEE, 0, RENT), W)["event_type"], "UNKNOWN")
    def test_wsol_account_lifecycle_not_trusted(self):
        r = decode_swap(tx("b", 1000, None, 10**9, 10 * L, 9 * L - RENT - FEE, 0, RENT, ins=[CREATE], mint=WSOL_MINT), W)
        self.assertEqual(r["event_type"], "UNKNOWN")
    def test_usdc_quote_with_creation(self):
        t = tx("b", 1000, None, 10**9, 10 * L, 10 * L - RENT - FEE, 0, RENT, ins=[CREATE], quote=USDC_MINT)
        t["transaction"]["message"]["accountKeys"] += ["UsdcAcct11111111111111111111111111111"]
        t["meta"]["preBalances"].append(0); t["meta"]["postBalances"].append(0)
        r = decode_swap(t, W)
        self.assertEqual((r["event_type"], r["quote_mint"], r["quote_delta_raw"]), ("BUY", USDC_MINT, -10 * 10**6))
    def test_account_from_address_lookup_table(self):
        t = tx("b", 1000, None, 10**9, 10 * L, 9 * L - RENT - FEE, 0, RENT, ins=[CREATE], loaded=True)
        r = decode_swap(t, W)
        self.assertEqual((r["event_type"], r["sol_delta_lamports"]), ("BUY", -L))
    def test_analysis_matches_open_and_close_round_trip(self):
        buy = tx("b", 1000, None, 10**9, 10 * L, 9 * L - RENT - FEE, 0, RENT, ins=[CREATE])
        sell = tx("s", 5000, 10**9, None, 9 * L, 9 * L + 2 * L + RENT - FEE, RENT, 0, ins=[CLOSE])
        m = analyze([buy, sell], W, 100.0)
        self.assertEqual((m["swap"], m["kapanan"], m["eslesmeyen_satis"], m["hesap_ac_kapa"]), (2, 1, 0, 0))
        self.assertAlmostEqual(m["gerceklesen_usd"], 100.0, delta=0.01)        # +1 SOL, kira K/Z'yi bozmadı
if __name__ == "__main__": unittest.main()

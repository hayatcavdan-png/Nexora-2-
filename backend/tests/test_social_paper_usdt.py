"""Offline 100 USDT scenario: no network, DB, secrets, Telegram or orders."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from nexora.social_ai.paper_usdt import from_file, portfolio, simulate
from nexora.token_safety import TOKEN_PROGRAM, TOKEN_2022

MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"
T0 = 1_800_000_000


def fixture(*, mint=MINT, t0=T0):
    proof = dict(
        queried_mint=mint, measured_at=t0 - 7, fetched_at=t0 - 5,
        value=dict(owner=TOKEN_PROGRAM, data=dict(parsed=dict(
            type="mint", info=dict(isInitialized=True, decimals=6,
                                   mintAuthority=None, freezeAuthority=None)
        )))
    )
    buy = dict(
        mint=mint, side="buy", quote_asset="USDT", executable=True,
        input_usdt="4", token_qty="40000", network_fee_usdt="0.03",
        dex_fee_usdt="0.02", slippage_bps="80", price_impact_bps="60",
        measured_at=t0 - 4, fetched_at=t0 - 1,
    )
    sell = dict(
        mint=mint, side="sell", quote_asset="USDT", executable=True,
        output_usdt="4.50", token_qty="40000", network_fee_usdt="0.03",
        dex_fee_usdt="0.05", slippage_bps="80", price_impact_bps="50",
        measured_at=t0 + 305, fetched_at=t0 + 306,
    )
    return dict(
        source="manual_mint", event_id="test-1", mint=mint,
        observed_at=t0, account=proof,
        liquidity=dict(mint=mint, verified=True, total_usdt="50000",
                       measured_at=t0 - 10, fetched_at=t0 - 8),
        buy_quote=buy, sell_quotes={"5dk": sell},
    )


class SocialPaperUsdtTests(unittest.TestCase):
    def test_safe_fixture_and_matured_profit(self):
        out = simulate(fixture(), now=T0 + 310)
        self.assertEqual(out["status"], "PAPER_ELIGIBLE")
        self.assertEqual(out["mode"], "OFFLINE_PAPER_ONLY")
        self.assertEqual(out["entry"]["total_cost_usdt"], "4.082")
        self.assertEqual(out["entry"]["remaining_cash_usdt"], "95.918")
        self.assertEqual(out["horizons"]["5dk"], {"status": "OK", "net_usdt": "0.302000"})
        for horizon in (15, 30, 60):
            self.assertEqual(out["horizons"][f"{horizon}dk"]["status"], "PENDING")
        self.assertFalse(out["real_order"])
        self.assertFalse(out["social_ai_transfer"])

    def test_slippage_changes_cost_and_net(self):
        row = fixture()
        row["buy_quote"]["slippage_bps"] = "0"
        row["sell_quotes"]["5dk"]["slippage_bps"] = "0"
        no_slip = simulate(row, now=T0+310)
        self.assertEqual(no_slip["entry"]["total_cost_usdt"], "4.05")
        self.assertEqual(no_slip["horizons"]["5dk"]["net_usdt"], "0.370000")
        with_slip = simulate(fixture(), now=T0+310)
        self.assertLess(
            float(with_slip["horizons"]["5dk"]["net_usdt"]),
            float(no_slip["horizons"]["5dk"]["net_usdt"])
        )

    def test_horizon_future_and_delayed_quote_rejected(self):
        row = fixture()
        self.assertEqual(simulate(row, now=T0+100)["horizons"]["5dk"]["status"], "PENDING")
        late = copy.deepcopy(row)
        late["sell_quotes"]["5dk"]["measured_at"] = T0 + 500
        late["sell_quotes"]["5dk"]["fetched_at"] = T0 + 501
        self.assertEqual(simulate(late, now=T0+601)["horizons"]["5dk"]["status"], "UNKNOWN")
        leak = copy.deepcopy(row)
        leak["sell_quotes"]["5dk"]["fetched_at"] = T0 + 400
        self.assertEqual(simulate(leak, now=T0+350)["horizons"]["5dk"]["status"], "UNKNOWN")

    def test_pre_observation_proof_required(self):
        for field in ("account", "liquidity", "buy_quote"):
            with self.subTest(field=field):
                row = fixture()
                row[field]["fetched_at"] = T0 + 2
                out = simulate(row, now=T0+310)
                self.assertEqual(out["status"], "BLOCKED")

    def test_mint_safety_and_authority(self):
        row = fixture()
        row["account"]["value"]["data"]["parsed"]["info"]["mintAuthority"] = MINT
        self.assertEqual(simulate(row, now=T0+10)["reason"], "MINT_RISK_OR_UNKNOWN")
        row = fixture()
        row["account"]["value"]["owner"] = TOKEN_2022
        row["account"]["value"]["data"]["parsed"]["info"]["extensions"] = [
            {"extension": "transferHook"}]
        self.assertEqual(simulate(row, now=T0+10)["reason"], "MINT_RISK_OR_UNKNOWN")

    def test_account_mint_cross_binding_and_invalid_mint(self):
        row = fixture()
        row["account"]["queried_mint"] = "So11111111111111111111111111111111111111112"
        self.assertEqual(simulate(row, now=T0+10)["reason"], "MINT_PROOF_MISSING_OR_STALE")
        row = fixture()
        row["mint"] = "FAKE"
        self.assertEqual(simulate(row, now=T0+10)["reason"], "MINT_INVALID")

    def test_sources_fail_closed_no_telegram(self):
        for source in ("telegram", "telegram_metadata", "x", "", None):
            with self.subTest(source=source):
                row = fixture()
                row["source"] = source
                self.assertEqual(simulate(row, now=T0+1)["reason"], "SOURCE_NOT_AUTHORIZED")
        row = fixture()
        row["source"] = "licensed_feed"
        self.assertEqual(simulate(row, now=T0+1)["reason"], "SOURCE_PERMISSION_MISSING")
        row["permission_verified"] = True
        row["license_id"] = "fixture-license-not-live-proof"
        self.assertEqual(simulate(row, now=T0+1)["status"], "PAPER_ELIGIBLE")

    def test_liquidity_and_quote_errors(self):
        row = fixture()
        row["liquidity"]["verified"] = False
        self.assertEqual(simulate(row, now=T0+1)["status"], "BLOCKED")
        row = fixture()
        row["buy_quote"]["quote_asset"] = "USDC"
        self.assertEqual(simulate(row, now=T0+1)["reason"], "ENTRY_QUOTE_UNKNOWN")
        row = fixture()
        row["buy_quote"]["slippage_bps"] = "9999"
        self.assertEqual(simulate(row, now=T0+1)["reason"], "ENTRY_QUOTE_UNKNOWN")
        row = fixture()
        row["buy_quote"]["network_fee_usdt"] = -1
        self.assertEqual(simulate(row, now=T0+1)["reason"], "ENTRY_QUOTE_UNKNOWN")
        row = fixture()
        row["buy_quote"]["input_usdt"] = "5"
        self.assertEqual(simulate(row, now=T0+1)["reason"], "ENTRY_LIMIT_EXCEEDED")

    def test_single_pass_dedup_and_cash(self):
        a = fixture()
        b = copy.deepcopy(a)
        out = portfolio([a, b], now=T0+310)
        self.assertEqual(out["positions"], 1)
        self.assertEqual(out["remaining_cash_usdt"], "95.918")
        self.assertEqual(out["results"][1]["reason"], "DUPLICATE_EVENT")
        self.assertEqual(portfolio([a, b], now=T0+310), out)
        self.assertRaises(ValueError, portfolio, [a]*51, now=T0)

    def test_snapshot_default_and_valid_fixture(self):
        empty = from_file("", now=T0+10)
        self.assertEqual(empty["snapshot_status"], "NOT_CONFIGURED")
        self.assertEqual(empty["results"], [])
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "fixture.json"
            file.write_text(json.dumps({"schema_version": 1, "candidates": [fixture()]}))
            result = from_file(str(file), now=T0+310)
            self.assertEqual(result["snapshot_status"], "OFFLINE_FIXTURE_ONLY")
            self.assertEqual(result["positions"], 1)
            self.assertNotIn("telegram", json.dumps(result).lower())


if __name__ == "__main__":
    unittest.main()

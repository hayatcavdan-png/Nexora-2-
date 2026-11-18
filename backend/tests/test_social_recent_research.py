"""Offline opt-in Jupiter recent/manual -> Helius/quote research regression."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from nexora.social_ai import recent_research as R
from nexora.token_safety import TOKEN_PROGRAM, TOKEN_2022

MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"


def profile(mint=MINT):
    return {
        "id": mint, "symbol": "DEMO", "name": "Safe synthetic",
        "liquidity": 23000,
        "audit": {
            "topHoldersPercentage": 22.5,
            "devBalancePercentage": 5.6,
            "isSus": False,
        },
    }


def rpc_result():
    return {"value": {"owner": TOKEN_PROGRAM, "data": {"parsed": {
        "type": "mint", "info": {
            "isInitialized": True,
            "decimals": 6,
            "freezeAuthority": None, "mintAuthority": None,
        }
    }}}}


class FakeRpc:
    def __init__(self, response=None):
        self.response = response if response is not None else rpc_result()
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        return self.response

    def close(self):
        pass


class FakeQuoter:
    def __init__(self, bad_side=None):
        self.calls = []
        self.bad_side = bad_side

    def quote(self, in_mint, out_mint, raw):
        self.calls.append((in_mint, out_mint, raw))
        if in_mint == R.USDT_MINT:
            result = {"in_amount": 4_000_000, "out_amount": 500_000,
                      "price_impact_pct": 1.25}
        else:
            result = {"in_amount": 500_000, "out_amount": 3_800_000,
                      "price_impact_pct": 0.5}
        if self.bad_side == "sell" and in_mint != R.USDT_MINT:
            result["price_impact_pct"] = None
        return result


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.content = json.dumps(data).encode("utf-8")

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, data):
        self.calls = []
        self.data = data

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.data)


class RecentResearchTests(unittest.TestCase):
    def test_recent_dedup_base58_exact_mints(self):
        rows = [{"id": "BAD", "symbol": MINT}, profile(), profile(),
                profile("So11111111111111111111111111111111111111112")]
        found = R.parse_recent(rows)
        self.assertEqual([x["id"] for x in found],
                         [MINT, "So11111111111111111111111111111111111111112"])
        self.assertEqual(R.parse_recent(rows, max_candidates=1)[0]["id"], MINT)

    def test_live_disabled_makes_zero_calls(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            a = R.research_recent()
            b = R.research_manual(MINT)
        self.assertEqual(a["status"], "DISABLED")
        self.assertEqual(b["status"], "DISABLED")
        self.assertEqual(a["results"], [])

    def test_eligible_is_quote_only_never_a_paper_order(self):
        rpc, quote = FakeRpc(), FakeQuoter()
        out = R.analyze(MINT, profile(), rpc_call=rpc.call, quote=quote.quote,
                        measured_at=1_800_000_000)
        self.assertEqual(out["status"], "RESEARCH_CANDIDATE")
        self.assertFalse(out["real_order"])
        self.assertFalse(out["paper_entry"])
        self.assertFalse(out["costs_complete"])
        self.assertTrue(out["quote_only"])
        self.assertEqual(out["expected_token_qty_raw"], "500000")
        self.assertEqual(out["immediate_sell_quote_usdt"], "3.8")
        self.assertEqual(quote.calls, [
            (R.USDT_MINT, MINT, 4_000_000), (MINT, R.USDT_MINT, 500_000)])
        self.assertEqual(rpc.calls[0][0], "getAccountInfo")
        self.assertEqual(rpc.calls[0][1][1]["encoding"], "jsonParsed")

    def test_missing_liquidity_and_audit_avoid_rpc_cost(self):
        for edit, expected in [
            ({"liquidity": 1}, "LIQUIDITY_LOW"),
            ({"liquidity": None}, "LIQUIDITY_UNKNOWN"),
            ({"audit": None}, "AUDIT_UNKNOWN"),
            ({"audit": {"topHoldersPercentage": 98, "devBalancePercentage": 0}},
             "HOLDER_CONCENTRATION_RISK"),
            ({"audit": {"topHoldersPercentage": 5}}, "HOLDER_CONCENTRATION_UNKNOWN"),
            ({"audit": {"topHoldersPercentage": 5, "devBalancePercentage": 1,
                         "isSus": True}}, "JUPITER_SUSPICIOUS_FLAG"),
        ]:
            with self.subTest(edit=edit):
                row = profile()
                row.update(edit)
                rpc, quote = FakeRpc(), FakeQuoter()
                result = R.analyze(MINT, row, rpc_call=rpc.call, quote=quote.quote)
                self.assertEqual(result["reason"], expected)
                self.assertEqual(rpc.calls, [])
                self.assertEqual(quote.calls, [])

    def test_mint_mismatch_unknown_authorities_malformed_and_token2022(self):
        rpc, quote = FakeRpc(), FakeQuoter()
        result = R.analyze(MINT, profile("So11111111111111111111111111111111111111112"),
                           rpc_call=rpc.call, quote=quote.quote)
        self.assertEqual(result["reason"], "SOURCE_MINT_MISMATCH")
        self.assertFalse(rpc.calls)
        for change, expected in [
            ("remove_auth", "TOKEN_AUTHORITY_UNKNOWN"),
            ("freeze", "TOKEN_UNSAFE_OR_UNKNOWN"),
            ("extensions_missing", "TOKEN_2022_EXTENSIONS_UNKNOWN"),
            ("not_mint", "NOT_A_TOKEN_MINT"),
        ]:
            with self.subTest(change=change):
                response = rpc_result()
                info = response["value"]["data"]["parsed"]["info"]
                if change == "remove_auth":
                    del info["mintAuthority"]
                elif change == "freeze":
                    info["freezeAuthority"] = MINT
                elif change == "extensions_missing":
                    response["value"]["owner"] = TOKEN_2022
                elif change == "not_mint":
                    response["value"]["data"]["parsed"]["type"] = "account"
                mock = FakeRpc(response)
                self.assertEqual(R.analyze(MINT, profile(), rpc_call=mock.call,
                                           quote=quote.quote)["reason"], expected)

    def test_bad_price_impact_no_sell_exit_and_roundtrip(self):
        rpc = FakeRpc()
        quote = FakeQuoter("sell")
        result = R.analyze(MINT, profile(), rpc_call=rpc.call, quote=quote.quote)
        self.assertEqual(result["reason"], "SELL_ROUTE_UNKNOWN_OR_UNSAFE")

        def bad_rtt(in_mint, out_mint, raw):
            if in_mint == R.USDT_MINT:
                return {"in_amount": 4_000_000, "out_amount": 500_000,
                        "price_impact_pct": 1}
            return {"in_amount": 500_000, "out_amount": 1_000_000,
                    "price_impact_pct": 1}
        result = R.analyze(MINT, profile(), rpc_call=rpc.call, quote=bad_rtt)
        self.assertEqual(result["reason"], "ROUNDTRIP_LOSS_TOO_HIGH")

    def test_manual_source_exact_mint_and_no_taker_wallet(self):
        rpc, quoter = FakeRpc(), FakeQuoter()
        session = FakeSession([profile(), profile("So11111111111111111111111111111111111111112")])
        with patch.object(R, "_last_request", 0.0):
            result = R.research_manual(
                MINT, enabled=True, rpc=rpc, quoter=quoter, session=session,
                api_key="synthetic-do-not-log", clock=lambda: 1_800_000_000)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["results"][0]["status"], "RESEARCH_CANDIDATE")
        self.assertEqual(session.calls[0][1]["params"], {"query": MINT})
        self.assertTrue(all("taker" not in kw.get("params", {})
                            for _, kw in session.calls))
        self.assertNotIn("synthetic-do-not-log", json.dumps(result))

    def test_recent_limit_and_throttle(self):
        rpc, quoter = FakeRpc(), FakeQuoter()
        session = FakeSession([profile(), profile()])
        with patch.object(R, "_last_request", 0.0):
            first = R.research_recent(
                enabled=True, limit=2, rpc=rpc, quoter=quoter,
                session=session, api_key="synthetic", clock=lambda: 1_800_000_000)
            second = R.research_recent(
                enabled=True, limit=2, rpc=rpc, quoter=quoter,
                session=session, api_key="synthetic", clock=lambda: 1_800_000_000)
        self.assertEqual(first["status"], "OK")
        self.assertEqual(len(first["results"]), 1)
        self.assertEqual(second["status"], "RATE_LIMITED")
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(first["source"], "JUPITER_RECENT_FIRST_POOL_NOT_MINT_BIRTH")

    def test_missing_credentials_or_manual_invalid_ca(self):
        out = R.research_manual("bad", enabled=True, api_key="synthetic")
        self.assertEqual(out["status"], "INVALID_MINT")
        with patch.dict("os.environ", {}, clear=True):
            out = R.research_recent(enabled=True, api_key="")
            self.assertEqual(out["status"], "JUPITER_KEY_MISSING")


if __name__ == "__main__":
    unittest.main()

"""Actual optional library imports and isolated analysis. No network, orders or DB writes."""
import json
import math
import unittest

from nexora.strategy_lab.integrations import (
    duckdb_summary, vectorbt_study, quantstats_summary,
    solana_py_mint_probe,
)

MINT = "4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw"


def bars(n=60):
    return [{
        "ts": 1_800_000_000 + i*60,
        "open": str(1 + i*0.008),
        "high": str(1.01 + i*0.008),
        "low": str(.99 + i*0.008),
        "close": str(1 + i*0.008),
    } for i in range(n)]


class OptionalToolsTests(unittest.TestCase):
    def test_duckdb_aggregate_in_memory(self):
        report = duckdb_summary([
            {"source":"raydium","status":"OK","hypothetical_net_usdt":.25},
            {"source":"raydium","status":"OK","hypothetical_net_usdt":-.10},
            {"source":"orca","status":"UNKNOWN","hypothetical_net_usdt":.00},
            {"source":"telegram","status":"OK","hypothetical_net_usdt":100},
        ])
        self.assertEqual(report["evaluated_rows"], 3)
        self.assertEqual(report["sources"][0]["n"], 2)
        self.assertAlmostEqual(report["sources"][0]["average_hypothetical_usdt"], .075)
        self.assertFalse(report["real_order"])

    def test_vectorbt_actual_backtest(self):
        result = vectorbt_study(bars())
        self.assertEqual(result["mode"], "SYNTHETIC_BACKTEST_ONLY")
        self.assertEqual(result["price_basis"], "next bar open")
        self.assertEqual(result["tools_used"], ["vectorbt"])
        self.assertFalse(result["real_order"])
        self.assertTrue(math.isfinite(result["final_equity_usdt"]))

    def test_quantstats_actual_drawdown(self):
        points = [{"ts": 1_800_000_000 + i*86400,
                   "equity":str(100 + (i%8) - (i%9)*.5)} for i in range(40)]
        result = quantstats_summary(points)
        self.assertEqual(result["tools_used"], ["quantstats"])
        self.assertLessEqual(result["max_drawdown_pct"], 0)
        self.assertFalse(result["real_order"])

    def test_solana_py_async_read_only_mint(self):
        # No HTTP request: mock the AsyncClient context and SOLDERS JSON response.
        import asyncio
        from nexora.token_safety import TOKEN_PROGRAM

        class Response:
            def to_json(self):
                return json.dumps({"result":{"value":{
                    "owner": TOKEN_PROGRAM, "data":{"parsed":{
                        "type":"mint", "info":{
                            "decimals":6, "isInitialized":True,
                            "mintAuthority":None,"freezeAuthority":None,
                        }
                    }}
                }}})
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def get_account_info_json_parsed(self, pubkey, commitment=None):
                self.status = commitment
                return Response()
        obj = asyncio.run(solana_py_mint_probe(
            MINT, "https://mainnet.helius-rpc.com/?api-key=unused-test",
            client_factory=lambda _: Client()))
        self.assertEqual(obj["used_sdk"], "solana-py")
        self.assertEqual(obj["status"], "MINT_CHECK_PASSED")
        self.assertFalse(obj["real_order"])


if __name__ == "__main__":
    unittest.main()

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import unittest
from unittest.mock import Mock, patch

from nexora.helius_client import (
    HeliusClient,
    HeliusRPCError,
)


class HeliusClientTests(unittest.TestCase):
    def setUp(self):
        self.client = HeliusClient(
            rpc_url="https://mainnet.helius-rpc.com/?api-key=test",
            max_retries=0,
        )

    def tearDown(self):
        self.client.close()

    @patch("nexora.helius_client.requests.Session.post")
    def test_health_success(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "ok",
        }
        post.return_value = response

        self.assertEqual(self.client.get_health(), "ok")
        post.assert_called_once()

    @patch("nexora.helius_client.requests.Session.post")
    def test_transaction_request(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": [],
        }
        post.return_value = response

        result = self.client.get_transactions_for_address(
            "WalletPublicAddress",
            limit=50,
        )

        self.assertEqual(result, [])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["method"], "getTransactionsForAddress")
        self.assertEqual(payload["params"][1]["limit"], 50)

    @patch("nexora.helius_client.requests.Session.post")
    def test_mutating_method_blocked(self, post):
        with self.assertRaises(ValueError):
            self.client.call("sendTransaction", [])

        post.assert_not_called()

    @patch("nexora.helius_client.requests.Session.post")
    def test_unknown_method_blocked(self, post):
        with self.assertRaises(ValueError):
            self.client.call("unknownMethod", [])

        post.assert_not_called()

    def test_invalid_retry_count(self):
        with self.assertRaises(ValueError):
            HeliusClient(
                rpc_url="https://mainnet.helius-rpc.com/?api-key=test",
                max_retries=-1,
            )

    def test_invalid_timeout(self):
        with self.assertRaises(ValueError):
            HeliusClient(
                rpc_url="https://mainnet.helius-rpc.com/?api-key=test",
                timeout=0,
            )

    @patch("nexora.helius_client.time.sleep")
    @patch("nexora.helius_client.requests.Session.post")
    def test_429_retries(self, post, sleep):
        first = Mock()
        first.status_code = 429
        first.headers = {"Retry-After": "2"}

        second = Mock()
        second.status_code = 200
        second.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "ok"}

        post.side_effect = [first, second]

        client = HeliusClient(
            rpc_url="https://mainnet.helius-rpc.com/?api-key=test",
            max_retries=1,
        )
        try:
            self.assertEqual(client.get_health(), "ok")
            self.assertEqual(post.call_count, 2)
            sleep.assert_called_once_with(2.0)
        finally:
            client.close()

    @patch("nexora.helius_client.time.sleep")
    @patch("nexora.helius_client.requests.Session.post")
    def test_500_retries(self, post, sleep):
        first = Mock()
        first.status_code = 500
        first.headers = {}

        second = Mock()
        second.status_code = 200
        second.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": "ok"}

        post.side_effect = [first, second]

        client = HeliusClient(
            rpc_url="https://mainnet.helius-rpc.com/?api-key=test",
            max_retries=1,
        )
        try:
            self.assertEqual(client.get_health(), "ok")
            self.assertEqual(post.call_count, 2)
            sleep.assert_called_once()
        finally:
            client.close()

    @patch("nexora.helius_client.requests.Session.post")
    def test_rpc_error_response(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "error": {
                "code": -32602,
                "message": "Invalid params",
            }
        }
        post.return_value = response

        with self.assertRaises(HeliusRPCError):
            self.client.get_health()

    @patch("nexora.helius_client.requests.Session.post")
    def test_invalid_json_rejected(self, post):
        response = Mock()
        response.status_code = 200
        response.json.side_effect = ValueError("Invalid JSON")
        post.return_value = response

        with self.assertRaisesRegex(HeliusRPCError, "JSON"):
            self.client.get_health()

    def test_invalid_wallet_parameters(self):
        with self.assertRaises(ValueError):
            self.client.get_transactions_for_address("")

        with self.assertRaises(ValueError):
            self.client.get_transactions_for_address(
                "WalletPublicAddress",
                limit=0,
            )

        with self.assertRaises(ValueError):
            self.client.get_transactions_for_address(
                "WalletPublicAddress",
                limit=True,
            )

        with self.assertRaises(ValueError):
            self.client.get_transactions_for_address(
                "WalletPublicAddress",
                commitment="processed",
            )

        with self.assertRaises(ValueError):
            self.client.get_transactions_for_address(
                "WalletPublicAddress",
                pagination_token="",
            )



    @patch("nexora.helius_client.requests.Session.post")
    def test_get_transaction_success(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"slot": 123, "meta": {"err": None}},
        }
        post.return_value = response

        result = self.client.get_transaction("TestSignature123")

        self.assertEqual(result["slot"], 123)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["method"], "getTransaction")
        self.assertEqual(payload["params"][0], "TestSignature123")
        self.assertEqual(payload["params"][1]["encoding"], "jsonParsed")
        self.assertEqual(
            payload["params"][1]["maxSupportedTransactionVersion"], 1
        )

    @patch("nexora.helius_client.requests.Session.post")
    def test_get_transaction_invalid_parameters(self, post):
        with self.assertRaises(ValueError):
            self.client.get_transaction("")

        with self.assertRaises(ValueError):
            self.client.get_transaction("TestSignature123", commitment="processed")

        post.assert_not_called()


    @patch("nexora.helius_client.requests.Session.post")
    def test_get_block_success(self, post):
        block = {
            "blockhash": "TestBlockHash",
            "transactions": [
                {"transaction": {"signatures": ["SignatureA"]}},
                {"transaction": {"signatures": ["SignatureB"]}},
            ],
        }
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": block}
        post.return_value = response

        result = self.client.get_block(12345)

        self.assertEqual(result, block)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["method"], "getBlock")
        self.assertEqual(payload["params"][0], 12345)
        options = payload["params"][1]
        self.assertEqual(options["encoding"], "json")
        self.assertEqual(options["transactionDetails"], "full")
        self.assertFalse(options["rewards"])
        self.assertEqual(options["commitment"], "finalized")
        self.assertEqual(options["maxSupportedTransactionVersion"], 1)

    def test_get_block_invalid_slot(self):
        for slot in (-1, True, 1.5, "123"):
            with self.subTest(slot=slot):
                with self.assertRaises(ValueError):
                    self.client.get_block(slot)

    @patch("nexora.helius_client.requests.Session.post")
    def test_get_block_invalid_commitment(self, post):
        with self.assertRaises(ValueError):
            self.client.get_block(12345, commitment="processed")

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

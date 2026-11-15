import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import unittest
from unittest.mock import Mock, patch
import requests

from nexora.helius_client import HeliusClient, HeliusRPCError


class TestStage14HTTPErrorPolicy(unittest.TestCase):

    def test_permanent_http_errors_not_retried(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                client = HeliusClient(
                    rpc_url="https://mainnet.helius-rpc.com/?api-key=test",
                    max_retries=3,
                )
                response = Mock()
                response.status_code = status
                response.raise_for_status.side_effect = requests.HTTPError(
                    "HTTP error", response=response
                )
                try:
                    with patch.object(client.session, "post", return_value=response) as post:
                        with patch("nexora.helius_client.time.sleep") as sleep:
                            with self.assertRaises(HeliusRPCError):
                                client.get_health()
                            self.assertEqual(post.call_count, 1)
                            sleep.assert_not_called()
                finally:
                    client.close()

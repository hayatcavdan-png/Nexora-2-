import io, os, unittest
from nexora.gizle import gizle, GizleyenAkis


class GizleTests(unittest.TestCase):
    def test_masks(self):
        os.environ["HELIUS_API_KEY"] = "abcd1234efgh"
        try:
            self.assertEqual(gizle("https://mainnet.helius-rpc.com/?api-key=XYZ123&x=1"), "https://mainnet.helius-rpc.com/?api-key=[GİZLİ]&x=1")
            self.assertNotIn("abcd1234efgh", gizle("hata: abcd1234efgh reddedildi"))
            self.assertEqual(gizle("X-API-Key: sk_live_1"), "X-API-Key: [GİZLİ]")
            self.assertEqual(gizle("Authorization: Bearer tok.en"), "Authorization: Bearer [GİZLİ]")
            self.assertEqual(gizle("sıradan mesaj 42"), "sıradan mesaj 42")
        finally:
            os.environ.pop("HELIUS_API_KEY")

    def test_stream(self):
        b = io.StringIO(); a = GizleyenAkis(b)
        a.write("wss://x/?api-key=GIZLI1 koptu\n"); a.flush()
        self.assertEqual(b.getvalue(), "wss://x/?api-key=[GİZLİ] koptu\n")


if __name__ == "__main__":
    unittest.main()

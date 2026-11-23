import json, os, tempfile, unittest
from nexora.dosya import json_oku, metin_oku, bayt_oku


class TestDosyaYardimcilari(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_json_oku_ve_kapatma(self):
        p = os.path.join(self.d, "a.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"ad": "çağrı"}, f, ensure_ascii=False)
        self.assertEqual(json_oku(p), {"ad": "çağrı"})

    def test_metin_ve_bayt(self):
        p = os.path.join(self.d, "b.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("merhaba")
        self.assertEqual(metin_oku(p), "merhaba")
        self.assertEqual(bayt_oku(p), "merhaba".encode("utf-8"))

    def test_olmayan_dosya_hata_verir(self):
        with self.assertRaises(FileNotFoundError):
            json_oku(os.path.join(self.d, "yok.json"))


if __name__ == "__main__":
    unittest.main()

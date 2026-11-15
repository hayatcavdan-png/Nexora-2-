import os, sqlite3, tarfile, tempfile, unittest
import yedek
from nexora.core import Paper


class YedekTests(unittest.TestCase):
    def test_backup_restore_roundtrip(self):
        kok = tempfile.mkdtemp()
        p = Paper(os.path.join(kok, "nexora_paper.db")); p.record_buy("e1", "W", "T", 5.0, 1_000_000, 6)
        open(os.path.join(kok, "wallets.txt"), "w").write("W1\n")
        open(os.path.join(kok, ".nexora_env"), "w").write("SECRET=1\n")
        y = yedek.yedekle(kok)
        with tarfile.open(y) as t: adlar = t.getnames()
        self.assertEqual(sorted(adlar), ["nexora_paper.db", "wallets.txt"])          # anahtar dosyası yok
        hedef = tempfile.mkdtemp()
        self.assertEqual(sorted(yedek.geri_yukle(y, hedef)), ["nexora_paper.db", "wallets.txt"])
        c = sqlite3.connect(os.path.join(hedef, "nexora_paper.db"))
        self.assertEqual(c.execute("SELECT COUNT(*) FROM positions").fetchone()[0], 1)

    def test_rotation(self):
        kok = tempfile.mkdtemp()
        Paper(os.path.join(kok, "nexora_paper.db"))
        for i in range(5): yedek.yedekle(kok, sakla=3, simdi=1_700_000_000 + i)
        self.assertEqual(len(os.listdir(os.path.join(kok, "yedekler"))), 3)

    def test_restore_ignores_unknown_paths(self):
        d = tempfile.mkdtemp(); kotu = os.path.join(d, "x.tar.gz")
        open(os.path.join(d, "evil"), "w").write("x")
        with tarfile.open(kotu, "w:gz") as t: t.add(os.path.join(d, "evil"), arcname="../evil.txt")
        self.assertEqual(yedek.geri_yukle(kotu, tempfile.mkdtemp()), [])


if __name__ == "__main__":
    unittest.main()

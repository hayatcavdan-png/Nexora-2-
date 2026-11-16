"""Bildirim taraması (N32, salt okunur kaynaklar): yeni öncü cüzdan alımlarını listede olmayan tokenler için bildirime çevirir.
  python3 bildirim_tara.py      tarar, yeni bildirim sayısını ve son bildirimleri yazdırır"""
import os, sqlite3

from nexora import borsa_liste
from nexora.bildirim import Bildirim, uret

TRACKER = os.getenv("TRACKER_DB", "nexora_tracker.db")
BILDIRIM = os.getenv("BILDIRIM_DB", "nexora_bildirim.db")


def sinyaller(yol=TRACKER, limit=500):
    if not os.path.exists(yol): return []
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=5)
    try:
        cur = c.execute("SELECT id, ts, sig, side, token, wallet FROM tracker_signals WHERE decision='KOPYALANDI' "
                        "ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(id=r[0], ts=r[1], sig=r[2], side=r[3], token=r[4], wallet=r[5]) for r in cur]
    except sqlite3.Error:
        return []
    finally:
        c.close()


if __name__ == "__main__":
    listeli = set(borsa_liste.yukle().keys())
    b = Bildirim(BILDIRIM)
    n = b.ekle(uret(sinyaller(), listeli))
    print(f"Yeni bildirim: {n}")
    for x in b.son(5): print(f"  [{x['tur']}] {x['metin']}")

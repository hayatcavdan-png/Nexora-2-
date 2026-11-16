"""Bildirim taraması (N32, salt okunur kaynaklar): yalnızca bildirim kaydı üretir; emir, anahtar ve ağ yazımı yok.
  - Öncü cüzdan alımlarının listesiz tokenleri (tracker_signals + borsa_liste)
  - Paper işlem açılış/kapanışları ve günlük zarar sınırı aşımı (Solana, BNB, Base paper defterleri)
  python3 bildirim_tara.py"""
import os, sqlite3, time

from nexora import borsa_liste
from nexora.bildirim import Bildirim, uret, islem_bildirimleri, gunluk_zarar_bildirimi

TRACKER = os.getenv("TRACKER_DB", "nexora_tracker.db")
BILDIRIM = os.getenv("BILDIRIM_DB", "nexora_bildirim.db")
DEFTERLER = [("solana", os.getenv("NEXORA_DB", "nexora_paper.db")), ("bnb", "nexora_bnb.db"), ("base", "nexora_base.db")]
ESIK = float(os.getenv("BILDIRIM_GUNLUK_ESIK", "0.03"))          # uygulamadaki daily_loss_pct ile aynı


def _ro(yol):
    if not os.path.exists(yol): return None
    return sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=5)


def sinyaller(yol=TRACKER, limit=500):
    c = _ro(yol)
    if c is None: return []
    try:
        return [dict(id=r[0], ts=r[1], sig=r[2], side=r[3], token=r[4], wallet=r[5]) for r in c.execute(
            "SELECT id, ts, sig, side, token, wallet FROM tracker_signals WHERE decision='KOPYALANDI' ORDER BY id DESC LIMIT ?", (limit,))]
    except sqlite3.Error:
        return []
    finally:
        c.close()


def defter_bildirimleri(eko, yol, now=None, limit=500):
    """Bir paper defterinden işlem ve günlük zarar bildirimleri. Defter yoksa ya da okunamıyorsa boş."""
    now = now or time.time()
    c = _ro(yol)
    if c is None: return []
    out = []
    try:
        satirlar = c.execute("SELECT id, ts, side, token, pnl, decision, wallet FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out += islem_bildirimleri(satirlar, eko)
        st = dict(c.execute("SELECT k, v FROM state WHERE k IN ('cash','day','day_start')").fetchall())
        if st.get("day") and st.get("day_start") and st.get("cash") is not None:
            poz = c.execute("SELECT COALESCE(SUM(qty*last_price),0) FROM positions").fetchone()[0] or 0.0
            equity = float(st["cash"]) + float(poz)
            out += gunluk_zarar_bildirimi(eko, st["day"], float(st["day_start"]), equity, ESIK)
    except (sqlite3.Error, ValueError):
        return out
    finally:
        c.close()
    return out


if __name__ == "__main__":
    listeli = set(borsa_liste.yukle().keys())
    b = Bildirim(BILDIRIM)
    yeni = uret(sinyaller(), listeli)
    for eko, yol in DEFTERLER: yeni += defter_bildirimleri(eko, yol)
    n = b.ekle(yeni)
    print(f"Yeni bildirim: {n}")
    for x in b.son(5): print(f"  [{x['tur']}] {x['metin']}")

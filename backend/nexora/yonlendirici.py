"""Yapay zekâ yönlendirici (N28), 1. sürüm: sinyal kaynaklarını karnelerine göre ağırlıklandıran PAPER portföy.

Kaynaklar: Solana öncü cüzdanlar, Platform 2 borsa sinyalleri, piyasa stratejileri, BNB ve Base cüzdanları. Her kaynak kendi
paper defterinde işlem yapmaya devam eder; yönlendirici bunlara DOKUNMAZ (salt okunur).

Her turda (saatlik):
  1. Her kaynağın değeri okunur (nakit + açık pozisyonların son fiyatı).
  2. Yönlendiricinin değeri, ÖNCEKİ turda belirlenen ağırlıklarla kaynakların bu aralıktaki getirisi kadar değişir
     (geleceğe bakma yok: ağırlık önce verilir, getiri sonra gelir).
  3. Yeni ağırlıklar yalnızca geçmiş kapanan işlemlerden hesaplanır:
       puan = ortalama işlem getirisi x n / (n + K)   (az işlemli kaynağa temkinli: sıfıra doğru çekilir)
     Puanı pozitif olmayan ya da EN_AZ_ISLEM'den az kapanan işlemi olan kaynağa para verilmez (nakitte kalır).
     Tek kaynağa en fazla AZAMI_PAY verilir; dağıtılamayan kısım nakit kalır.
Kabul ölçütü (aşama listesi): 3 hafta paper'da yönlendirici getirisi her kaynağın getirisine eşit ya da daha iyi ya da
daha düşük düşüşle yakın getiri. Gerçek emir YOK."""
import json, math, os, sqlite3, time

PENCERE_GUN = float(os.getenv("YONLENDIRICI_PENCERE_GUN", "14"))
EN_AZ_ISLEM, K, AZAMI_PAY = 5, 10, 0.40
BASLANGIC = 100.0


def kaynaklar(kok="."):
    from nexora import piyasa
    k = [("solana", "Solana öncü cüzdanlar", os.getenv("NEXORA_DB", "nexora_paper.db")),
         ("borsa", "Borsa sinyalleri (Platform 2)", os.getenv("BORSA_DB", "nexora_borsa.db"))]
    k += [(f"strateji_{s.ad}", f"Strateji: {s.ad}", f"nexora_strateji_{s.ad}.db") for s in piyasa.STRATEJILER]
    k += [("bnb", "BNB Chain cüzdanlar", "nexora_bnb.db"), ("base", "Base cüzdanlar", "nexora_base.db")]
    return [(i, ad, yol if os.path.isabs(yol) else os.path.join(kok, yol)) for i, ad, yol in k]


def _oku(yol):
    if not os.path.exists(yol): return None
    return sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=5)


def deger(yol):
    """Kaynağın paper değeri (nakit + pozisyonlar). Okunamazsa None."""
    c = _oku(yol)
    if c is None: return None
    try:
        r = c.execute("SELECT v FROM state WHERE k='cash'").fetchone()
        if not r: return None
        pos = c.execute("SELECT SUM(qty*last_price) FROM positions").fetchone()[0] or 0.0
        v = float(r[0]) + float(pos)
        return v if math.isfinite(v) and v > 0 else None
    except (sqlite3.Error, ValueError, TypeError):
        return None
    finally:
        c.close()


def karne(yol, now=None, gun=PENCERE_GUN):
    """Penceredeki kapanan (satış) işlemlerin sayısı, kazanma oranı, ortalama getiri, toplam K/Z."""
    now = now or time.time()
    c = _oku(yol)
    bos = dict(n=0, kazanma=0.0, ort_getiri=0.0, kz=0.0)
    if c is None: return bos
    try:
        satir = c.execute("SELECT qty, price, fee, pnl FROM trades WHERE LOWER(side)='sell' AND decision='KOPYALANDI' AND ts>=?",
                          (now - gun * 86400,)).fetchall()
    except sqlite3.Error:
        return bos
    finally:
        c.close()
    getiri, kz = [], 0.0
    for qty, price, fee, pnl in satir:
        if pnl is None or not qty or not price: continue
        maliyet = qty * price - (fee or 0.0) - pnl            # satış geliri - K/Z = alış maliyeti
        if maliyet <= 0: continue
        getiri.append(pnl / maliyet); kz += pnl
    if not getiri: return bos
    return dict(n=len(getiri), kazanma=round(sum(g > 0 for g in getiri) / len(getiri), 3),
                ort_getiri=round(sum(getiri) / len(getiri), 5), kz=round(kz, 2))


def agirliklar(karneler):
    """{kaynak: karne} -> {kaynak: pay} (toplam <= 1; kalan nakit)."""
    puan = {}
    for i, k in karneler.items():
        if k["n"] < EN_AZ_ISLEM: continue
        p = k["ort_getiri"] * k["n"] / (k["n"] + K)
        if p > 0: puan[i] = p
    top = sum(puan.values())
    if top <= 0: return {}
    pay = {i: min(AZAMI_PAY, p / top) for i, p in puan.items()}
    return {i: round(v, 4) for i, v in pay.items()}


class Yonlendirici:
    def __init__(self, yol="nexora_yonlendirici.db"):
        self.db = sqlite3.connect(yol, timeout=10)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS tur(ts REAL PRIMARY KEY, deger REAL NOT NULL, agirlik TEXT NOT NULL, kaynak_deger TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS kaynak_baz(kaynak TEXT PRIMARY KEY, ts REAL NOT NULL, deger REAL NOT NULL);
        """)

    def son(self):
        r = self.db.execute("SELECT ts, deger, agirlik, kaynak_deger FROM tur ORDER BY ts DESC LIMIT 1").fetchone()
        return dict(ts=r[0], deger=r[1], agirlik=json.loads(r[2]), kaynak_deger=json.loads(r[3])) if r else None

    def tur(self, kaynak_listesi, now=None):
        now = now or time.time()
        simdi = {i: deger(yol) for i, _, yol in kaynak_listesi}
        once = self.son()
        if once is None:
            yeni_deger = BASLANGIC
        else:
            getiri = 0.0
            for i, w in once["agirlik"].items():                  # önceki ağırlıklar x bu aralığın getirisi
                a, b = once["kaynak_deger"].get(i), simdi.get(i)
                if a and b: getiri += w * (b / a - 1)
            yeni_deger = once["deger"] * (1 + getiri)
        for i, v in simdi.items():                               # kaynağın ilk görüldüğü değer (karşılaştırma tabanı)
            if v: self.db.execute("INSERT OR IGNORE INTO kaynak_baz VALUES(?,?,?)", (i, now, v))
        karneler = {i: karne(yol, now) for i, _, yol in kaynak_listesi}
        w = {i: p for i, p in agirliklar(karneler).items() if simdi.get(i)}
        self.db.execute("INSERT OR REPLACE INTO tur VALUES(?,?,?,?)", (now, yeni_deger, json.dumps(w), json.dumps(simdi)))
        self.db.commit()
        return self.durum(kaynak_listesi, karneler, now)

    def durum(self, kaynak_listesi, karneler=None, now=None):
        now = now or time.time()
        s = self.son()
        if s is None: return dict(bos=True)
        bas = self.db.execute("SELECT ts, deger FROM tur ORDER BY ts LIMIT 1").fetchone()
        zirve = self.db.execute("SELECT MAX(deger) FROM tur").fetchone()[0]
        baz = {r[0]: (r[1], r[2]) for r in self.db.execute("SELECT kaynak, ts, deger FROM kaynak_baz")}
        karneler = karneler or {i: karne(yol, now) for i, _, yol in kaynak_listesi}
        satir = []
        for i, ad, _ in kaynak_listesi:
            b, v = baz.get(i), s["kaynak_deger"].get(i)
            satir.append(dict(kaynak=i, ad=ad, pay=s["agirlik"].get(i, 0.0), karne=karneler.get(i),
                              getiri_pct=round((v / b[1] - 1) * 100, 2) if b and v else None,
                              olcum_gun=round((now - b[0]) / 86400, 1) if b else 0.0))
        return dict(deger=round(s["deger"], 4), getiri_pct=round((s["deger"] / bas[1] - 1) * 100, 2),
                    zirveden_dusus_pct=round((zirve - s["deger"]) / zirve * 100, 2) if zirve else 0.0,
                    nakit_pay=round(1 - sum(s["agirlik"].values()), 4), olcum_gun=round((now - bas[0]) / 86400, 1),
                    kaynaklar=satir, ts=s["ts"],
                    aciklama="Kaynakları geçmiş karnelerine göre ağırlıklandıran sanal portföy. Ağırlık önce verilir, "
                             "getiri sonra ölçülür. Gerçek para yok.")

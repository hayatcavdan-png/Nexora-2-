"""N11 · Pilot cüzdan bakiyesi ve GERÇEK EMİR BAŞARI ÖLÇÜMÜ (imzasız, gönderimsiz).

  python pilot_olcum.py bakiye        # SOL ve USDC bakiyesi (salt okunur)
  python pilot_olcum.py olc           # son sinyal token'ları için alım işlemi oluştur + denetle + zincirde simüle et
  PILOT_N=10 PILOT_USD=1 python pilot_olcum.py olc

Ne ölçer: "bu sinyali şu an gerçekten kopyalasaydık işlem zincirde geçer miydi?" Paper sistemin fiyat tahmini değil,
gerçek cüzdan bakiyesiyle Jupiter'in verdiği gerçek işlemin simülasyonu. Sonuçlar pilot_sim tablosuna yazılır.
Emir GÖNDERİLMEZ, anahtar dosyası OKUNMAZ (yalnızca açık adres). Gerçek emir N12 ve ayrı açık onay ister."""
import os, sqlite3, sys, time

from nexora.constants import USDC_MINT
from nexora.emir import EmirHazirlayici, EmirHatasi, denetle
from nexora.helius_client import HeliusClient, HeliusRPCError
import pilot_cuzdan

DB = os.getenv("NEXORA_DB", "nexora_paper.db")
TRACKER = os.getenv("TRACKER_DB", "nexora_tracker.db")
MIN_SOL = 0.01                                     # ağ ücreti ve token hesabı açılışı için alt sınır


def bakiye(helius, adres):
    sol = (helius.call("getBalance", [adres]).get("value") or 0) / 1e9
    r = helius.call("getTokenAccountsByOwner", [adres, {"mint": USDC_MINT}, {"encoding": "jsonParsed"}])
    usdc = 0.0
    for a in (r or {}).get("value") or []:
        try: usdc += float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
        except (KeyError, TypeError, ValueError): pass
    return dict(sol=round(sol, 6), usdc=round(usdc, 4))


def son_tokenler(tracker_path, n, haric=(USDC_MINT,)):
    if not os.path.exists(tracker_path): return []
    c = sqlite3.connect(f"file:{tracker_path}?mode=ro", uri=True, timeout=5)
    try:
        out = []
        for (t,) in c.execute("SELECT token FROM tracker_signals WHERE side='buy' ORDER BY id DESC LIMIT 500"):
            if t and t not in haric and t not in out: out.append(t)
            if len(out) >= n: break
        return out
    finally:
        c.close()


def _tablo(db):
    db.execute("""CREATE TABLE IF NOT EXISTS pilot_sim(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, token TEXT, usd REAL,
        asama TEXT, basarili INTEGER, hata TEXT, router TEXT, birim INTEGER)""")


def olc(helius, hazirlayici, adres, tokenler, usd, db, bekle=1.1, uyku=time.sleep):
    _tablo(db); sonuc = []
    for i, t in enumerate(tokenler):
        if i: uyku(bekle)                                            # Jupiter hız sınırı
        k = dict(token=t, asama="hazirla", basarili=0, hata=None, router=None, birim=None)
        try:
            o = hazirlayici.hazirla(USDC_MINT, t, int(round(usd * 1e6)), adres)
            k["router"] = o.get("router")
            if not o["transaction"]:
                k["hata"] = o.get("hata") or "işlem oluşturulmadı"
            else:
                sorun, _ = denetle(o["transaction"], adres)
                if sorun: k.update(asama="denetle", hata="; ".join(sorun))
                else:
                    s = hazirlayici.simule(o["transaction"])
                    k.update(asama="simule", basarili=int(s["basarili"]), hata=None if s["basarili"] else str(s["hata"])[:200], birim=s["birim"])
        except (EmirHatasi, HeliusRPCError) as e:
            k["hata"] = str(e)[:200]
        db.execute("INSERT INTO pilot_sim(ts,token,usd,asama,basarili,hata,router,birim) VALUES(?,?,?,?,?,?,?,?)",
                   (time.time(), t, usd, k["asama"], k["basarili"], k["hata"], k["router"], k["birim"]))
        db.commit(); sonuc.append(k)
    return sonuc


def ozet(db):
    _tablo(db)
    r = db.execute("SELECT COUNT(*), SUM(basarili), SUM(asama='simule') FROM pilot_sim").fetchone()
    n, ok, sim = r[0], r[1] or 0, r[2] or 0
    nedenler = db.execute("SELECT COALESCE(hata,'?') h, COUNT(*) FROM pilot_sim WHERE basarili=0 GROUP BY h ORDER BY 2 DESC LIMIT 5").fetchall()
    return dict(n=n, basarili=ok, simule_edilen=sim, oran_pct=round(ok * 100 / n, 1) if n else None, nedenler=nedenler)


def main(argv, helius=None, session=None, db_yolu=DB, tracker=TRACKER, uyku=time.sleep, adres=None):
    komut = argv[0] if argv else "bakiye"
    adres = adres or pilot_cuzdan.adres()
    helius = helius or HeliusClient(max_retries=2)
    b = bakiye(helius, adres)
    print(f"Pilot cüzdan {adres[:4]}…{adres[-4:]}: {b['sol']} SOL · {b['usdc']} USDC")
    if komut == "bakiye":
        if b["sol"] < MIN_SOL: print(f"  Ağ ücreti için en az {MIN_SOL} SOL gerekir.")
        return b
    if komut != "olc": sys.exit("Kullanım: python pilot_olcum.py [bakiye|olc]")
    usd = float(os.getenv("PILOT_USD", "1")); n = int(os.getenv("PILOT_N", "8"))
    if not 0 < usd <= 5: sys.exit("PILOT_USD 0-5 arası olmalı")
    if b["sol"] < MIN_SOL or b["usdc"] < usd:
        print(f"  Ölçüm için en az {MIN_SOL} SOL ve {usd} USDC gerekir. Hiçbir şey denenmedi."); return dict(b, hazir=False)
    tokenler = son_tokenler(tracker, n)
    if not tokenler: print("  Son sinyal yok."); return dict(b, sonuc=[])
    h = EmirHazirlayici(helius, api_key=os.getenv("JUPITER_API_KEY", ""), session=session)
    db = sqlite3.connect(db_yolu, timeout=10)
    try:
        print(f"  {len(tokenler)} token için {usd} USDC alım işlemi simüle ediliyor (GÖNDERİM YOK)…")
        s = olc(helius, h, adres, tokenler, usd, db, uyku=uyku)
        for k in s:
            print(f"   {k['token'][:4]}…{k['token'][-4:]}  {'GEÇER' if k['basarili'] else 'GEÇMEZ'}  {k['asama']}"
                  + (f"  ({k['hata'][:70]})" if k["hata"] else f"  {k['birim']} CU, {k['router']}"))
        o = ozet(db)
        print(f"  Toplam (tüm ölçümler): {o['basarili']}/{o['n']} geçti (%{o['oran_pct']})")
        for h_, c in o["nedenler"]: print(f"    {c}× {h_[:90]}")
        return dict(b, sonuc=s, ozet=o)
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])

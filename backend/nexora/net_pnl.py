"""Geliştirme 4 (PROFIT ENGINE V1): gerçekçi net kâr/zarar ve mutabakat. SALT OKUMA; hiçbir kaydı değiştirmez.

Girdi: paper motorunun `trades` tablosu (yalnızca decision='KOPYALANDI').
  - Alım satırı: price = gerçekleşen (kaymalı) alım fiyatı, fee = alım ücreti.
  - Satım satırı: price = gerçekleşen (kaymalı) satım fiyatı, fee = satım ücreti, pnl = motorun bildirdiği K/Z.

Hesaplar (her kapanmış bacak için, cüzdan+token bazında FIFO eşleşme):
  brut_usd   = miktar * (satım_fiyatı - alım_fiyatı)            (ücret ve kayma dahil gerçekleşen fiyatlar üzerinden)
  ucret_usd  = alım_ücreti + satım_ücreti
  net_usd    = brut_usd - ucret_usd
  bildirilen = motorun yazdığı pnl; fark = bildirilen - net  (mutabakat)

SINIRLAR (raporda da yazılır):
  - Ham (kaymasız) fiyat kaydedilmediği için kayma ayrı gösterilemez; brüt, kaymayı İÇERİR.
  - Açık pozisyonlar yalnızca 'gerçekleşmemiş' olarak ayrı verilir; kapanmış K/Z'ye katılmaz.
  - Aynı satım iki kez sayılmaz (her satım satırı yalnızca bir kez eşleşir).
"""
import os, sqlite3
from collections import defaultdict, deque

TOLERANS_USD = 0.01


def eslestir(trades, anahtar_modu=None):
    """trades: [dict(ts, wallet, token, side, qty, price, fee, pnl)] zaman sıralı.
    Dönüş: (kapanan_bacaklar, acik_pozisyonlar, satis_mutabakat).
    Bacak: dict(wallet, token, qty, alim_fiyat, satim_fiyat, brut_usd, ucret_usd, net_usd, satim_ts, satim_no).
    satis_mutabakat: her satış olayı için dict(satim_no, net_usd (bacakların toplamı), bildirilen (motorun pnl'i))."""
    # anahtar_modu: "cuzdan" (varsayılan; cüzdan+token FIFO) | "token" (paper motorunun aynısı: pozisyonlar yalnızca token
    # bazında tutulur, farklı cüzdanların alımları tek havuzda birleşir). Mutabakat farkının kaynağını ayırt etmek için.
    modu = anahtar_modu or os.getenv("NET_PNL_ANAHTAR", "cuzdan")
    kuyruk = defaultdict(deque)            # (wallet, token) veya (token) -> [alım dict'leri] FIFO
    kapanan, satis_mut = [], []
    for no, t in enumerate(sorted(trades, key=lambda x: x["ts"])):
        anahtar = (t["wallet"], t["token"]) if modu == "cuzdan" else (t["token"],)
        if t["side"] == "buy":
            kuyruk[anahtar].append(dict(qty=float(t["qty"]), price=float(t["price"]), fee=float(t["fee"] or 0), ts=t["ts"]))
            continue
        if t["side"] != "sell": continue
        toplam = float(t["qty"]); kalan = toplam; satim_fee = float(t["fee"] or 0); satim = float(t["price"])
        olay = []
        while kalan > 1e-12 and kuyruk[anahtar]:
            al = kuyruk[anahtar][0]
            k = min(kalan, al["qty"])
            brut = k * (satim - al["price"])
            ucret = al["fee"] * (k / al["qty"]) + satim_fee * (k / toplam if toplam else 0.0)
            b = dict(wallet=t["wallet"], token=t["token"], qty=k, alim_fiyat=al["price"], satim_fiyat=satim,
                     alim_ts=al["ts"], satim_ts=t["ts"], satim_no=no, brut_usd=brut, ucret_usd=ucret, net_usd=brut - ucret)
            olay.append(b)
            al["fee"] -= al["fee"] * (k / al["qty"])     # kalan alım ücreti, kalan miktarla orantılı
            al["qty"] -= k
            kalan -= k
            if al["qty"] <= 1e-12: kuyruk[anahtar].popleft()
        kapanan.extend(olay)
        if olay and t.get("pnl") is not None:
            satis_mut.append(dict(satim_no=no, net_usd=round(sum(b["net_usd"] for b in olay), 6), bildirilen=float(t["pnl"])))
    acik = []
    for anahtar, q in kuyruk.items():
        w, tok = (anahtar if len(anahtar) == 2 else (None, anahtar[0]))
        for al in q:
            if al["qty"] > 1e-12:
                acik.append(dict(wallet=w, token=tok, qty=al["qty"], alim_fiyat=al["price"], alim_ts=al["ts"], ucret_usd=al["fee"]))
    return kapanan, acik, satis_mut


def mutabakat(satis_mut):
    """Satış olayı bazında: motorun bildirdiği K/Z ile yeniden hesaplanan net K/Z (bacakların toplamı) karşılaştırması."""
    fark = [s["bildirilen"] - s["net_usd"] for s in satis_mut]
    asan = sum(1 for f in fark if abs(f) > TOLERANS_USD)
    return dict(karsilastirilan=len(fark), toleransi_asan=asan, toplam_fark=round(sum(fark), 4) if fark else 0.0,
                eslesmeyen_yuzde=round(100.0 * asan / len(fark), 1) if fark else None)


def ozet(bacaklar):
    """Kapanmış bacaklardan: brüt, ücret, net toplamı; kazanma oranı; beklenen net değer; maksimum düşüş."""
    if not bacaklar:
        return dict(bacak=0, brut=0.0, ucret=0.0, net=0.0, kazanma=None, beklenen_net=None, maks_dusus=0.0)
    sirali = sorted(bacaklar, key=lambda b: b["satim_ts"])
    kum, zirve, dd = 0.0, 0.0, 0.0
    for b in sirali:
        kum += b["net_usd"]; zirve = max(zirve, kum); dd = min(dd, kum - zirve)
    n = len(bacaklar)
    kaz = sum(1 for b in bacaklar if b["net_usd"] > 0)
    return dict(bacak=n, brut=round(sum(b["brut_usd"] for b in bacaklar), 4), ucret=round(sum(b["ucret_usd"] for b in bacaklar), 4),
                net=round(sum(b["net_usd"] for b in bacaklar), 4), kazanma=round(100.0 * kaz / n, 1),
                beklenen_net=round(sum(b["net_usd"] for b in bacaklar) / n, 4), maks_dusus=round(dd, 4))


def acik_deger(acik, fiyatlar):
    """Açık pozisyonların gerçekleşmemiş K/Z'si. fiyatlar: {token: son_fiyat}. Fiyatı olmayanlar 'belirsiz' sayılır, toplama girmez."""
    gerc, belirsiz = 0.0, 0
    for p in acik:
        f = fiyatlar.get(p["token"])
        if f is None:
            belirsiz += 1; continue
        gerc += p["qty"] * (f - p["alim_fiyat"]) - p["ucret_usd"]
    return dict(gerceklesmemis=round(gerc, 4), belirsiz=belirsiz, acik=len(acik))


def db_oku(path):
    """Paper veritabanından KOPYALANDI satırlarını salt okunur çeker."""
    if not path or not os.path.exists(path): return []
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        cur = c.execute("SELECT ts, wallet, token, side, qty, price, fee, pnl FROM trades WHERE decision='KOPYALANDI' ORDER BY ts")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        c.close()


if __name__ == "__main__":                       # elle: python3 -m nexora.net_pnl
    kap, acik, sm = eslestir(db_oku(os.getenv("PAPER_DB", "nexora_paper.db")))
    o, m = ozet(kap), mutabakat(sm)
    print(f"Net K/Z (kapanan): {o['bacak']} bacak · brüt {o['brut']:+.2f}$ · ücret {o['ucret']:.2f}$ · net {o['net']:+.2f}$")
    print(f"Kazanma %{o['kazanma']} · beklenen net/bacak {o['beklenen_net']} · maks düşüş {o['maks_dusus']}$")
    print(f"Mutabakat: {m['karsilastirilan']} satış karşılaştırıldı, {m['toleransi_asan']} tanesi toleransı aşıyor, toplam fark {m['toplam_fark']}$")
    print(f"Açık pozisyon: {len(acik)} (gerçekleşmemiş K/Z ayrı, fiyat verisiyle hesaplanır)")
    print("Not: ham (kaymasız) fiyat kaydedilmediği için brüt K/Z kaymayı içerir.")

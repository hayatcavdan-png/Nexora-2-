"""Portföy denetimi (salt okunur): defteri işlem kayıtlarından baştan hesaplar ve kayıtlı nakitle karşılaştırır;
açık pozisyonların değerlemesini, en büyük kâr/zararları ve son işlemleri listeler.
Çalıştır (backend klasöründe): python portfoy_denetim.py"""
import os, re, sqlite3, sys, time

from nexora.core import CFG


def denetle(path, now=None):
    now = now if now is not None else time.time()
    if not os.path.exists(path): return dict(hazir=False)
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        st = {r["k"]: r["v"] for r in c.execute("SELECT k, v FROM state")}
        tr = [dict(r) for r in c.execute("SELECT * FROM trades WHERE decision='KOPYALANDI' ORDER BY id")]
        poz = [dict(r) for r in c.execute("SELECT * FROM positions")]
    finally:
        c.close()
    nakit_beklenen = CFG["start_cash"]
    for t in tr:
        tutar = (t["qty"] or 0) * (t["price"] or 0)
        nakit_beklenen += -(tutar + (t["fee"] or 0)) if t["side"] == "buy" else (tutar - (t["fee"] or 0))
    nakit = float(st.get("cash", 0) or 0)
    sat = [t for t in tr if t["side"] == "sell"]
    gerceklesen = sum(t["pnl"] or 0 for t in sat)
    alim_ucreti = sum(t["fee"] or 0 for t in tr if t["side"] == "buy")
    pozlar = []
    for p in poz:
        deger = (p["qty"] or 0) * (p["last_price"] or 0)
        mts = st.get(f"mark_ts:{p['token']}")
        pozlar.append(dict(token=p["token"], cuzdan=p["wallet"], maliyet=round(p["cost"], 4), deger=round(deger, 4),
                           kz=round(deger - p["cost"], 4), kz_pct=round((deger / p["cost"] - 1) * 100, 1) if p["cost"] else None,
                           degerleme_once_sn=round(now - float(mts)) if mts else None))
    pozisyon_deger = sum(x["deger"] for x in pozlar)
    toplam = nakit + pozisyon_deger
    # Kimlik: toplam = başlangıç + gerçekleşen - alım ücretleri + gerçekleşmemiş
    beklenen_toplam = CFG["start_cash"] + gerceklesen - alim_ucreti + sum(x["kz"] for x in pozlar)
    # Şüpheli: alış anında al-sat kaybı %-2'nin altında (teklifler çelişkili) açılmış ve kapanmış pozisyonlar
    alis_rt = {}
    for t in tr:
        if t["side"] == "buy":
            m = re.search(r"al-sat kaybı %(-?[\d.]+)", t["reason"] or "")
            if m: alis_rt[t["token"]] = float(m.group(1))
    supheli = [dict(id=t["id"], token=t["token"], pnl=round(t["pnl"] or 0, 4), al_sat=alis_rt.get(t["token"]))
               for t in sat if alis_rt.get(t["token"], 0) < -2.0]
    return dict(hazir=True, supheli=supheli, supheli_kz=round(sum(x["pnl"] for x in supheli), 4), nakit=round(nakit, 4), nakit_beklenen=round(nakit_beklenen, 4), nakit_farki=round(nakit - nakit_beklenen, 4),
                pozisyon_degeri=round(pozisyon_deger, 4), toplam=round(toplam, 4), toplam_farki=round(toplam - beklenen_toplam, 4),
                gerceklesen=round(gerceklesen, 4), alim_ucreti=round(alim_ucreti, 4), gerceklesmemis=round(sum(x["kz"] for x in pozlar), 4),
                pozisyonlar=pozlar,
                en_buyuk=sorted(({k: t[k] for k in ("id", "ts", "token", "wallet", "pnl", "reason")} for t in sat), key=lambda t: -abs(t["pnl"] or 0))[:5],
                son=[{k: t[k] for k in ("id", "ts", "side", "token", "wallet", "pnl", "reason")} for t in tr[-10:]])


def metin(d):
    if not d.get("hazir"): return "Paper veritabanı yok."
    kisa = lambda a: (a or "")[:4] + "…" + (a or "")[-4:]
    tamam = abs(d["nakit_farki"]) < 0.01 and abs(d["toplam_farki"]) < 0.01
    L = [("DEFTER TUTARLI" if tamam else "UYARI: DEFTER TUTARSIZ"),
         f"Nakit {d['nakit']:.2f} (işlemlerden hesaplanan {d['nakit_beklenen']:.2f}, fark {d['nakit_farki']:+.4f})",
         f"Pozisyon değeri {d['pozisyon_degeri']:.2f} · toplam {d['toplam']:.2f}",
         f"Başlangıç {100:.2f} + gerçekleşen {d['gerceklesen']:+.2f} − alım ücretleri {d['alim_ucreti']:.2f} + gerçekleşmemiş {d['gerceklesmemis']:+.2f}"
         f" = {100 + d['gerceklesen'] - d['alim_ucreti'] + d['gerceklesmemis']:.2f} (fark {d['toplam_farki']:+.4f})"]
    if d.get("supheli"):
        L += ["", f"UYARI: {len(d['supheli'])} kapanış tutarsız teklifle açılmış (alışta al-sat kaybı %-2'nin altında); "
                  f"toplam etkisi {d['supheli_kz']:+.2f} USDC gerçekçi değil. Bunlar hariç toplam ≈ {d['toplam'] - d['supheli_kz']:.2f}:"]
        L += [f"  #{x['id']} {kisa(x['token'])} {x['pnl']:+.2f} (alışta al-sat %{x['al_sat']})" for x in d["supheli"]]
    L += ["", "Açık pozisyonlar:"]
    for p in d["pozisyonlar"]:
        L.append(f"  {kisa(p['token'])} {p['cuzdan'][:4] if p['cuzdan'] else '?'}…  maliyet {p['maliyet']:.2f}  değer {p['deger']:.2f}"
                 f"  K/Z {p['kz']:+.2f} (%{p['kz_pct']})  değerleme {p['degerleme_once_sn']} sn önce")
    L += ["", "En büyük gerçekleşen K/Z:"]
    L += [f"  #{t['id']} {time.strftime('%d.%m %H:%M', time.localtime(t['ts']))} {kisa(t['token'])} {kisa(t['wallet'])} {t['pnl']:+.2f}  {t['reason']}" for t in d["en_buyuk"]]
    L += ["", "Son 10 işlem:"]
    L += [f"  #{t['id']} {time.strftime('%d.%m %H:%M', time.localtime(t['ts']))} {t['side']:<4} {kisa(t['token'])} {kisa(t['wallet'])} "
          f"{(t['pnl'] or 0):+.2f}  {t['reason']}" for t in d["son"]]
    return "\n".join(L)


if __name__ == "__main__":
    print(metin(denetle(sys.argv[1] if len(sys.argv) > 1 else os.getenv("NEXORA_DB", "nexora_paper.db"))))

"""Strateji teşhisi (salt okunur): neden kâr yok? Cüzdan seçimi mi, giriş mi, çıkış mı, kurallar mı?
Paper defterine, takip ve etiket veritabanlarına yalnızca okuma için bağlanır; hiçbir şey yazmaz, ağ isteği yapmaz.
Çalıştır (backend klasöründe):  python3 strateji_teshis.py [gün=3]"""
import json, os, sqlite3, sys, time
from collections import defaultdict
from statistics import median

GUN = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0


def _ro(path):
    if not os.path.exists(path): return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10); c.row_factory = sqlite3.Row
    return c


def _q(c, sql, args=()):
    if c is None: return []
    try: return [dict(r) for r in c.execute(sql, args)]
    except sqlite3.OperationalError: return []


def _k(w): return (w[:4] + "…" + w[-4:]) if w and len(w) > 10 else (w or "?")


def _md(v): return round(median(v), 1) if v else None


def _ort(v): return round(sum(v) / len(v), 1) if v else None


def _liste(path):
    try: return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]
    except OSError: return []


def rapor(now=None):
    now = now or time.time(); bas = now - GUN * 86400
    p = _ro(os.getenv("NEXORA_DB", "nexora_paper.db"))
    t = _ro(os.getenv("TRACKER_DB", "nexora_tracker.db"))
    e = _ro(os.getenv("ETIKET_DB", "nexora_etiket.db"))
    L = [f"== STRATEJİ TEŞHİSİ: son {GUN:g} gün =="]

    # 1) Defter
    tr = _q(p, "SELECT * FROM trades WHERE ts>=?", (bas,))
    al = [x for x in tr if x["side"] == "buy" and x["decision"] == "KOPYALANDI"]
    sat = [x for x in tr if x["side"] == "sell" and x["decision"] == "KOPYALANDI"]
    pnl = [x["pnl"] or 0 for x in sat]
    poz = _q(p, "SELECT * FROM positions")
    acik_mal = sum(x["cost"] or 0 for x in poz)
    acik_deg = sum((x["qty"] or 0) * (x["last_price"] or 0) for x in poz)
    L.append(f"[1] Alım {len(al)}, satış {len(sat)}, gerçekleşen K/Z {sum(pnl):+.2f}$, "
             f"kazanan {sum(1 for v in pnl if v > 0)}/{len(pnl)}")
    L.append(f"    Açık {len(poz)} poz: maliyet {acik_mal:.2f}$, değer {acik_deg:.2f}$ ({acik_deg - acik_mal:+.2f}$)")
    iz = _q(p, "SELECT * FROM pos_iz WHERE opened_ts>=?", (bas,))
    kap = [x for x in iz if x["status"] == "closed" and x["closed_ts"] and x["opened_ts"]]
    if kap:
        L.append(f"    Tutma süresi medyan {_md([(x['closed_ts'] - x['opened_ts']) / 60 for x in kap])} dk; "
                 f"en kötü an ort %{_ort([x['min_pct'] for x in kap if x['min_pct'] is not None])}, "
                 f"en iyi an ort %{_ort([x['max_pct'] for x in kap if x['max_pct'] is not None])}")
        tepe = [x for x in kap if (x["max_pct"] or 0) >= 20]
        if tepe: L.append(f"    %20+ kâra çıkıp sonra kapanan {len(tepe)} poz: sonuç toplamı {sum(x['pnl'] or 0 for x in tepe):+.2f}$ "
                          "(kâr alma olsaydı korunabilirdi)")
    takili = _q(p, "SELECT COUNT(*) n FROM durum_gecis WHERE yeni='TAKILDI' AND ts>=?", (bas,))
    if takili and takili[0]["n"]: L.append(f"    Satış teklifi alınamayıp takılan: {takili[0]['n']}")

    # 2) Red nedenleri
    red = defaultdict(int)
    for x in tr:
        if x["side"] == "buy" and x["decision"] != "KOPYALANDI":
            red[(x["reason"] or "?").split(":")[0].split("(")[0].strip()[:42]] += 1
    if red:
        L.append(f"[2] Reddedilen alım {sum(red.values())}:")
        for r, n in sorted(red.items(), key=lambda kv: -kv[1])[:8]: L.append(f"    {n:>4}  {r}")

    # 3) Etiket: kopyalasaydık (gerçek teklif, $5, ücret dahil)
    son = _q(e, """SELECT o.wallet, o.al_sat_kaybi_pct rt, o.gecikme_sn gec, s.ufuk, s.getiri_pct g FROM etiket_olay o
                   JOIN etiket_sonuc s ON s.event_id=o.event_id WHERE o.ts>=? AND s.getiri_pct IS NOT NULL""", (bas,))
    if son:
        L.append("[3] Her sinyali kopyalasaydık (gerçek teklif, ücret dahil):")
        for u in ("5dk", "30dk", "kaynak"):
            g = [x["g"] for x in son if x["ufuk"] == u]
            if g: L.append(f"    {u:>6}: n={len(g):<4} ort %{_ort(g):+} medyan %{_md(g):+} pozitif %{round(100 * sum(v > 0 for v in g) / len(g))}")
        ol = _q(e, "SELECT al_sat_kaybi_pct rt, gecikme_sn gec FROM etiket_olay WHERE ts>=?", (bas,))
        L.append(f"    al-sat kaybı medyan %{_md([x['rt'] for x in ol if x['rt'] is not None])}, "
                 f"sinyal gecikmesi medyan {_md([x['gec'] for x in ol if x['gec'] is not None])} sn")
        cz = defaultdict(lambda: defaultdict(list))
        for x in son: cz[x["wallet"]][x["ufuk"]].append(x["g"])
        L.append("[4] Cüzdan bazında (kaynak satınca çıkış, yoksa 30dk): n / ort / medyan / pozitif")
        sat_ = []
        for w, d in cz.items():
            g = d.get("kaynak") or d.get("30dk") or []
            if g: sat_.append((w, len(g), _ort(g), _md(g), round(100 * sum(v > 0 for v in g) / len(g))))
        for w, n, o, m, pz in sorted(sat_, key=lambda x: -(x[2] or -999))[:14]:
            L.append(f"    {_k(w)} n={n:<3} ort %{o:+} med %{m:+} poz %{pz}")
    else:
        L.append("[3] Etiket verisi yok (nexora_etiket.db boş ya da yok)")

    # 5) Gölge (reddedilenler)
    gl = _q(p, "SELECT reason, pnl_usd FROM shadow WHERE opened_ts>=? AND status!='open'", (bas,))
    if gl:
        gg = defaultdict(list)
        for x in gl: gg[(x["reason"] or "?").split("(")[0].strip()[:36]].append(x["pnl_usd"] or 0)
        L.append("[5] Gölge (reddedilseydi değil de girseydik): neden / n / toplam K/Z")
        for r, v in sorted(gg.items(), key=lambda kv: -len(kv[1]))[:6]: L.append(f"    {r:<36} {len(v):>3} {sum(v):+.2f}$")

    # 6) Zarar kesme ölçümü
    try:
        from nexora.rapor import stop_summary
        z = stop_summary(_q(p, "SELECT * FROM pos_iz"), _q(p, "SELECT * FROM stop_tetik"))
        if z["kapanan"]:
            L.append(f"[6] Zarar kesme (tüm zamanlar, {z['kapanan']} kapanmış): gerçek {z['gercek_kz']:+.2f}$; " +
                     ", ".join(f"%{x['esik']} stop {x['fark']:+.2f}$" for x in z["esikler"]))
    except Exception as ex:
        L.append(f"[6] zarar kesme hesaplanamadı: {type(ex).__name__}")

    # 7) Liste
    w, izle = _liste("wallets.txt"), _liste("izle_listesi.txt")
    sinyal = _q(t, "SELECT wallet, COUNT(*) n FROM tracker_signals WHERE side='BUY' AND ts>=? GROUP BY wallet", (bas,))
    aktif = {x["wallet"] for x in sinyal}
    try: ks = json.load(open("kesif_son.json"))
    except (OSError, ValueError): ks = {}
    onerilen = [x["wallet"] for x in ks.get("kopyalanabilir", [])]
    L.append(f"[7] Takip {len(w)} cüzdan (izle {len(izle)}), son {GUN:g} günde alım yapan {len(aktif & set(w))}; "
             f"son keşif önerisi {len(onerilen)}, listede olmayan {len([x for x in onerilen if x not in w])}")
    sessiz = [x for x in w if x not in aktif]
    if sessiz: L.append(f"    Sessiz cüzdanlar: {', '.join(_k(x) for x in sessiz[:10])}")
    for c in (p, t, e):
        if c is not None: c.close()
    return "\n".join(L)


if __name__ == "__main__":
    print(rapor())

"""Strateji teşhisi (salt okunur): neden kâr yok? Cüzdan seçimi mi, giriş mi, çıkış mı, kurallar mı?
Paper defterine, takip ve etiket veritabanlarına yalnızca okuma için bağlanır; hiçbir şey yazmaz, ağ isteği yapmaz.
Sunucu /teshis (yalnızca kurucu) ve günlük özet bildirimi bunu kullanır. Elle:  python3 strateji_teshis.py [gün=3]"""
import json, os, sqlite3, sys, time
from collections import defaultdict
from statistics import median



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


def rapor(now=None, GUN=3.0):
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
        if tepe: L.append(f"    %20+ kâra çıkan {len(tepe)} poz: kapanışta toplam {sum(x['pnl'] or 0 for x in tepe):+.2f}$")
    # 1b) Çıkışı kim tetikledi? (20.11 düzeltmesinden önce, aynı token'ı satan HERHANGİ bir izlenen cüzdan pozisyonu kapatıyordu)
    acan = {}
    for x in _q(p, "SELECT token, wallet, closed_ts FROM pos_iz WHERE closed_ts IS NOT NULL AND closed_ts>=?", (bas - 60,)):
        acan.setdefault(x["token"], []).append((x["closed_ts"], x["wallet"]))
    grup = defaultdict(list)
    for s in sat:
        a = min(acan.get(s["token"], []), key=lambda v: abs(v[0] - s["ts"]), default=None)
        if a is None or abs(a[0] - s["ts"]) > 120: continue
        ev = str(s["event_id"])
        grup["zaman aşımı (24 sa)" if ev.startswith("zaman:") else "kaynakta token kalmadı" if ev.startswith("aktarim:")
             else "açan cüzdan" if s["wallet"] in (a[1], "MANUEL") else "BAŞKA cüzdan"].append(s["pnl"] or 0)
    if grup:
        L.append("    Çıkışı tetikleyen: " + "; ".join(f"{k} {len(v)} satış {sum(v):+.2f}$" for k, v in sorted(grup.items())))
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

    # 8) Token özellikleri: hangi token türü kaybettiriyor? (kaynak satınca çıkış getirisi)
    tk = _q(e, """SELECT o.tb_yas_sn yas, o.tb_likidite lik, o.tb_organik org, o.tb_top_pct top, o.tb_dev_pct dev,
                         o.al_sat_kaybi_pct rt, s.getiri_pct g FROM etiket_olay o JOIN etiket_sonuc s ON s.event_id=o.event_id
                  WHERE s.ufuk='kaynak' AND s.getiri_pct IS NOT NULL AND o.ts>=?""", (now - max(GUN, 14) * 86400,))
    if tk:
        L.append(f"[8] Token türüne göre (son {max(GUN, 14):g} gün, kaynak satınca çıkış): n / ort / pozitif")
        boyut = [("Yaş", "yas", [("<1 sa", 0, 3600), ("1-24 sa", 3600, 86400), (">1 gün", 86400, 1e18)]),
                 ("Likidite", "lik", [("<10k$", 0, 1e4), ("10-50k$", 1e4, 5e4), ("50-250k$", 5e4, 2.5e5), (">250k$", 2.5e5, 1e18)]),
                 ("Organik", "org", [("<30", 0, 30), ("30-60", 30, 60), ("60+", 60, 1e9)]),
                 ("Top10 pay", "top", [("<%20", 0, 20), ("%20-40", 20, 40), (">%40", 40, 1e9)]),
                 ("Al-sat kaybı", "rt", [("<%1", -1e9, 1), ("%1-3", 1, 3), (">%3", 3, 1e9)])]
        for ad, k, aral in boyut:
            par = []
            for et, lo, hi in aral:
                g = [x["g"] for x in tk if x[k] is not None and lo <= x[k] < hi]
                if g: par.append(f"{et} {len(g)}/{_ort(g):+}/%{round(100 * sum(v > 0 for v in g) / len(g))}")
            if par: L.append(f"    {ad:<12} " + "  ".join(par))

        # 9) Aday filtre kuralları (al-sat kaybı <= %3 olanlar üzerinde; o sınır artık uygulanıyor)
        taban = [x for x in tk if x["rt"] is not None and x["rt"] <= 3]
        if taban:
            genc = lambda x: x["yas"] is not None and x["yas"] < 3600
            sig = lambda x: x["lik"] is not None and x["lik"] < 1e4
            org = lambda x: x["org"] is not None and x["org"] < 30
            kurallar = [("genç (<1 sa)", genc), ("sığ (<10k$)", sig), ("organik<30", org),
                        ("genç VE sığ", lambda x: genc(x) and sig(x)), ("genç VEYA sığ", lambda x: genc(x) or sig(x)),
                        ("sığ VEYA org<30", lambda x: sig(x) or org(x)), ("üçünden biri", lambda x: genc(x) or sig(x) or org(x))]
            tg = [x["g"] for x in taban]
            L.append(f"[9] Filtre denemesi (al-sat <= %3, n={len(tg)}, ort %{_ort(tg):+}): kural / elenen n ort / kalan n ort poz")
            for ad, f in kurallar:
                el = [x["g"] for x in taban if f(x)]; ka = [x["g"] for x in taban if not f(x)]
                if el and ka:
                    L.append(f"    {ad:<16} {len(el):>3} %{_ort(el):+6} | {len(ka):>3} %{_ort(ka):+6} %{round(100 * sum(v > 0 for v in ka) / len(ka))}")

    # 10) Deney masası: aynı sinyaller farklı kurallarla
    try:
        from nexora import deney
        m = deney.masa(os.getenv("ETIKET_DB", "nexora_etiket.db"), now, gun=14)
        if m["sinyal"]:
            L.append(f"[10] Deney masası (son 14 gün, {m['sinyal']} ölçülmüş sinyal, 100$ ile yeniden oynatma):")
            L.append("    kural / işlem / kaçan / K/Z / kazanan / en büyük düşüş")
            for r in m["sonuclar"]:
                L.append(f"    {r['ad']}")
                L.append(f"      {r['islem']:>4} işlem {r['kacan']:>4} kaçan  {r['kz']:+7.2f}$  %{r['kazanan']:<3} düşüş {r['dusus']:.2f}$"
                         + (f"  (sınır yüzünden {r['limit_durdu']} alım yok)" if r.get("limit_durdu") else ""))
    except Exception as ex:
        L.append(f"[10] deney masası hesaplanamadı: {type(ex).__name__}")
    try:                                   # 10b) ALPHA HUNTER X fikirleri: çoklu cüzdan teyidi ve geri çekilmede giriş
        from nexora import deney
        m = deney.modeller(os.getenv("ETIKET_DB", "nexora_etiket.db"), now, gun=14)
        if m["sinyal"]:
            L.append(f"[10b] Giriş modelleri (son 14 gün, 8x%5, al-sat <= %3): model / aday / işlem / K/Z / kazanan / düşüş")
            for r in m["sonuclar"]:
                L.append(f"    {r['ad']}")
                L.append(f"      {r['aday']:>4} aday {r['islem']:>4} işlem  {r['kz']:+7.2f}$  %{r['kazanan']:<3} düşüş {r['dusus']:.2f}$")
    except Exception as ex:
        L.append(f"[10b] giriş modelleri hesaplanamadı: {type(ex).__name__}")

    try:                                   # 11) Gölge havuz ve yapay zekâ verisi
        from nexora import golge
        k = golge.karne(os.getenv("ETIKET_DB", "nexora_etiket.db"), now=now)
        from nexora.ozellik import veri_seti
        n = len(veri_seti(os.getenv("ETIKET_DB", "nexora_etiket.db")))
        L.append(f"[11] Gölge havuz {k['havuz']} cüzdan (kopyalanmaz): {k['olculen']} ölçüldü, {k['sinyal']} sinyal (14 gün), "
                 f"terfi adayı {len(k['terfi'])}. Yapay zekâ verisi: {n}/500 etiketli örnek")
        for w, m in [x for x in k["satirlar"] if x[0] in k["terfi"]][:5]:
            L.append(f"    terfi adayı {_k(w)}  n={m['n']} ort %{m['ort']:+.1f} medyan %{m['medyan']:+.1f}")
    except Exception as ex:
        L.append(f"[11] gölge havuz hesaplanamadı: {type(ex).__name__}")

    try:                                   # 12) Yapay zekâ gölge kararı (N19): model ileriye dönük ne seçti, ne oldu
        from nexora.model_kapisi import golge_rapor
        g = golge_rapor(os.getenv("ETIKET_DB", "nexora_etiket.db"))
        if g.get("n"):
            f = lambda v: "—" if v is None else f"%{v:+.2f}"
            k = g["kopya"]
            L.append(f"[12] YZ gölge karar ({g['gun']} gün, {g['n']} sinyal, {g['etiketli']} sonuçlandı, seçim oranı %{100 * g['secim_orani']:.0f}): "
                     f"seçtikleri {f(g['secili_ort'])}, seçmedikleri {f(g['secilmeyen_ort'])}, hepsi {f(g['hepsi_ort'])}")
            L.append(f"    kopyalananlarda: {k['etiketli']} sonuç, seçtikleri ({k['secilen']}) {f(k['secili_ort'])}, "
                     f"seçmedikleri {f(k['secilmeyen_ort'])}" + ("" if g["yeterli"] else " · karar için en az 14 gün ve 100 sonuç gerekli"))
        else:
            L.append("[12] YZ gölge karar: henüz kayıt yok (model kabul edilince başlar)")
    except Exception as ex:
        L.append(f"[12] YZ gölge karar hesaplanamadı: {type(ex).__name__}")

    try:                                   # 13-15) Giriş/çıkış deneyleri (dış araştırma, 20.11): çıkış, token yaşı, teyit bağımsızlığı
        from nexora import giris_cikis as GC
        L += GC.satirlar(GC.rapor(os.getenv("ETIKET_DB", "nexora_etiket.db"), now, 14), 14)
    except Exception as ex:
        L.append(f"[13] giriş/çıkış deneyleri hesaplanamadı: {type(ex).__name__}")
    try:                                   # 16) Hyperliquid gölge ölçümü (20.11): büyük trader'ları kopyalasaydık
        from nexora import hl
        L += hl.satirlar(hl.rapor(os.getenv("HL_DB", "nexora_hl.db"), now, 14))
    except Exception as ex:
        L.append(f"[16] Hyperliquid ölçümü hesaplanamadı: {type(ex).__name__}")

    # 6b) Kısmi satış ölçümü
    km = _q(p, "SELECT * FROM kismi_olcum WHERE acilis_ts>=?", (bas,))
    if km:
        kap = [x for x in km if x["status"] != "open"]
        sim, son = sum(x["simdi_usd"] or 0 for x in kap), sum(x["sonra_usd"] or 0 for x in kap)
        L.append(f"[6b] Kısmi satış (kaynak kadar satsaydık): {len(km)} ölçüm, {len(kap)} kapandı; kalan pay ilk satışta "
                 f"{sim:.2f}$, orantılı satışla {son:.2f}$ (fark {son - sim:+.2f}$)")

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


def gunluk_ozet(now=None, gun=1.0, paper_path=None):
    """Bildirim için kısa özet (son `gun` gün): alım, satış, gerçekleşen ve açık K/Z, reddedilen alımlar."""
    now = now or time.time(); bas = now - gun * 86400
    p = _ro(paper_path or os.getenv("NEXORA_DB", "nexora_paper.db"))
    try:
        tr = _q(p, "SELECT side, decision, reason, pnl FROM trades WHERE ts>=?", (bas,))
        poz = _q(p, "SELECT cost, qty, last_price FROM positions")
    finally:
        if p is not None: p.close()
    sat = [x["pnl"] or 0 for x in tr if x["side"] == "sell" and x["decision"] == "KOPYALANDI"]
    red = [x for x in tr if x["side"] == "buy" and x["decision"] != "KOPYALANDI"]
    acik = sum((x["qty"] or 0) * (x["last_price"] or 0) - (x["cost"] or 0) for x in poz)
    return dict(alim=sum(1 for x in tr if x["side"] == "buy" and x["decision"] == "KOPYALANDI"), satis=len(sat),
                kazanan=sum(1 for v in sat if v > 0), gerceklesen=round(sum(sat), 2), acik_poz=len(poz), acik_kz=round(acik, 2),
                red=len(red), red_slot=sum(1 for x in red if (x["reason"] or "").startswith(("maks. eşzamanlı", "toplam risk"))))


def ozet_metni(o):
    return (f"Son 24 saat: {o['alim']} alım, {o['satis']} satış ({o['kazanan']} kazanan), gerçekleşen K/Z {o['gerceklesen']:+.2f}$. "
            f"Açık {o['acik_poz']} pozisyon {o['acik_kz']:+.2f}$. Reddedilen alım {o['red']} (yer/risk sınırı: {o['red_slot']}).")


if __name__ == "__main__":
    print(rapor(GUN=float(sys.argv[1]) if len(sys.argv) > 1 else 3.0))

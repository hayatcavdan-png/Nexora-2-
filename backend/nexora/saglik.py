"""Sistem sağlığı ve 'canlı ölçümü tutuyor mu?' (uygulama 5.22.0). SALT OKUNUR.

durum():       servisler (systemd), kurulu sürüm, son keşif / yapay zekâ / takip / Hyperliquid zamanları.
olaylar():     servis durumu değişince bildirim (90 sn'den uzun süren kesinti; yeniden başlatma alarm üretmez).
tutarlilik():  bir başlangıç anından (varsayılan: 20.11 çıkış düzeltmesi) beri canlı paper defteri ile aynı dönemin
               deney masası yeniden oynatması (aynı kural: 8x%5, al-sat <= %3, kaynak çıkışı) yan yana."""
from .dosya import json_oku, metin_oku, bayt_oku
import json, os, sqlite3, subprocess, time

BIRIMLER = ("nexora-sunucu", "nexora-takip", "nexora-piyasa", "nexora-bnb", "nexora-base", "nexora-hl")
ZAMANLAYICI = ("nexora-kesif.timer", "nexora-yedek.timer", "nexora-bildirim.timer")
AD = {"nexora-sunucu": "Sunucu (uygulama)", "nexora-takip": "Solana takip", "nexora-piyasa": "Piyasa stratejileri",
      "nexora-bnb": "BNB takip", "nexora-base": "Base takip", "nexora-hl": "Hyperliquid ölçüm",
      "nexora-kesif.timer": "Gece keşfi (zamanlayıcı)", "nexora-yedek.timer": "Yedek (zamanlayıcı)",
      "nexora-bildirim.timer": "Bildirim (zamanlayıcı)"}
KESINTI_SN = 90
DUZELTME_TS = 1795182300          # 20.11.2026 13:45 UTC: pozisyonu yalnızca açan cüzdanın satışı kapatır
DURUM_DOSYA = "saglik_durum.json"


def _calistir(komut):
    try: return subprocess.run(komut, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError): return ""


def servisler(calistir=_calistir):
    """[dict(birim, ad, durum, yeniden_baslama, baslangic)]; systemd okunamazsa durum 'bilinmiyor'."""
    birimler = BIRIMLER + ZAMANLAYICI
    cikti = calistir(["systemctl", "show", *birimler, "-p", "Id", "-p", "ActiveState", "-p", "NRestarts", "-p", "ActiveEnterTimestamp"])
    bloklar, b = [], {}
    for satir in (cikti or "").splitlines():
        if not satir.strip():
            if b: bloklar.append(b); b = {}
            continue
        k, _, v = satir.partition("="); b[k.strip()] = v.strip()
    if b: bloklar.append(b)
    bul = {x.get("Id"): x for x in bloklar}
    out = []
    for u in birimler:
        x = bul.get(u) or {}
        out.append(dict(birim=u, ad=AD.get(u, u), durum=x.get("ActiveState") or "bilinmiyor",
                        yeniden_baslama=int(x["NRestarts"]) if (x.get("NRestarts") or "").isdigit() else None,
                        baslangic=x.get("ActiveEnterTimestamp") or None))
    return out


def surum(calistir=_calistir, kok=".."):
    try: kurulan = open(os.path.join(kok, ".kurulan")).read().strip()
    except OSError: kurulan = ""
    hedef = kurulan or "HEAD"
    s = (calistir(["git", "-C", kok, "log", "-1", "--format=%h|%ct|%s", hedef]) or "").strip()
    if "|" not in s: return dict(kurulan=kurulan[:7] or None, mesaj=None, ts=None)
    h, ts, m = s.split("|", 2)
    return dict(kurulan=h, ts=float(ts) if ts.isdigit() else None, mesaj=m[:120])


def _son_ts(db, sql):
    if not os.path.exists(db): return None
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try: r = c.execute(sql).fetchone()
        finally: c.close()
        return float(r[0]) if r and r[0] is not None else None
    except sqlite3.Error:
        return None


def zamanlar():
    k = {}
    try: k = json_oku("kesif_son.json")
    except (OSError, ValueError): pass
    yz = None
    try: yz = os.path.getmtime("yz_model.json")
    except OSError: pass
    hl = _son_ts(os.getenv("HL_DB", "nexora_hl.db"), "SELECT MAX(son_ms) / 1000.0 FROM hl_imlec")
    return dict(kesif=k.get("ts"), kesif_durum=k.get("durum"), yz_sonuc=k.get("yz"), yz_model_dosya=yz,
                son_sinyal=_son_ts(os.getenv("TRACKER_DB", "nexora_tracker.db"), "SELECT MAX(ts) FROM tracker_signals"),
                son_etiket=_son_ts(os.getenv("ETIKET_DB", "nexora_etiket.db"), "SELECT MAX(ts) FROM etiket_olay"),
                hl_son=hl)


def durum(paper=None, calistir=_calistir, now=None):
    now = now or time.time()
    d = dict(ts=now, servisler=servisler(calistir), surum=surum(calistir), zamanlar=zamanlar())
    if paper is not None:
        try:
            eq, ds = paper.equity(), float(paper._get("day_start") or 0)
            lim = paper.limit("daily_loss_pct")
            kayip = (ds - eq) / ds if ds > 0 else 0.0
            d["paper"] = dict(ozkaynak=round(eq, 2), gun_basi=round(ds, 2), gunluk_kayip_pct=round(100 * kayip, 2),
                              limit_pct=round(100 * lim, 2), limit_doldu=kayip >= lim, acil_durdurma=paper.killed(),
                              acik_poz=len(paper.portfolio()["positions"]))
        except Exception as e:
            d["paper"] = dict(hata=f"{type(e).__name__}")
    d["sorun"] = sum(1 for s in d["servisler"] if s["durum"] not in ("active", "bilinmiyor"))
    return d


def olaylar(son, now=None, calistir=_calistir, yol=DURUM_DOSYA):
    """Servis durumu geçişleri. Kesinti KESINTI_SN'den uzun sürerse 'durdu', sonra düzelirse 'yeniden çalışıyor'."""
    now = now or time.time()
    try: kayit = json_oku(yol)
    except (OSError, ValueError): kayit = {}
    ilk = not kayit; out = []
    for s in servisler(calistir):
        if s["durum"] == "bilinmiyor": continue
        u, aktif = s["birim"], s["durum"] == "active"
        k = kayit.get(u)
        if k is None or k["aktif"] != aktif:
            kayit[u] = k = dict(aktif=aktif, ts=now, onceki_uyarildi=bool(k and k.get("uyarildi")), uyarildi=False)
        if ilk: continue
        if not aktif and now - k["ts"] >= KESINTI_SN:
            t = k["ts"] + KESINTI_SN; k["uyarildi"] = True
            if t > son:
                out.append(dict(id=f"s{u}{int(k['ts'])}", ts=t, tur="risk", baslik=f"Servis durdu: {AD.get(u, u)}",
                                metin=f"{u} {int((now - k['ts']) // 60)} dakikadır çalışmıyor (durum: {s['durum']}). "
                                      f"Sunucuda: sudo systemctl restart {u}"))
        elif aktif and k.get("onceki_uyarildi") and k["ts"] > son:
            out.append(dict(id=f"r{u}{int(k['ts'])}", ts=k["ts"], tur="bilgi", baslik=f"Servis yeniden çalışıyor: {AD.get(u, u)}",
                            metin=f"{u} tekrar aktif."))
    if not kayit: return out                  # systemd okunamadı (geliştirme ortamı): dosya yazılmaz
    try:
        with open(yol + ".tmp", "w") as f: json.dump(kayit, f)
        os.replace(yol + ".tmp", yol)
    except OSError:
        pass
    return out


def tutarlilik(paper_db=None, etiket_db=None, bas=DUZELTME_TS, now=None, golge=None):
    """Başlangıçtan beri canlı defter ile deney masası (aynı kural, aynı dönem). Yüzdeler 100 $'a göre."""
    from nexora import deney as D
    now = now or time.time()
    paper_db = paper_db or os.getenv("NEXORA_DB", "nexora_paper.db"); etiket_db = etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db")
    canli = dict(alim=0, satis=0, kazanan=0, gerceklesen=0.0, acik=0, acik_kz=0.0, ozkaynak=None, gunluk=[], baska_satici=0)
    if os.path.exists(paper_db):
        c = sqlite3.connect(f"file:{paper_db}?mode=ro", uri=True, timeout=10); c.row_factory = sqlite3.Row
        try:
            tr = [dict(r) for r in c.execute("SELECT ts, side, pnl, decision, reason FROM trades WHERE ts>=? ORDER BY ts", (bas,))]
            poz = [dict(r) for r in c.execute("SELECT cost, qty, last_price FROM positions")]
            st = {r["k"]: r["v"] for r in c.execute("SELECT k, v FROM state")}
        finally:
            c.close()
        sat = [t for t in tr if t["side"] == "sell" and t["decision"] == "KOPYALANDI"]
        gun = {}
        for t in sat: g = time.strftime("%Y-%m-%d", time.gmtime(t["ts"])); gun[g] = gun.get(g, 0.0) + (t["pnl"] or 0)
        acik_kz = sum((p["qty"] or 0) * (p["last_price"] or 0) - (p["cost"] or 0) for p in poz)
        oz = float(st.get("cash") or 0) + sum((p["qty"] or 0) * (p["last_price"] or 0) for p in poz)
        canli.update(alim=sum(1 for t in tr if t["side"] == "buy" and t["decision"] == "KOPYALANDI"), satis=len(sat),
                     kazanan=sum(1 for t in sat if (t["pnl"] or 0) > 0), gerceklesen=round(sum(t["pnl"] or 0 for t in sat), 2),
                     acik=len(poz), acik_kz=round(acik_kz, 2), ozkaynak=round(oz, 2),
                     gunluk=[dict(gun=g, kz=round(v, 2)) for g, v in sorted(gun.items())],
                     baska_satici=sum(1 for t in tr if t["reason"] == "satan cüzdan pozisyonu açan değil"),
                     limit_red=sum(1 for t in tr if t["reason"] == "günlük zarar limiti"))
    bas_oz = (canli["ozkaynak"] or 0) - canli["gerceklesen"] - canli["acik_kz"]
    canli["toplam_pct"] = round(100 * (canli["gerceklesen"] + canli["acik_kz"]) / bas_oz, 2) if bas_oz > 0 else None
    golge = D.golge_seti() if golge is None else set(golge)
    s = [x for x in D.sinyaller(etiket_db, now, gun=max(1.0, (now - bas) / 86400 + 1)) if x[0] >= bas and x[2] not in golge]
    deney = dict(sinyal=len(s), **D.simule(s, **D.MODEL_AYAR, gunluk_zarar=0.03, token_gunluk=2))   # canlıdaki sınırlarla
    deney["toplam_pct"] = deney["kz"]                       # simülasyon 100 $ ile başlar: K/Z = yüzde
    fark = None if canli["toplam_pct"] is None else round(canli["toplam_pct"] - deney["toplam_pct"], 2)
    gun = (now - bas) / 86400
    es = eslesme(paper_db, etiket_db, bas)
    if es["n"] >= 10:                          # asıl ölçüt: AYNI sinyallerde canlı sonuç ile ölçülen sonuç
        f = es["fark_medyan"]
        if abs(f) <= 2.0: yorum = f"Aynı {es['n']} işlemde canlı, ölçümü tutuyor (medyan fark %{f:+.1f})."
        elif f < 0: yorum = f"Aynı {es['n']} işlemde canlı ölçümün GERİSİNDE (medyan %{f:+.1f}): yürütme (kayma, gecikme, ücret) incelenmeli."
        else: yorum = f"Aynı {es['n']} işlemde canlı ölçümün önünde (medyan %{f:+.1f}); örneklem büyüdükçe izlenecek."
    elif canli["satis"] < 10 or deney["islem"] < 10: yorum = "Henüz erken: iki tarafta da en az 10 kapanan işlem gerekiyor."
    elif fark is not None and abs(fark) <= max(2.0, abs(deney["toplam_pct"]) * 0.5): yorum = "Canlı defter ölçümü tutuyor."
    elif fark is not None and fark < 0: yorum = "Canlı defter ölçümün GERİSİNDE: farkın nedeni incelenmeli (red nedenleri, gecikme, limit)."
    else: yorum = "Canlı defter ölçümün önünde (şans olabilir; örneklem büyüdükçe izlenecek)."
    return dict(bas=bas, gun=round(gun, 1), canli=canli, deney=deney, fark_pct=fark, yorum=yorum, eslesme=es)


def eslesme(paper_db, etiket_db, bas):
    """Aynı sinyal, iki sonuç (21.11): canlıda kapanan her pozisyonun getirisi (K/Z / maliyet) ile o pozisyonu açan sinyalin
    etiket motorundaki 'kaynak' getirisi. Deney masası yalnızca etiketlenmiş alt kümeyi oynatabildiği için (günde 400 sınırı,
    24 sa sonuç) portföy karşılaştırması ilk günlerde yanıltıcıdır; bu eşleştirme doğrudan yürütme farkını ölçer."""
    out = dict(n=0, canli_ort=None, olculen_ort=None, fark_ort=None, fark_medyan=None, etiketsiz=0, alim=0, etiketli_alim=0, eksiksizlik=None)
    if not (os.path.exists(paper_db) and os.path.exists(etiket_db)): return out
    p = sqlite3.connect(f"file:{paper_db}?mode=ro", uri=True, timeout=10); e = sqlite3.connect(f"file:{etiket_db}?mode=ro", uri=True, timeout=10)
    try:
        # N16 eksiksizlik: kopyalanan alımların kaçı etiket motorunda kayıtlı (hedef ≥ %90)
        alim = [r[0] for r in p.execute("SELECT event_id FROM trades WHERE side='buy' AND decision='KOPYALANDI' AND ts>=?", (bas,))]
        etk = sum(1 for ev in alim if e.execute("SELECT 1 FROM etiket_olay WHERE event_id=?", (ev,)).fetchone())
        out.update(alim=len(alim), etiketli_alim=etk, eksiksizlik=round(100 * etk / len(alim)) if alim else None)
        ciftler = []
        for tok, w, ac, cost, pnl in p.execute("""SELECT token, wallet, opened_ts, cost, pnl FROM pos_iz WHERE status='closed' AND tam=1
                                                  AND closed_ts>=? AND cost>0 AND pnl IS NOT NULL""", (bas,)):
            b = p.execute("""SELECT event_id FROM trades WHERE token=? AND wallet=? AND side='buy' AND decision='KOPYALANDI'
                             AND ABS(ts-?)<10 ORDER BY ABS(ts-?) LIMIT 1""", (tok, w, ac, ac)).fetchone()
            if not b: continue
            g = e.execute("SELECT getiri_pct FROM etiket_sonuc WHERE event_id=? AND ufuk='kaynak' AND getiri_pct IS NOT NULL", (b[0],)).fetchone()
            if g is None: out["etiketsiz"] += 1; continue
            ciftler.append((100 * pnl / cost, float(g[0])))
    except sqlite3.Error:
        return out
    finally:
        p.close(); e.close()
    if not ciftler: return out
    fk = sorted(c - o for c, o in ciftler); n = len(ciftler)
    out.update(n=n, canli_ort=round(sum(c for c, _ in ciftler) / n, 2), olculen_ort=round(sum(o for _, o in ciftler) / n, 2),
               fark_ort=round(sum(fk) / n, 2), fark_medyan=round(fk[n // 2] if n % 2 else (fk[n // 2 - 1] + fk[n // 2]) / 2, 2))
    return out

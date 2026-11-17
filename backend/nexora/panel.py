"""Uygulama paneli için salt okunur veri (N14). Ağ isteği yapmaz; yerel dosya ve veritabanlarını okur."""
import csv, json, os, sqlite3, time

from nexora.core import CFG
from nexora.rapor import build_report


from nexora.core import kararlilik_hesapla

def _ro(path):
    if not path or not os.path.exists(path): return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _rows(conn, sql, args=()):
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    except sqlite3.OperationalError:
        return []


def _read_list(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]


def gecmis(paper_path, now=None):
    """Portföy değer eğrisi. Her kopyalanan işlemden sonra gerçekleşen değer; son nokta, açık
    pozisyonların son değerlemesiyle güncel toplam değer. Alımda ödenen ağ ücreti de düşülür."""
    now = now if now is not None else time.time()
    start = CFG["start_cash"]
    c = _ro(paper_path)
    if c is None:
        return dict(baslangic=start, noktalar=[dict(ts=now, deger=start)], guncel=start)
    try:
        trades = _rows(c, "SELECT ts, side, pnl, fee FROM trades WHERE decision='KOPYALANDI' ORDER BY id")
        state = {r["k"]: r["v"] for r in _rows(c, "SELECT k, v FROM state")}
        pos_value = sum((r["qty"] or 0) * (r["last_price"] or 0) for r in _rows(c, "SELECT qty, last_price FROM positions"))
    finally:
        c.close()
    value, pts = start, []
    if trades: pts.append(dict(ts=trades[0]["ts"] - 1, deger=round(start, 4)))
    for t in trades:
        if t["side"] == "buy": value -= t["fee"] or 0
        else: value += t["pnl"] or 0
        pts.append(dict(ts=t["ts"], deger=round(value, 4)))
    guncel = float(state.get("cash", start) or start) + pos_value
    pts.append(dict(ts=now, deger=round(guncel, 4)))
    return dict(baslangic=start, noktalar=pts, guncel=round(guncel, 4), **dusus(pts, start))


def dusus(pts, start):
    """En büyük düşüş: değer eğrisinde bir zirveden sonraki en derin dip (% ve USDC). Eğri yalnızca işlem anlarında
    ve şu anda örneklendiği için gün içi açık pozisyon dalgalanmasını tam göstermez (alt sınır gibi okunmalı)."""
    zirve, en_kotu, en_kotu_usd = start, 0.0, 0.0
    for p in pts:
        zirve = max(zirve, p["deger"])
        if zirve > 0:
            d = (zirve - p["deger"]) / zirve * 100
            if d > en_kotu: en_kotu, en_kotu_usd = d, zirve - p["deger"]
    son = pts[-1]["deger"] if pts else start
    zirve_son = max([start] + [p["deger"] for p in pts])
    return dict(max_dusus_pct=round(en_kotu, 2), max_dusus_usd=round(en_kotu_usd, 4),
                zirveden_uzaklik_pct=round((zirve_son - son) / zirve_son * 100, 2) if zirve_son > 0 else 0.0)


def cuzdanlar(paper_path, tracker_path, analiz_csv="cuzdan_analiz.csv", tarama_csv="cuzdan_tarama.csv",
              kayip_json="takip_kaybi.json", gecmis_db=None):
    """Takip edilen ve analiz edilen cüzdanlar: analiz metrikleri + takip durumu + paper performansı."""
    tracked = [w for w in _read_list("wallets.txt") if w not in set(_read_list("kara_liste.txt"))]
    black = _read_list("kara_liste.txt")
    analiz = {}
    if os.path.exists(analiz_csv):
        for r in csv.DictReader(open(analiz_csv, newline="")): analiz[r["wallet"]] = r
    taranan = sum(1 for _ in csv.DictReader(open(tarama_csv, newline=""))) if os.path.exists(tarama_csv) else 0

    status = {}
    tc = _ro(tracker_path)
    if tc is not None:
        try:
            for r in _rows(tc, "SELECT wallet, quarantined, last_error FROM tracker_wallets"):
                status[r["wallet"]] = r
        finally:
            tc.close()
    perf = {r["wallet"]: r for r in build_report(paper_path, None).get("cuzdanlar", [])}
    kayip = {}
    if os.path.exists(kayip_json):
        try:
            for w in json.load(open(kayip_json, encoding="utf-8")).get("cuzdanlar", []): kayip[w["cuzdan"]] = w
        except (ValueError, KeyError, OSError):
            kayip = {}

    def num(r, k, cast=float):
        try: return cast(r.get(k)) if r and r.get(k) not in (None, "") else None
        except ValueError: return None

    out = []
    from nexora import analiz_gecmis
    gecmis_db = gecmis_db or os.getenv("DNA_DB", "nexora_dna.db")
    for w in dict.fromkeys(tracked + [w for w, r in analiz.items() if r.get("karar") == "kopyalanabilir"]):
        a, s, p, k = analiz.get(w), status.get(w), perf.get(w, {}), kayip.get(w, {})
        try: eg = analiz_gecmis.ozet(gecmis_db, [w])[0] if os.path.exists(gecmis_db) else {}
        except Exception: eg = {}
        q = (s or {}).get("quarantined") or 0
        out.append(dict(
            wallet=w, takipte=w in tracked,
            durum="bot" if q == 2 else "karantina" if q == 1 else ("aktif" if w in tracked else "takip dışı"),
            karar=(a or {}).get("karar", "analiz yok"),
            kazanma_orani=num(a, "kazanma_orani"), kar_faktoru=num(a, "kar_faktoru"),
            kaynak_kz=num(a, "gerceklesen_usd"), ort_getiri=num(a, "ort_getiri"),
            medyan_tutma_sn=num(a, "medyan_tutma_sn", lambda v: int(float(v))),
            kapanan_kaynak=num(a, "kapanan", lambda v: int(float(v))),
            skor=num(a, "skor") or 0.0,
            max_dusus_usd=num(a, "max_dusus_usd"), dusus_kazanc_orani=num(a, "dusus_kazanc_orani"),
            kalite_puani=num(a, "kalite_puani", lambda v: int(float(v))), gerekce=(a or {}).get("gerekce") or "",
            medyan_getiri=num(a, "medyan_getiri"), son_yari_getiri=num(a, "son_yari_getiri"), en_iyi_haric_usd=num(a, "en_iyi_haric_usd"),
            egilim=eg.get("egilim"), analiz_goruntu=eg.get("goruntu", 0), analiz_ts=eg.get("son_ts"),
            paper_sinyal=p.get("sinyal", 0), paper_kopyalanan=p.get("kopyalanan", 0),
            paper_kapanan=p.get("kapanan", 0), paper_kz=p.get("gerceklesen_kz", 0.0), paper_acik=p.get("acik", 0),
            takip_tur=k.get("islem", 0), takip_giris=k.get("giris_kaybi_ort"), takip_cikis=k.get("cikis_kaybi_ort"),
            takip_kaynak=k.get("kaynak_getiri_ort"), takip_bizim=k.get("bizim_getiri_ort")))
    out.sort(key=lambda r: (not r["takipte"], -(r["skor"] or 0)))
    kararlar = {}
    for r in analiz.values(): kararlar[r.get("karar", "?")] = kararlar.get(r.get("karar", "?"), 0) + 1
    return dict(ozet=dict(taranan=taranan, analiz=len(analiz), kopyalanabilir=kararlar.get("kopyalanabilir", 0),
                          takipte=len(tracked), kara_liste=len(black), kararlar=kararlar),
                cuzdanlar=out)


def asamalar(path="asamalar.json"):
    if not os.path.exists(path): return dict(rows=[], guncelleme=None)
    d = json.load(open(path, encoding="utf-8"))
    meta = (d.get("meta") or [{}])[0].get("value")
    return dict(rows=d.get("rows", []), guncelleme=meta)


NABIZ_SURE = 300      # takip bu kadar saniye kalp atışı yazmazsa "durdu" sayılır

def kesif_olayi(path, son):
    """Günlük otomatik keşfin sonucu (kesif_son.json): yeni kopyalanabilir cüzdan ya da hata varsa bir olay."""
    try:
        with open(path) as f: k = json.load(f)
    except (OSError, ValueError):
        return None
    ts = float(k.get("ts") or 0)
    if ts <= son: return None
    if k.get("durum") == "hata":
        return dict(id=f"x{int(ts)}", ts=ts, tur="risk", baslik="Otomatik keşif başarısız", metin=k.get("hata") or "bilinmeyen hata")
    kd = k.get("kadro") or {}
    if kd.get("degisti"):                        # kadro listeyi değiştirdi: en önemli olay bu
        kisa = lambda ws: ", ".join(w[:4] + "…" + w[-4:] for w in ws[:3])
        parca = []
        if kd.get("terfi"): parca.append(f"{len(kd['terfi'])} cüzdan kopyalamaya geçti ({kisa(kd['terfi'])})")
        if kd.get("dusur"): parca.append(f"{len(kd['dusur'])} cüzdan izlemeye düştü ({kisa(kd['dusur'])})")
        if kd.get("cikar"): parca.append(f"{len(kd['cikar'])} cüzdan listeden çıktı")
        if kd.get("eklenen"): parca.append(f"{len(kd['eklenen'])} yeni cüzdan izlemeye alındı")
        return dict(id=f"x{int(ts)}", ts=ts, tur="kesif", baslik=f"Kadro güncellendi: {kd.get('kopyalanan', 0)} kopyalanan, "
                    f"{kd.get('izlenen', 0)} izlenen cüzdan", metin="; ".join(parca) + ". Karar, sinyallerin gerçek tekliflerle "
                    "ölçülen sonucuna göre verildi (paper).")
    yeni = k.get("kopyalanabilir") or []
    evm_yeni = {z: v.get("eklenen") or [] for z, v in (k.get("evm") or {}).items() if v.get("eklenen")}
    if not yeni and evm_yeni:                    # yalnız EVM ekosistemlerine paper cüzdan eklendi
        adlar = {"bnb": "BNB Chain", "base": "Base"}
        satir = "; ".join(f"{adlar.get(z, z)}: {len(w)} cüzdan ({', '.join(x[:6] + '…' + x[-4:] for x in w)})" for z, w in evm_yeni.items())
        return dict(id=f"x{int(ts)}", ts=ts, tur="kesif", baslik=f"Keşif: {sum(len(w) for w in evm_yeni.values())} yeni EVM cüzdanı paper takipte",
                    metin=satir + ". Yalnızca kârlılık analizinden 'kopyalanabilir' çıkanlar eklenir.")
    bozuk = [b for b in (k.get("takip") or {}).get("bozulan") or [] if b.get("yeni")]
    if not yeni and bozuk:                       # takipteki bir cüzdan yeni eşik altına düştü
        satir = "; ".join(f"{b['wallet'][:4]}…{b['wallet'][-4:]} {b.get('karar')}: {b.get('gerekce')}" for b in bozuk[:3])
        return dict(id=f"x{int(ts)}", ts=ts, tur="risk", baslik=f"Takipteki {len(bozuk)} cüzdan eşik altına düştü",
                    metin=satir + ". Listeden çıkarmak sizin kararınız (wallets.txt).")
    if not yeni: return None
    satir = "; ".join(f"{c['wallet'][:4]}…{c['wallet'][-4:]} K/Z {c['gerceklesen_usd']:+.0f}$ kazanma %{100 * c['kazanma_orani']:.0f}"
                      for c in yeni[:3])
    return dict(id=f"x{int(ts)}", ts=ts, tur="kesif", baslik=f"Keşif: {len(yeni)} yeni kopyalanabilir cüzdan",
                metin=f"{satir}. Eklemek için sunucuda: sudo bash /opt/nexora/deploy/calistir.sh cuzdan_ekle.py --uygula")


OZET_SAAT_UTC = 6     # günlük özet her gün 06:00 UTC'de (09:00 İstanbul) bir kez


def olaylar(paper_path, tracker_path, son=0.0, limit=20, now=None, kesif_path=None, ozet=False):
    """Bildirim olayları (ts > son): kopyalanan alım, kapanan pozisyon, günlük zarar sınırı, bot işareti.
    Uygulama son gördüğü ts'yi saklar ve yalnızca yenileri ister."""
    now = now if now is not None else time.time()
    out = []
    c = _ro(paper_path)
    if c is not None:
        try:
            nb = {r["k"]: r["v"] for r in _rows(c, "SELECT k, v FROM state WHERE k='takip_nabiz'")}.get("takip_nabiz")
            if nb:
                t = float(nb) + NABIZ_SURE
                if t <= now and t > son:
                    out.append(dict(id=f"n{int(float(nb))}", ts=t, tur="risk", baslik="Takip durdu",
                                    metin="Canlı takip 5 dakikadır çalışmıyor. Termux'ta: ./nexora durum"))
            for g in _rows(c, "SELECT id, token, ts, neden FROM durum_gecis WHERE yeni='TAKILDI' AND ts > ?", (son,)):
                tok = (g["token"] or "")[:4] + "…" + (g["token"] or "")[-4:]
                out.append(dict(id=f"d{g['id']}", ts=g["ts"], tur="risk", baslik=f"Pozisyon satılamıyor: {tok}",
                                metin=f"{g['neden']}. Teklif yeniden alınınca pozisyon otomatik olarak açık duruma döner."))
            gunler = set()
            for t in _rows(c, "SELECT id, ts, side, token, wallet, pnl, decision, reason FROM trades WHERE ts > ? ORDER BY ts", (son,)):
                tok = (t["token"] or "")[:4] + "…" + (t["token"] or "")[-4:]
                cuz = (t["wallet"] or "")[:4] + "…" + (t["wallet"] or "")[-4:]
                if t["decision"] == "KOPYALANDI" and t["side"] == "buy":
                    out.append(dict(id=f"t{t['id']}", ts=t["ts"], tur="alim", baslik=f"Alım kopyalandı: {tok}",
                                    metin=f"Kaynak {cuz} · {t['reason']}"))
                elif t["decision"] == "KOPYALANDI" and t["side"] == "sell":
                    kz = t["pnl"] or 0.0
                    out.append(dict(id=f"t{t['id']}", ts=t["ts"], tur="kapanis",
                                    baslik=f"Pozisyon kapandı: {tok} {'+' if kz >= 0 else ''}{kz:.2f} USDC",
                                    metin=f"Kaynak {cuz} sattı"))
                elif t["decision"] == "REDDEDİLDİ" and t["reason"] == "günlük zarar limiti":
                    gun = time.strftime("%Y-%m-%d", time.localtime(t["ts"]))
                    once = _rows(c, "SELECT 1 FROM trades WHERE reason='günlük zarar limiti' AND ts < ? AND ts >= ? LIMIT 1",
                                 (t["ts"], time.mktime(time.strptime(gun, "%Y-%m-%d"))))
                    if not once and gun not in gunler:
                        gunler.add(gun)
                        out.append(dict(id=f"z{gun}", ts=t["ts"], tur="risk", baslik="Günlük zarar sınırı devrede",
                                        metin="Yeni alımlar gün sonuna kadar durduruldu."))
        finally:
            c.close()
    tc = _ro(tracker_path)
    if tc is not None:
        try:
            for r in _rows(tc, """SELECT id, sig, wallet, token, side, kesinlik, kesinlik_ts FROM tracker_signals
                    WHERE kesinlik IN ('hatali','dusuruldu') AND decision='KOPYALANDI' AND kesinlik_ts > ?""", (son,)):
                tok = (r["token"] or "")[:4] + "…" + (r["token"] or "")[-4:]
                out.append(dict(id=f"k{r['id']}", ts=r["kesinlik_ts"], tur="risk",
                                baslik=f"Kopyalanan sinyal {'başarısız' if r['kesinlik'] == 'hatali' else 'kesinleşmedi'}: {tok}",
                                metin="Kaynak işlem zincirde " + ("başarısız oldu" if r["kesinlik"] == "hatali" else
                                      "kesinleşmedi (çatallanma)") + "; paper kayıt korunur, rapora işlendi."))
            for r in _rows(tc, "SELECT wallet, updated, last_error FROM tracker_wallets WHERE quarantined=2 AND updated > ?", (son,)):
                cuz = r["wallet"][:4] + "…" + r["wallet"][-4:]
                out.append(dict(id=f"b{r['wallet']}", ts=r["updated"], tur="bot", baslik=f"Cüzdan durduruldu: {cuz}",
                                metin=r["last_error"] or "yüksek frekans (bot olabilir)"))
        finally:
            tc.close()
    ke = kesif_olayi(kesif_path, son) if kesif_path else None
    if ke: out.append(ke)
    if ozet:                                   # günlük özet: bugünün özet anı geçtiyse ve uygulama henüz görmediyse
        an = now - now % 86400 + OZET_SAAT_UTC * 3600
        if an > now: an -= 86400
        if an > son:
            try:
                from nexora import teshis
                o = teshis.gunluk_ozet(an, 1.0, paper_path)
                out.append(dict(id=f"g{int(an)}", ts=an, tur="ozet",
                                baslik=f"Günlük özet: gerçekleşen {o['gerceklesen']:+.2f}$, açık {o['acik_kz']:+.2f}$",
                                metin=teshis.ozet_metni(o) + " Ayrıntı: Günlük Rapor › Strateji teşhisi."))
            except Exception:
                pass
    out.sort(key=lambda e: e["ts"])
    return dict(olaylar=out[:limit], simdi=now)


SUNUCU_BASLANGIC = time.time()


def saglik(paper_path, tracker_path, yedek_dizin="yedekler", now=None):
    """Sistem sağlığı (N6): takip süreci, WebSocket, son sinyal, disk, veritabanı boyutu ve son yedek."""
    import glob, shutil
    now = now if now is not None else time.time()
    st, takip = {}, None
    c = _ro(paper_path)
    kararlilik = None
    if c is not None:
        try:
            st = {r["k"]: r["v"] for r in _rows(c, "SELECT k, v FROM state WHERE k IN ('takip_nabiz','takip_saglik','izleme_bas')")}
            izn = _rows(c, "SELECT COUNT(*) n FROM karar_izi")
            kes = _rows(c, "SELECT bas, bit, sure_sn FROM kesinti ORDER BY bas")
            kararlilik = kararlilik_hesapla(st.get("izleme_bas"), st.get("takip_nabiz"), kes, now)
        finally:
            c.close()
    else:
        izn = []
    try: takip = json.loads(st["takip_saglik"]) if st.get("takip_saglik") else None
    except ValueError: takip = None
    nabiz = float(st["takip_nabiz"]) if st.get("takip_nabiz") else None
    son_sinyal = None
    tc = _ro(tracker_path)
    if tc is not None:
        try:
            r = _rows(tc, "SELECT MAX(ts) t FROM tracker_signals")
            son_sinyal = r[0]["t"] if r else None
        finally:
            tc.close()
    yed = sorted(glob.glob(os.path.join(yedek_dizin, "nexora_*.tar.gz")))
    try:
        du = shutil.disk_usage(os.path.dirname(os.path.abspath(paper_path)) or ".")
        disk = dict(bos_gb=round(du.free / 1e9, 1), dolu_pct=round(du.used / du.total * 100, 1))
    except OSError:
        disk = None
    boyut = lambda f: round(os.path.getsize(f) / 1e6, 2) if f and os.path.exists(f) else None
    takip_durum = "yok" if nabiz is None else ("çalışıyor" if now - nabiz < NABIZ_SURE else "durdu")
    return dict(
        sunucu_calisma_sn=round(now - SUNUCU_BASLANGIC),
        takip=takip_durum, takip_nabiz_once_sn=None if nabiz is None else round(now - nabiz),
        takip_calisma_sn=round(now - takip["baslangic"]) if takip and takip.get("baslangic") else None,
        ws=(takip or {}).get("ws"), ws_kopma=(takip or {}).get("ws_kopma"),
        ws_son_mesaj_once_sn=round(now - takip["ws_son_mesaj"]) if takip and takip.get("ws_son_mesaj") else None,
        okunamayan=(takip or {}).get("okunamayan"), cuzdan=(takip or {}).get("cuzdan"), bot=(takip or {}).get("bot"),
        son_sinyal_once_sn=round(now - son_sinyal) if son_sinyal else None,
        karar_izi=izn[0]["n"] if izn else 0, kararlilik=kararlilik,
        disk=disk, paper_db_mb=boyut(paper_path), takip_db_mb=boyut(tracker_path),
        son_yedek=os.path.basename(yed[-1]) if yed else None,
        son_yedek_once_sn=round(now - os.path.getmtime(yed[-1])) if yed else None,
    )

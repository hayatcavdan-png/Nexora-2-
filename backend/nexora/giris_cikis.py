"""Giriş/çıkış deneyleri (salt okunur ölçüm; işlem kuralını DEĞİŞTİRMEZ). 20.11.2026, dış araştırma bulgularına göre:

  A) Çıkış: kaynak satınca çıkmak mı, kendi zaman çıkışımız mı (5 dk / 30 dk / 'kaynak ya da 30 dk, hangisi önce')?
     Aynı sinyaller, aynı kural (8x%5, al-sat <= %3), yalnızca çıkış değişir. Sonuçlar gerçek Jupiter teklifinden (etiket).
  B) Token yaşı: sinyal anında token kaç saniyelik? İlk dakikalardaki alımlar (sniper/insider bölgesi) ayrı ölçülür.
     Cüzdan profili: cüzdanın alımlarındaki medyan token yaşı (hızlı giren cüzdanlar kopyalanabilir mi?).
  C) Teyit bağımsızlığı: aynı token'ı 15 dk içinde başka bir cüzdan da aldıysa, ikinci alım AYNI BLOKTA mı (aynı kişinin
     cüzdanları / bundle olabilir) yoksa farklı zamanda mı (bağımsız teyit)?
Gölge havuz sinyalleri A'da dışarıda tutulur (canlıda kopyalanabilecek olanlar); B ve C tüm ölçülmüş sinyalleri kullanır."""
import os, sqlite3, time
from collections import defaultdict
from statistics import median

from nexora import deney as D

YAS_DILIM = ((0, 60, "< 1 dk"), (60, 600, "1–10 dk"), (600, 3600, "10–60 dk"), (3600, 86400, "1–24 sa"), (86400, None, "> 1 gün"))
TEYIT_SN = 900
AYNI_BLOK_SN = 1.0


def _oku(etiket_db, now, gun):
    """{event_id: dict(ts, wallet, token, rt, yas, blok, sonuc={ufuk: (ts, getiri)})} — son 'gun' gün."""
    if not etiket_db or not os.path.exists(etiket_db): return {}
    c = sqlite3.connect(f"file:{etiket_db}?mode=ro", uri=True, timeout=10)
    out = {}
    try:
        for e, ts, w, t, rt, yas, bt in c.execute("""SELECT event_id, ts, wallet, token, al_sat_kaybi_pct, tb_yas_sn, block_time
                                                     FROM etiket_olay WHERE ts >= ?""", (now - gun * 86400,)):
            out[e] = dict(ts=ts, wallet=w, token=t, rt=rt, yas=yas, blok=bt, sonuc={})
        for e, u, ts, g in c.execute("SELECT event_id, ufuk, ts, getiri_pct FROM etiket_sonuc WHERE getiri_pct IS NOT NULL"):
            if e in out: out[e]["sonuc"][u] = (ts, float(g))
    except sqlite3.OperationalError:
        return {}
    finally:
        c.close()
    return out


def _ozet(g):
    if not g: return dict(n=0, ort=None, medyan=None, pozitif=None)
    return dict(n=len(g), ort=round(sum(g) / len(g), 2), medyan=round(median(g), 2), pozitif=round(100 * sum(v > 0 for v in g) / len(g)))


def cikis_deneyi(olay, golge=frozenset(), kural=None):
    """A) Yalnızca kaynak VE 30dk sonucu olan sinyaller (adil karşılaştırma). Dönüş: [dict(ad, n, islem, kz, kazanan, dusus)]."""
    kural = kural or dict(max_poz=8, oran=0.05, rt_max=3.0)
    ortak = sorted((o for o in olay.values() if o["wallet"] not in golge and "kaynak" in o["sonuc"] and "30dk" in o["sonuc"]),
                   key=lambda o: o["ts"])
    def sinyal(sec):
        out = []
        for o in ortak:
            r = sec(o)
            if r is None: continue
            ts, g = r; out.append((o["ts"], max(o["ts"], ts), o["wallet"], o["token"], g, o["rt"]))
        return out
    def once(o):                               # kaynak 30 dk içinde sattıysa kaynakla, yoksa 30. dakikada çık
        k = o["sonuc"]["kaynak"]
        return k if k[0] <= o["ts"] + 1800 + 60 else o["sonuc"]["30dk"]
    secenek = [("Kaynak satınca (şimdiki)", lambda o: o["sonuc"]["kaynak"]),
               ("30 dk sonra çık", lambda o: o["sonuc"]["30dk"]),
               ("5 dk sonra çık", lambda o: o["sonuc"].get("5dk")),
               ("Kaynak ya da 30 dk, hangisi önce", once)]
    sonuc = []
    for ad, sec in secenek:
        s = sinyal(sec)
        sonuc.append(dict(ad=ad, n=len(s), **D.simule(s, **kural)))
    return sonuc


def _dilim(yas):
    for a, b, ad in YAS_DILIM:
        if yas >= a and (b is None or yas < b): return ad
    return None


def yas_deneyi(olay):
    """B) Token yaşına göre kaynak-çıkış getirisi ve cüzdan profili (medyan giriş yaşı)."""
    d = defaultdict(list); cuz = defaultdict(list); bilinen = 0
    for o in olay.values():
        k = o["sonuc"].get("kaynak")
        if k is None: continue
        if o["yas"] is None or o["yas"] < 0: continue
        bilinen += 1; d[_dilim(o["yas"])].append(k[1]); cuz[o["wallet"]].append((o["yas"], k[1]))
    dilimler = [dict(ad=ad, **_ozet(d.get(ad, []))) for *_, ad in YAS_DILIM]
    profil = defaultdict(list)                 # cüzdanın medyan giriş yaşı dilimi -> o cüzdanların tüm getirileri
    for w, v in cuz.items():
        if len(v) < 3: continue
        profil[_dilim(median(y for y, _ in v))].extend(g for _, g in v)
    profiller = [dict(ad=ad, cuzdan=sum(1 for w, v in cuz.items() if len(v) >= 3 and _dilim(median(y for y, _ in v)) == ad),
                      **_ozet(profil.get(ad, []))) for *_, ad in YAS_DILIM]
    toplam = sum(1 for o in olay.values() if "kaynak" in o["sonuc"])
    return dict(bilinen=bilinen, toplam=toplam, dilimler=dilimler, profiller=profiller)


def teyit_deneyi(olay):
    """C) Her sinyal için 15 dk önceki başka-cüzdan alımları: yok / yalnızca aynı blok / farklı zamanda (bağımsız)."""
    tok = defaultdict(list)
    for o in olay.values(): tok[o["token"]].append(o)
    grup = defaultdict(list)
    for v in tok.values():
        v.sort(key=lambda o: o["ts"])
        for i, o in enumerate(v):
            k = o["sonuc"].get("kaynak")
            if k is None: continue
            onceki = [p for p in v[:i] if p["wallet"] != o["wallet"] and o["ts"] - p["ts"] <= TEYIT_SN]
            if not onceki: grup["teyitsiz (ilk alan)"].append(k[1]); continue
            ayni = all(p["blok"] is not None and o["blok"] is not None and abs(p["blok"] - o["blok"]) <= AYNI_BLOK_SN for p in onceki)
            grup["teyitli: yalnızca aynı blok (bağlı olabilir)" if ayni else "teyitli: farklı zamanda (bağımsız)"].append(k[1])
    return [dict(ad=ad, **_ozet(grup.get(ad, []))) for ad in
            ("teyitsiz (ilk alan)", "teyitli: farklı zamanda (bağımsız)", "teyitli: yalnızca aynı blok (bağlı olabilir)")]


YAS_ESIK = ((0, "Şimdiki (yaş süzgeci yok)"), (600, "Token en az 10 dk'lık"), (3600, "Token en az 1 sa'lik"),
            (86400, "Token en az 1 günlük"))


def yas_filtre_deneyi(olay, golge=frozenset(), kural=None):
    """B2) Şimdiki kural + 'şu yaştan genç token'a girme' (kaynak çıkışı, gölge hariç). Yaşı bilinmeyen sinyal geçer."""
    kural = kural or dict(max_poz=8, oran=0.05, rt_max=3.0)
    tum = sorted((o for o in olay.values() if o["wallet"] not in golge and "kaynak" in o["sonuc"]), key=lambda o: o["ts"])
    out = []
    for esik, ad in YAS_ESIK:
        s = [(o["ts"], max(o["ts"], o["sonuc"]["kaynak"][0]), o["wallet"], o["token"], o["sonuc"]["kaynak"][1], o["rt"])
             for o in tum if esik == 0 or o["yas"] is None or o["yas"] >= esik]
        out.append(dict(ad=ad, n=len(s), **D.simule(s, **kural)))
    return out


def rapor(etiket_db=None, now=None, gun=14, golge=None):
    now = now if now is not None else time.time()
    olay = _oku(etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db"), now, gun)
    golge = D.golge_seti() if golge is None else set(golge)
    return dict(cikis=cikis_deneyi(olay, golge), yas=yas_deneyi(olay), yas_filtre=yas_filtre_deneyi(olay, golge),
                teyit=teyit_deneyi(olay), olay=len(olay))


def satirlar(r, gun=14):
    f = lambda v: "—" if v is None else f"%{v:+.1f}"
    L = [f"[13] Çıkış deneyi (son {gun} gün, 8x%5, al-sat <= %3; aynı sinyaller, yalnızca çıkış farklı): çıkış / sinyal / işlem / K/Z / kazanan / düşüş"]
    for x in r["cikis"]:
        L.append(f"    {x['ad']:<34} {x['n']:>4} {x['islem']:>4}  {x['kz']:+7.2f}$  %{x['kazanan']:<3} düşüş {x['dusus']:.2f}$")
    y = r["yas"]
    L.append(f"[14] Token yaşı (alım anında; yaşı bilinen {y['bilinen']}/{y['toplam']} sinyal): yaş / n / ort / medyan / pozitif")
    for x in y["dilimler"]:
        if x["n"]: L.append(f"    {x['ad']:<9} n={x['n']:<4} ort {f(x['ort'])} med {f(x['medyan'])} poz %{x['pozitif']}")
    L.append("    Cüzdan profili (cüzdanın medyan giriş yaşı, 3+ ölçüm): profil / cüzdan / n / ort / medyan")
    for x in y["profiller"]:
        if x["n"]: L.append(f"    {x['ad']:<9} {x['cuzdan']:>3} cüzdan n={x['n']:<4} ort {f(x['ort'])} med {f(x['medyan'])}")
    L.append("[14b] Yaş süzgeci (şimdiki kural, kaynak çıkışı, gölge hariç): süzgeç / sinyal / işlem / K/Z / kazanan / düşüş")
    for x in r.get("yas_filtre") or []:
        L.append(f"    {x['ad']:<28} {x['n']:>4} {x['islem']:>4}  {x['kz']:+7.2f}$  %{x['kazanan']:<3} düşüş {x['dusus']:.2f}$")
    L.append("[15] Teyit bağımsızlığı (15 dk içinde başka cüzdan aynı token'ı aldı mı?): grup / n / ort / medyan / pozitif")
    for x in r["teyit"]:
        if x["n"]: L.append(f"    {x['ad']:<44} n={x['n']:<4} ort {f(x['ort'])} med {f(x['medyan'])} poz %{x['pozitif']}")
    return L

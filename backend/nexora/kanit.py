"""Kanıt karnesi: hangi sinyal kaynağı GERÇEKTEN para kazandırıyor? (salt okunur)

Ürünün pazarlanabilmesi için en önemli soru bu. Her kaynak (Solana cüzdanları, borsa sinyalleri, piyasa stratejileri,
BNB, Base, yönlendirici) için zararlar dahil paper sonuçlarından:
  - işlem başına getiri (%; kaynakların portföy büyüklüğünden bağımsız), kazanma oranı, kâr faktörü
  - ortalama getirinin %95 güven ALT sınırı: şans eseri iyi görünen kısa seriyi ayıklar
  - portföy getirisi (başlangıç 100) ve saatlik değer kayıtlarından en büyük düşüş (yönlendirici kayıtları)
Kanıt düzeyi (kaba ama dürüst):
  yetersiz veri : < 30 kapanan işlem ya da < 14 gün
  zararda       : ortalama işlem getirisi <= 0
  umut verici   : ortalama > 0 ama güven alt sınırı <= 0 (şans olabilir)
  güçlü         : güven alt sınırı > 0 VE kâr faktörü >= 1,3
"Güçlü" bile gerçek para için tek başına yeterli değildir: hazırlık karnesi, hukuk ve ayrı açık onay gerekir."""
import json, os, sqlite3, time

from nexora.hazirlik import islem_istatistigi
from nexora import yonlendirici as Y

MIN_ISLEM, MIN_GUN, MIN_PF = 30, 14, 1.3
BASLANGIC = 100.0


def _islemler(yol):
    if not os.path.exists(yol): return []
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=5)
    try:
        return c.execute("SELECT ts, qty, price, fee, pnl FROM trades WHERE LOWER(side)='sell' AND decision='KOPYALANDI' "
                         "AND pnl IS NOT NULL ORDER BY ts").fetchall()
    except sqlite3.Error:
        return []
    finally:
        c.close()


def _ilk_islem(yol):
    if not os.path.exists(yol): return None
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=5)
    try:
        return c.execute("SELECT MIN(ts) FROM trades WHERE decision='KOPYALANDI'").fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        c.close()


def getiriler(satirlar, bas_ts=0.0):
    out = []
    for ts, qty, price, fee, pnl in satirlar:
        if ts < bas_ts or not qty or not price: continue
        maliyet = qty * price - (fee or 0.0) - pnl
        if maliyet > 0: out.append(100.0 * pnl / maliyet)
    return out


def duzey(ist, gun):
    if ist.get("n", 0) < MIN_ISLEM or gun < MIN_GUN: return "yetersiz veri"
    if ist["ort"] <= 0: return "zararda"
    if ist.get("guven_alt") is not None and ist["guven_alt"] > 0 and (ist.get("profit_factor") or 0) >= MIN_PF: return "güçlü"
    return "umut verici"


def en_buyuk_dusus(degerler):
    zirve, en = None, 0.0
    for v in degerler:
        if not v: continue
        zirve = v if zirve is None else max(zirve, v)
        en = max(en, (zirve - v) / zirve * 100)
    return round(en, 2)


def karne(kok=".", yon_db="nexora_yonlendirici.db", now=None):
    now = now or time.time()
    kaynaklar = Y.kaynaklar(kok)
    seri = {}                                             # saatlik değer kayıtları (yönlendirici turlarından)
    yon_yol = yon_db if os.path.isabs(yon_db) else os.path.join(kok, yon_db)
    yon = []
    if os.path.exists(yon_yol):
        c = sqlite3.connect(f"file:{yon_yol}?mode=ro", uri=True, timeout=5)
        try:
            for ts, d, kd in c.execute("SELECT ts, deger, kaynak_deger FROM tur ORDER BY ts"):
                yon.append((ts, d))
                for k, v in json.loads(kd).items(): seri.setdefault(k, []).append(v)
        except sqlite3.Error:
            pass
        finally:
            c.close()
    out = []
    for i, ad, yol in kaynaklar:
        sat = _islemler(yol); ilk = _ilk_islem(yol)
        gun = round((now - ilk) / 86400, 1) if ilk else 0.0
        ist = islem_istatistigi(getiriler(sat))
        hafta = islem_istatistigi(getiriler(sat, now - 7 * 86400))
        deger = Y.deger(yol)
        out.append(dict(kaynak=i, ad=ad, gun=gun, duzey=duzey(ist, gun) if ist.get("n") else "yetersiz veri",
                        islem=ist, son7=hafta, portfoy_getiri_pct=round((deger / BASLANGIC - 1) * 100, 2) if deger else None,
                        en_buyuk_dusus_pct=en_buyuk_dusus(seri.get(i, [])) if seri.get(i) else None))
    if yon:
        gun = round((now - yon[0][0]) / 86400, 1)
        out.append(dict(kaynak="yonlendirici", ad="Yapay zekâ yönlendirici", gun=gun,
                        duzey="yetersiz veri" if gun < 21 else ("zararda" if yon[-1][1] <= yon[0][1] else "umut verici"),
                        islem=dict(n=0), son7=dict(n=0), portfoy_getiri_pct=round((yon[-1][1] / yon[0][1] - 1) * 100, 2),
                        en_buyuk_dusus_pct=en_buyuk_dusus([d for _, d in yon])))
    sira = {"güçlü": 0, "umut verici": 1, "yetersiz veri": 2, "zararda": 3}
    out.sort(key=lambda x: (sira[x["duzey"]], -(x["portfoy_getiri_pct"] or -1e9)))
    guclu = [x["ad"] for x in out if x["duzey"] == "güçlü"]
    return dict(ts=now, kaynaklar=out,
                ozet=("Kanıtlanmış kaynak: " + ", ".join(guclu)) if guclu else
                     "Henüz hiçbir kaynak güçlü kanıt düzeyinde değil (en az 30 kapanan işlem, 14 gün, güven alt sınırı > 0, kâr faktörü ≥ 1,3).",
                not_="Paper sonuçlarıdır; gerçek para kullanılmaz. Geçmiş sonuç gelecekteki kazancı garanti etmez.")


def metin(k):
    satir = ["NEXORA kanıt karnesi · " + time.strftime("%d.%m.%Y %H:%M", time.localtime(k["ts"])), k["ozet"], ""]
    for x in k["kaynaklar"]:
        ist = x["islem"]
        g = "—" if x["portfoy_getiri_pct"] is None else f"%{x['portfoy_getiri_pct']:+.2f}"
        dd = "—" if x["en_buyuk_dusus_pct"] is None else f"%{x['en_buyuk_dusus_pct']:.1f}"
        satir.append(f"[{x['duzey'].upper()}] {x['ad']}  ({x['gun']} gün)")
        satir.append(f"   portföy {g} · en büyük düşüş {dd}")
        if ist.get("n"):
            ga = "—" if ist.get("guven_alt") is None else f"%{ist['guven_alt']:+.2f}"
            pf = "—" if ist.get("profit_factor") is None else f"{ist['profit_factor']:.2f}"
            satir.append(f"   {ist['n']} kapanan · kazanma %{ist['kazanma_pct']:.0f} · işlem başına ort. %{ist['ort']:+.2f} "
                         f"(güven alt sınırı {ga}) · kâr faktörü {pf} · son 7 gün {x['son7'].get('n', 0)} işlem")
    satir += ["", k["not_"]]
    return "\n".join(satir)

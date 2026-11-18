"""N16–N19 salt okunur veri kalitesi, net sonuç ve gölge karar raporu."""
import re
import time
from collections import Counter, defaultdict
from statistics import median

from nexora.model import degerlendir, kalibrasyon
from nexora.model_kapisi import EN_AZ_GOLGE_ETIKET, EN_AZ_GOLGE_GUN, GOLGE_GEREKCELERI, golge_gerekcesi
from nexora.olcum import GIRIS_TOLERANS, IZLENEN, UFUKLAR, etiket_sonucu, politika, pozitif, sayi
from nexora.ozellik import OZELLIKLER, aileler, bot_karari, cesitlilik, sinyalleri_oku, t0_ozellikler


def _gozlem(s):
    g = s.golge or {}
    ts, p, esik = (sayi(g.get(k)) for k in ("ts", "olasilik", "esik"))
    version = g.get("model_surumu")
    if (not isinstance(version, str) or not re.fullmatch(r"[0-9]{1,12}-[0-9a-f]{8}", version)
            or not s.ts or ts is None or not s.ts <= ts <= s.ts + GIRIS_TOLERANS
            or int(version.split("-")[0]) > s.ts
            or p is None or esik is None or not (0 <= p <= 1 and 0 <= esik <= 1)):
        version = p = esik = None
    if g:
        kod = g.get("gerekce")
        if kod not in GOLGE_GEREKCELERI or g["sinif"] != GOLGE_GEREKCELERI[kod][0]:
            kod = "veri"
        if kod in ("aday", "esik") and (p is None or (p >= esik) != (kod == "aday")):
            kod = "model"
    else:
        kod = golge_gerekcesi(s.olay, None)
    sinif, neden = GOLGE_GEREKCELERI[kod]
    return dict(sinif=sinif, gerekce=neden, model_surumu=version, olasilik=p, esik=esik,
                secim=True if kod == "aday" else (False if kod in ("esik", "risk", "izle") else None))


def _olcu(v):
    sayilar = [x for val in v if (x := sayi(val)) is not None and abs(x) <= 1e30]
    return dict(n=len(sayilar), medyan=round(median(sayilar), 4) if sayilar else None)


def _golge_ozet(sinyaller, gozlemler, sonuclar):
    surumler = defaultdict(list)
    for s, g, net in zip(sinyaller, gozlemler, sonuclar):
        if g["model_surumu"] is not None:
            surumler[g["model_surumu"]].append((s, g, net))
    out = {}
    for v, rows in sorted(surumler.items()):
        bilinen = [(s, g, n) for s, g, n in rows if n is not None]
        ps, ys = [g["olasilik"] for _, g, _ in bilinen], [n for _, _, n in bilinen]
        kalib, ece = kalibrasyon(ps, ys)
        bas, son = rows[0][0].ts, rows[-1][0].ts
        gun = (son - bas) / 86400
        ilk = [g["olasilik"] >= g["esik"] for s, g, _ in rows if s.ts < bas + 7 * 86400]
        son7 = [g["olasilik"] >= g["esik"] for s, g, _ in rows if s.ts > son - 7 * 86400]
        kayma = sum(son7) / len(son7) - sum(ilk) / len(ilk) if gun >= EN_AZ_GOLGE_GUN and ilk and son7 else None
        out[v] = dict(n=len(rows), etiketli=len(bilinen), gun=round(gun, 2),
                      yeterlilik=gun >= EN_AZ_GOLGE_GUN and len(bilinen) >= EN_AZ_GOLGE_ETIKET,
                      cesitlilik=cesitlilik([s for s, _, _ in bilinen]), kalibrasyon=kalib, ece=ece,
                      brier=sum((p - (n > 0)) ** 2 for p, n in zip(ps, ys)) / len(ps) if ps else None,
                      kayma=round(kayma, 4) if kayma is not None else None,
                      net=politika([g["secim"] for _, g, _ in rows], [n for _, _, n in rows]),
                      hepsini_kopyala=politika([True] * len(rows), [n for _, _, n in rows]))
    return out


def rapor(db_path, ufuk="kaynak", *, now=None, ayrinti=False, dogrula=True):
    if ufuk not in (*UFUKLAR, "kaynak"):
        raise ValueError("ufuk geçersiz")
    now = time.time() if now is None else now
    sinyaller, eslesmeyen = sinyalleri_oku(db_path)
    if not sinyaller:
        return dict(durum="veri yok", sinyal_sayisi=0, eslesmeyen_etiket=eslesmeyen)
    aile = aileler(sinyaller)
    gozlemler = [_gozlem(s) for s in sinyaller]
    t0 = [t0_ozellikler(s.olay) for s in sinyaller]
    bot = [bot_karari(s.olay) for s in sinyaller]
    n = len(sinyaller)
    out = dict(
        durum="ölçüm mevcut", sinyal_sayisi=n, eslesmeyen_etiket=eslesmeyen, ufuk=ufuk,
        cesitlilik=cesitlilik(sinyaller, aile),
        token_ailesi_sayisi=len(set(aile.values())),
        coklu_token_ailesi=sum(v > 1 for v in Counter(aile[s.token] for s in sinyaller if s.token).values()),
        kopyalandi=bot.count(1.0), reddedildi=bot.count(0.0),
        sadece_izlenen=sum(s.olay.get("gerekce") == IZLENEN for s in sinyaller), bot_karari_bilinmiyor=bot.count(None),
        eksik_t0_pct={k: round(100 * sum(o[k] is None for o in t0) / n, 2) for k in OZELLIKLER if k != "bot_kopyaladi"},
        veri_kaynagi=dict(
            t0_v1=sum(s.olay.get("olcum_v") == 1 and s.ts is not None for s in sinyaller),
            zincir_zamani_bilinen=sum(pozitif(s.olay.get("block_time")) is not None for s in sinyaller),
            t0_token_gecmis=sum(any(o[k] is not None for k in ("log_likidite", "log_yas_saat", "organik")) for o in t0),
            cuzdanda_kaynak_zamani_dogrulanmis=0,
            olculen_likidite=_olcu(pozitif(s.olay.get("tb_likidite")) for s in sinyaller),
            algilama_gecikmesi_sn=_olcu(s.olay.get("gecikme_sn") for s in sinyaller),
            teklif_gecikmesi_sn=_olcu(pozitif(s.olay.get("giris_ts")) - s.ts for s in sinyaller
                                     if pozitif(s.olay.get("giris_ts")) is not None and s.ts is not None),
            al_sat_kaybi_pct=_olcu(s.olay.get("al_sat_kaybi_pct") for s in sinyaller)),
        ufuklar={}, golge=dict(hedef_ufuk="kaynak", siniflar=dict(Counter(g["sinif"] for g in gozlemler))))
    ufuk_sonuclari = {}
    for u in (*UFUKLAR, "kaynak"):
        sonuc = [etiket_sonucu(s.olay, s.etiketler.get(u), u, now) for s in sinyaller]
        ufuk_sonuclari[u] = sonuc
        durum = Counter(d for d, _, _ in sonuc)
        net = [v if d == "OK" else None for d, v, _ in sonuc]
        olgun = n - durum["bekliyor"]
        out["ufuklar"][u] = dict(
            net_ornek=durum["OK"], unknown=n - durum["OK"], bekleyen=durum["bekliyor"], olgun=olgun,
            etiket_basari_pct=round(100 * durum["OK"] / olgun, 2) if olgun else None,
            dogrulanamayan_eski_kayit=durum["eski kayıt"], gec_etiket=durum["kaçırıldı"],
            satis_yolu_hatasi=durum["satış yolu hatası"], durumlar=dict(durum),
            cikis_sapmasi_sn=_olcu(s.etiketler.get(u, {}).get("sapma_sn") for s in sinyaller),
            net=dict(hepsini_kopyala=politika([True] * n, net),
                     mevcut_bot=politika([None if b is None else b == 1.0 for b in bot], net),
                     alim_yok=politika([False] * n, net), golge_ai=politika([g["secim"] for g in gozlemler], net)))
        if u == "kaynak":
            out["golge"]["surumler"] = _golge_ozet(sinyaller, gozlemler, net)
    if dogrula:
        out["dogrulama"], _ = degerlendir(sinyaller, ufuk, now=now)
        out["avantaj"] = out["dogrulama"]["karar"] if out["dogrulama"]["karar"] == "avantaj var" else "avantaj doğrulanamadı"
    if ayrinti:
        out["sinyaller"] = [dict(sinyal_no=i + 1, **g, sonuclar={
            u: dict(durum=d if d == "OK" else "UNKNOWN", neden=d, net_usdc=round(v, 6) if d == "OK" else None,
                    getiri_pct=p if d == "OK" else None)
            for u, sonuc in ufuk_sonuclari.items() for d, v, p in [sonuc[i]]
        }) for i, g in enumerate(gozlemler)]
    return out

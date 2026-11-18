"""N18 lojistik regresyonu ve zamanda ileri, token aileli doğrulama."""
import json
import math
import os
import random
import tempfile
import time
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

from nexora.olcum import etiket_sonucu, politika, sayi
from nexora.ozellik import OZELLIKLER, aileler, cesitlilik, ornekler

EN_AZ_ORNEK = 500
ANA_OZELLIKLER = [k for k in OZELLIKLER if k != "bot_kopyaladi"]


def _sig(z): return 1 / (1 + math.exp(-max(-35, min(35, z))))


def _deger(v):
    x = sayi(v)
    return x if x is not None and abs(x) <= 1e12 else None


def _medyan(v):
    v = sorted(v); n = len(v)
    return 0.0 if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


class Model:
    def __init__(self, ozellikler=OZELLIKLER, l2=1.0, adim=0.1, tur=400):
        self.oz, self.l2, self.adim, self.tur = list(ozellikler), l2, adim, tur

    def _hazirla(self, X):
        satir = []
        for o in X:
            v = []
            for k in self.oz:
                x = _deger(o.get(k))
                v.append(((self.medyan[k] if x is None else x) - self.ort[k]) / self.std[k])
                v.append(1.0 if x is None else 0.0)
            satir.append(v)
        return satir

    def egit(self, X, y_getiri):
        getiriler = [sayi(g) for g in y_getiri]
        if not X or len(X) != len(getiriler) or any(g is None for g in getiriler):
            raise ValueError("eğitim verisi geçersiz")
        sutun = {k: [_deger(o.get(k)) for o in X] for k in self.oz}
        self.medyan = {k: _medyan([x for x in v if x is not None]) for k, v in sutun.items()}
        dol = {k: [self.medyan[k] if x is None else x for x in v] for k, v in sutun.items()}
        self.ort = {k: sum(v) / len(v) for k, v in dol.items()}
        self.std = {k: max(1e-12, math.sqrt(sum((x - self.ort[k]) ** 2 for x in v) / len(v)) or 1.0)
                    for k, v in dol.items()}
        A = self._hazirla(X); y = [1.0 if g > 0 else 0.0 for g in getiriler]
        n, d = len(A), len(A[0])
        self.w, self.b = [0.0] * d, math.log((sum(y) + 1) / (n - sum(y) + 1))
        for _ in range(self.tur):
            gw, gb = [0.0] * d, 0.0
            for a, t in zip(A, y):
                e = _sig(self.b + sum(wi * ai for wi, ai in zip(self.w, a))) - t
                gb += e
                for j in range(d): gw[j] += e * a[j]
            self.b -= self.adim * gb / n
            self.w = [wi - self.adim * (g / n + self.l2 * wi / n) for wi, g in zip(self.w, gw)]
        return self

    def olasilik(self, X):
        return [_sig(self.b + sum(wi * ai for wi, ai in zip(self.w, a))) for a in self._hazirla(X)]

    def agirliklar(self):
        """Standartlaştırılmış etki (eksiklik göstergeleri hariç), büyükten küçüğe."""
        return sorted(((k, round(self.w[2 * i], 4)) for i, k in enumerate(self.oz)), key=lambda x: -abs(x[1]))

    @classmethod
    def yukle(cls, d):
        """kaydet() çıktısından modeli kurar. Eksik/bozuk alan ValueError verir."""
        try:
            alanlar = d["ozellikler"]
            if not isinstance(alanlar, list) or not alanlar or any(k not in OZELLIKLER for k in alanlar):
                raise ValueError("model özellikleri geçersiz")
            if len(alanlar) != len(set(alanlar)):
                raise ValueError("model özellikleri yinelenmiş")
            m = cls(ozellikler=alanlar)
            m.w, m.b = [float(x) for x in d["w"]], float(d["b"])
            m.medyan, m.ort, m.std = ({k: float(d[ad][k]) for k in m.oz} for ad in ("medyan", "ort", "std"))
        except (KeyError, TypeError, ValueError, OverflowError) as e:
            raise ValueError(f"model dosyası bozuk: {e}") from None
        if len(m.w) != 2 * len(m.oz): raise ValueError("model ağırlık sayısı tutarsız")
        if any(_deger(x) is None for x in [m.b, *m.w, *m.medyan.values(), *m.ort.values(), *m.std.values()]):
            raise ValueError("model sayısal değerleri geçersiz")
        if any(x < 1e-12 for x in m.std.values()):
            raise ValueError("model ölçeği geçersiz")
        return m

    def kaydet(self, yol, meta):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=Path(yol).parent, delete=False) as f:
                tmp = f.name
                json.dump(dict(surum=1, olusturma=time.time(), ozellikler=self.oz, w=self.w, b=self.b, medyan=self.medyan,
                               ort=self.ort, std=self.std, **meta), f, ensure_ascii=False, indent=1, allow_nan=False)
            os.replace(tmp, yol)
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def _esik_sec(p, y, en_az_kapsam=0.2):
    """Eğitim kümesinde seçilenlerin ortalama getirisini en yükselten olasılık eşiği (en az %20 kapsam)."""
    en_iyi = (sum(y) / len(y), 0.0)
    for e in sorted(set(round(x, 3) for x in p)):
        s = [g for pi, g in zip(p, y) if pi >= e]
        if len(s) >= en_az_kapsam * len(y) and sum(s) / len(s) > en_iyi[0]: en_iyi = (sum(s) / len(s), e)
    return en_iyi[1]


def zaman_bol(veri, kesir, bitis=1.0, aile=None):
    """Aynı kayıt zamanındaki sinyaller beraber kalır. Açık sonuçlar ve ortak aileler eğitimden çıkar."""
    zamanlar = [r.ts for r in veri]
    if not zamanlar:
        return [], [], 0
    bas = bisect_left(zamanlar, zamanlar[min(int(len(veri) * kesir), len(veri) - 1)])
    son = len(veri) if bitis == 1 else bisect_left(zamanlar, zamanlar[int(len(veri) * bitis)])
    sin = veri[bas:son]
    if not sin:
        return [], [], bas
    grup = (lambda r: r.token) if aile is None else (lambda r: aile[r.token])
    gruplar = {grup(r) for r in sin}
    egt = [r for r in veri[:bas] if r.cikis_ts < sin[0].ts and grup(r) not in gruplar]
    return egt, sin, bas - len(egt)


def kalibrasyon(ps, ys):
    n = len(ps)
    if not n:
        return [], None
    kutu = defaultdict(list)
    for p, y in zip(ps, ys):
        kutu[min(4, int(p * 5))].append((p, y > 0))
    ece, out = 0, []
    for i, b in sorted(kutu.items()):
        tahmin, gercek = (sum(x) / len(b) for x in zip(*b))
        ece += len(b) / n * abs(tahmin - gercek)
        out.append(dict(aralik=f"{i / 5:.1f}-{(i + 1) / 5:.1f}", n=len(b),
                        tahmin=round(tahmin, 4), gercek=round(gercek, 4)))
    return out, ece


def _brier(ps, ys):
    return sum((p - (g > 0)) ** 2 for p, g in zip(ps, ys)) / len(ys)


def _aralik(farklar):
    if not farklar:
        return None
    v = sorted(farklar)
    return [v[int(0.025 * (len(v) - 1))], v[int(0.975 * (len(v) - 1))]]


def _blok_araliklari(veri, secimler, aile, tekrar, tohum):
    """Bağlı aileleri ve UTC günlerini ayrı ayrı örnekle. Karşılaştırmalar aynı blokları çeker."""
    out = {}
    for ad, blok in (("token_ailesi", lambda r: aile[r.token]), ("gun", lambda r: int(r.ts // 86400))):
        # [n, getiri, seçilen n, seçilen getiri, net model, net hepsi, net bot]
        gruplar = defaultdict(lambda: [0.0] * 7)
        for r, sec in zip(veri, secimler):
            b = gruplar[blok(r)]
            b[0] += 1
            b[1] += r.getiri
            b[2] += sec
            b[3] += r.getiri if sec else 0.0
            b[4] += r.net if sec else 0.0
            b[5] += r.net
            b[6] += r.net if r.bot == 1.0 else 0.0
        v = list(gruplar.values())
        rnd, fark = random.Random(tohum), defaultdict(list)
        if len(v) >= 2:
            for _ in range(tekrar):
                n, g, s, gs, m, h, b = map(sum, zip(*rnd.choices(v, k=len(v))))
                if s:
                    fark["islem_getiri"].append(gs / s - g / n)
                fark["hepsi"].append((m - h) / n)
                fark["bot"].append((m - b) / n)
                fark["alim_yok"].append(m / n)
        aralik = {k: _aralik(fark[k]) for k in ("islem_getiri", "hepsi", "bot", "alim_yok")}
        if len(fark["islem_getiri"]) < tekrar * 0.95:
            aralik["islem_getiri"] = None
        out[ad] = dict(n=len(v), aralik=aralik)
    return out


def _ort(v):
    return sum(v) / len(v) if v else None


def _sinama(egt, sin, bot_dahil=False):
    alanlar = OZELLIKLER if bot_dahil else ANA_OZELLIKLER
    girdi = (lambda r: dict(r.ozellik, bot_kopyaladi=r.bot)) if bot_dahil else (lambda r: r.ozellik)
    X, y = [girdi(r) for r in egt], [r.getiri for r in egt]
    m = Model(alanlar).egit(X, y)
    esik = _esik_sec(m.olasilik(X), y)
    ps, ys = m.olasilik([girdi(r) for r in sin]), [r.getiri for r in sin]
    sec = [p >= esik for p in ps]
    kalib, ece = kalibrasyon(ps, ys)
    brier, taban = _brier(ps, ys), _brier([sum(g > 0 for g in y) / len(y)] * len(ys), ys)
    net = [r.net for r in sin]
    ortak = [(r, s) for r, s in zip(sin, sec) if r.bot is not None]
    ortak_net = [r.net for r, _ in ortak]
    kopya_secili = [r.getiri for r, s in ortak if s]
    return dict(
        esik=esik, secilen=sum(sec), sinama_hepsi_ort=_ort(ys),
        sinama_secili_ort=_ort([g for g, s in zip(ys, sec) if s]),
        brier=brier, brier_taban=taban, ece=ece, kalibrasyon=kalib,
        kopya=dict(n=len(ortak), hepsi=_ort([r.getiri for r, _ in ortak]),
                   secilen=len(kopya_secili), secili=_ort(kopya_secili)),
        net=dict(model=politika(sec, net), hepsi=politika([True] * len(sin), net),
                 alim_yok=politika([False] * len(sin), net), ortak_n=len(ortak),
                 ortak_model=politika([s for _, s in ortak], ortak_net),
                 ortak_hepsi=politika([True] * len(ortak), ortak_net),
                 ortak_alim_yok=politika([False] * len(ortak), ortak_net),
                 ortak_bot=politika([r.bot == 1.0 for r, _ in ortak], ortak_net))), m, sec


def _cesitli(d, gun, aile_min):
    return (d["gun"]["n"] >= gun and d["token_ailesi"]["n"] >= aile_min and d["cuzdan"]["n"] >= 5
            and d["gun"]["en_buyuk_pay"] <= 0.40 and d["token_ailesi"]["en_buyuk_pay"] <= 0.20
            and d["cuzdan"]["en_buyuk_pay"] <= 0.40)


def degerlendir(sinyaller, ufuk="kaynak", *, now=None, bootstrap=1000, tohum=7, zorla=False):
    """İlk %70 geliştirme ve üç ileri pencere, son %30 sabit sınama."""
    now = time.time() if now is None else now
    veri = sorted(ornekler(sinyaller, ufuk, now), key=lambda r: r.ts)
    aile = aileler(sinyaller)
    n = len(veri)
    durumlar = [(s, etiket_sonucu(s.olay, s.etiketler.get(ufuk), ufuk, now)[0]) for s in sinyaller]
    olgun = sum(d != "bekliyor" for _, d in durumlar)
    dagilim = cesitlilik(veri, aile)
    sonuc = dict(karar="avantaj doğrulanamadı", n=n, gerekli=EN_AZ_ORNEK, olgun=olgun,
                 aile_n=dagilim["token_ailesi"]["n"], basari_orani=n / olgun if olgun else None,
                 cesitlilik=dagilim, gerekceler=[])
    if n < EN_AZ_ORNEK:
        sonuc["gerekceler"].append("500 doğrulanmış etiket eşiği")
        if not zorla:
            sonuc["karar"] = "yetersiz veri"
            return sonuc, None
    if not olgun or n / olgun < 0.90:
        sonuc["gerekceler"].append("olgun etiketlerin %90 başarı eşiği")
    if not _cesitli(dagilim, 14, 30):
        sonuc["gerekceler"].append("veri çeşitliliği")
    egt, sin, ayiklanan = zaman_bol(veri, 0.7, aile=aile)
    d = cesitlilik(sin, aile)
    sonuc.update(egitim=len(egt), sinama=len(sin), ayiklanan=ayiklanan, sinama_cesitlilik=d)
    if len(egt) < 50 or len(sin) < 20 or len({r.getiri > 0 for r in egt}) < 2:
        sonuc["gerekceler"].append("ileri sınama için eğitim veya test desteği")
        return sonuc, None

    sin_olgun = sum(s.ts is not None and s.ts >= sin[0].ts and d != "bekliyor" for s, d in durumlar)
    sonuc["sinama_olgun"] = sin_olgun
    if not sin_olgun or len(sin) / sin_olgun < 0.90:
        sonuc["gerekceler"].append("sınama döneminde %90 etiket başarısı")
    sin_grup = d["token_ailesi"]["n"]
    if not _cesitli(d, 5, 20):
        sonuc["gerekceler"].append("sınama çeşitliliği")
    ana, m, sec = _sinama(egt, sin)
    secili_dagilim = cesitlilik([r for r, s in zip(sin, sec) if s], aile)
    if secili_dagilim["token_ailesi"]["n"] < 5 or secili_dagilim["gun"]["n"] < 3:
        sonuc["gerekceler"].append("model seçimlerinin bağımsız blok desteği")
    if bootstrap < 200:
        sonuc["gerekceler"].append("blok bootstrap tekrar sayısı")
    ablation, _, _ = _sinama(egt, sin, bot_dahil=True)
    sonuc.update(ana, secili_cesitlilik=secili_dagilim, agirliklar=m.agirliklar()[:10], bot_dahil_ablation=ablation, sinama_aile_n=sin_grup)

    tum = _blok_araliklari(sin, sec, aile, bootstrap, tohum)
    ortak = [(r, s) for r, s in zip(sin, sec) if r.bot is not None]
    bot = _blok_araliklari([r for r, _ in ortak], [s for _, s in ortak], aile, bootstrap, tohum)
    sonuc.update(blok_araliklari=tum, ortak_blok_araliklari=bot)
    a = [v["aralik"]["islem_getiri"] for v in tum.values()]
    sonuc["fark_guven_araligi"] = [min(v[0] for v in a), max(v[1] for v in a)] if all(a) else None
    if any(v["aralik"][k] is None or v["aralik"][k][0] <= 0
           for v in tum.values() for k in ("islem_getiri", "hepsi", "alim_yok")):
        sonuc["gerekceler"].append("hepsini kopyala ve alım yapmama karşılaştırmasında blok güven aralığı")
    if (len(ortak) < 0.5 * len(sin) or bot["gun"]["n"] < 5 or bot["token_ailesi"]["n"] < 20
            or len({r.bot for r, _ in ortak}) < 2
            or any(v["aralik"]["bot"] is None or v["aralik"]["bot"][0] <= 0 for v in bot.values())):
        sonuc["gerekceler"].append("kayıtlı bot kararına karşı eşleşmiş örnek veya kanıt")
    if not (ana["brier"] < ana["brier_taban"] and ana["ece"] <= 0.15):
        sonuc["gerekceler"].append("Brier veya kalibrasyon")

    # Son %30 eşik, ablation seçimi ve ileri pencere geliştirmesi için kullanılmaz.
    gelistirme = egt
    ileri = []
    for bas, son in ((0.4, 0.6), (0.6, 0.8), (0.8, 1.0)):
        e, s, atilan = zaman_bol(gelistirme, bas, son, aile=aile)
        f = dict(egitim=len(e), sinama=len(s), ayiklanan=atilan, aile_n=len({aile[r.token] for r in s}),
                 cesitlilik=cesitlilik(s, aile))
        if len(e) >= 50 and len(s) >= 20 and len({r.getiri > 0 for r in e}) == 2:
            metrik, _, _ = _sinama(e, s)
            f.update(metrik)
        ileri.append(f)
    sonuc["ileri_pencereler"] = ileri
    if not all(p.get("net") and p["aile_n"] >= 10 and p["cesitlilik"]["gun"]["n"] >= 2
               and p["net"]["model"]["sinyal_basi_usdc"] > p["net"]["hepsi"]["sinyal_basi_usdc"]
               and p["net"]["model"]["sinyal_basi_usdc"] > 0 for p in ileri):
        sonuc["gerekceler"].append("ileriye yürüyen pencerelerde tutarlılık")
    if not sonuc["gerekceler"] and not zorla:
        sonuc["karar"] = "avantaj var"
        return sonuc, m
    return sonuc, None

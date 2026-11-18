"""EVM cüzdan kârlılık analizi (N24, keşfin 2. yarısı). Platform 1 (Solana) ile AYNI karar ve sağlamlık kuralları.

Cüzdanın son günlerdeki ERC-20 transferleri bloklardan okunur (eth_getLogs; düğüm sınırında aralık bölünür), token içeren her
işlem makbuzuyla çözülür (swap mı, ne alındı, ne ödendi), karşı varlık USD'ye çevrilir (stablecoin = 1 $, yerel/sarılı
coin = tek bir güncel fiyat: yaklaşıklık), token başına FIFO ile gerçekleşen K/Z hesaplanır. Salt okunur."""
from collections import Counter, defaultdict
from statistics import median

from nexora.evm import ZINCIRLER, YEREL, EvmHatasi, TRANSFER, _konu, coz_tam
from nexora.evm_kesif import _loglar
from nexora.wallet_analysis import saglamlik, verdict, score

BLOK_SURESI = {"bnb": 0.75, "base": 2.0}            # yaklaşık saniye/blok (tutma süresi tahmini için)


def swaplar(rpc, cuzdan, zincir, bas, son, en_fazla_islem=150, sayac=None, gezgin=None):
    """Cüzdanın [bas, son] bloklarındaki swap'ları, blok sırasıyla: [dict(blok, yon, token, miktar_raw, karsi, karsi_raw)].
    `sayac` verilirse: islem (token hareketli işlem), cozulemeyen (swap olarak çözülemeyen) sayıları yazılır."""
    w = cuzdan.lower(); karsi = ZINCIRLER[zincir]["karsi"]
    islemler = gezgin(w, bas) if gezgin else None           # gezgin (Blockscout) varsa geçmiş tek sayfalı istekle gelir
    if islemler is None:
        islemler = {}
        for konular in ([TRANSFER, None, _konu(w)], [TRANSFER, _konu(w)]):
            for l in _loglar(rpc, {"topics": konular}, bas, son):
                if (l.get("address") or "").lower() in karsi: continue  # yalnızca karşı varlık hareketi: swap adayı değil
                islemler.setdefault(l["transactionHash"], int(l["blockNumber"], 16))
    out = []; secili = sorted(islemler.items(), key=lambda x: x[1])[-en_fazla_islem:]
    if sayac is not None: sayac.update(islem=len(islemler), cozulemeyen=0, araci=Counter())
    for karma, blok in secili:
        try:
            tx = rpc.call("eth_getTransactionByHash", [karma]) or {}
            s = coz_tam(rpc, tx, rpc.call("eth_getTransactionReceipt", [karma]) or {}, w, zincir, blok)
        except EvmHatasi:
            continue
        if s: out.append(dict(s, blok=blok))
        elif sayac is not None:
            sayac["cozulemeyen"] += 1; sayac["araci"][(tx.get("to") or "?").lower()] += 1
    return out


def usd(rpc, zincir, karsi, raw, yerel_usd):
    if karsi in (YEREL, ZINCIRLER[zincir]["sarili"]): return raw / 1e18 * yerel_usd
    return raw / 10 ** rpc.ondalik(karsi)


def analiz(sw, rpc, zincir, yerel_usd, cuzdan=""):
    """Swap listesinden Solana analiziyle aynı alanlar: kapanan, kazanma, kâr faktörü, ortalama getiri, tutma, sağlamlık..."""
    kuyruk = defaultdict(list); kapanan = []; satis = eslesmeyen = 0
    for s in sw:
        u = usd(rpc, zincir, s["karsi"], s["karsi_raw"], yerel_usd)
        if s["yon"] == "buy":
            kuyruk[s["token"]].append([s["miktar_raw"], u, s["blok"]]); continue
        satis += 1; kalan = s["miktar_raw"]; maliyet = 0.0; tutmalar = []
        q = kuyruk[s["token"]]
        while kalan > 0 and q:
            lot = q[0]; al = min(kalan, lot[0]); pay = al / lot[0]
            maliyet += lot[1] * pay; tutmalar.append((s["blok"] - lot[2]) * BLOK_SURESI[zincir])
            lot[0] -= al; lot[1] -= lot[1] * pay; kalan -= al
            if lot[0] <= 0: q.pop(0)
        if maliyet <= 0: eslesmeyen += 1; continue
        oran = (s["miktar_raw"] - kalan) / s["miktar_raw"]
        kapanan.append(dict(pnl=u * oran - maliyet, cost=maliyet, ts=s["blok"], holds=tutmalar, token=s["token"]))
    kazanc = sum(c["pnl"] for c in kapanan if c["pnl"] > 0); kayip = -sum(c["pnl"] for c in kapanan if c["pnl"] < 0)
    getiri = [c["pnl"] / c["cost"] for c in kapanan if c["cost"] > 0]
    token_kz = defaultdict(float); token_say = defaultdict(int)
    for c in kapanan: token_kz[c["token"]] += c["pnl"]; token_say[c["token"]] += 1
    tut = [median(c["holds"]) for c in kapanan if c["holds"]]
    duz = sum(1 for g in getiri if abs(g) < 0.02)
    m = dict(wallet=cuzdan, swap=len(sw), alis=sum(1 for s in sw if s["yon"] == "buy"), satis=satis, kapanan=len(kapanan),
             eslesmeyen_satis=eslesmeyen, gerceklesen_usd=round(kazanc - kayip, 2), token_sayisi=len({s["token"] for s in sw}),
             kazanma_orani=round(sum(1 for c in kapanan if c["pnl"] > 0) / len(kapanan), 3) if kapanan else 0.0,
             kar_faktoru=round(kazanc / kayip, 2) if kayip > 0 else (99.0 if kazanc > 0 else 0.0),
             ort_getiri=round(sum(getiri) / len(getiri), 4) if getiri else 0.0,
             medyan_tutma_sn=round(median(tut)) if tut else None,
             en_buyuk_token_payi=round(max(token_kz.values()) / kazanc, 3) if kazanc > 0 and token_kz else 0.0,
             sifir_tur_orani=round(duz / len(getiri), 3) if getiri else 0.0, tek_token_tur=max(token_say.values()) if token_say else 0,
             **saglamlik(kapanan))
    karar, neden = verdict(m)
    m.update(karar=karar, gerekce="; ".join(neden), skor=round(score(m), 4) if karar == "kopyalanabilir" else 0.0)
    return m


def yerel_fiyat(teklif, zincir):
    """1 yerel coin (BNB/ETH) kaç USD: toplayıcıdan sarılı coin -> USD stablecoin teklifi."""
    z = ZINCIRLER[zincir]
    return teklif.teklif(z["sarili"], z["usd"], 10 ** 18)["cikis_raw"] / 10 ** z["usd_ondalik"]


COZULEMEZ_ORAN, COZULEMEZ_EN_AZ = 0.5, 10


def cozum_karari(m, sayac):
    """İşlemlerinin yarıdan fazlası swap olarak çözülemeyen cüzdan: ödeme tarafı zincir kayıtlarında görünmüyor
    (ör. parası önceden bir bot/emir sözleşmesine yatırılmış). Maliyeti ölçülemez ve sinyalleri de çözülemez:
    hangi karar çıkmış olursa olsun 'çözülemiyor' olur (görünen azınlık işlemle verilen karar yanıltıcıdır) ve kopyalanmaz."""
    n, c = sayac.get("islem", 0), sayac.get("cozulemeyen", 0)
    if n < COZULEMEZ_EN_AZ or c / n <= COZULEMEZ_ORAN: return m
    en = (sayac.get("araci") or Counter()).most_common(1)
    araci = f"; en sık aracı {en[0][0][:10]}… ({en[0][1]} işlem)" if en else ""
    return dict(m, karar="çözülemiyor", gerekce=f"işlemlerin %{100 * c / n:.0f}'i swap olarak çözülemedi{araci}", skor=0.0)

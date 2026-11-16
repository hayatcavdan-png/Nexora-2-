"""EVM cüzdan keşfi (PAPER, salt okunur): yükselen token'ları erken alan gerçek kullanıcı cüzdanları.
  python evm_kesif.py bnb                 # adaylar -> wallets_bnb_kesif.txt (takip listesine DOKUNMAZ)
  python evm_kesif.py bnb --ekle          # analizden "kopyalanabilir" çıkan ilk 5 cüzdanı wallets_bnb.txt'e ekler (yedekli)
  EVM_KESIF_TOKEN=15 EVM_KESIF_EN_AZ=2 python evm_kesif.py bnb
Adaylar son EVM_ANALIZ_GUN (2) günlük alım-satımlarıyla Solana ile aynı kurallarla analiz edilir (EVM_ANALIZ_ADAY=20 aday)."""
import json, os, shutil, sys
from collections import Counter
import requests
from nexora import ekosistem
from nexora.evm import ZINCIRLER, EvmRpc, KyberTeklif
from nexora import evm_analiz as A
from nexora import evm_kesif as K

TOKEN = int(os.getenv("EVM_KESIF_TOKEN", "25")); EN_AZ = int(os.getenv("EVM_KESIF_EN_AZ", "2")); EKLE = 5
ANALIZ = int(os.getenv("EVM_ANALIZ_ADAY", "20")); GUN = int(os.getenv("EVM_ANALIZ_GUN", "2"))


def main(argv, rpc=None, s=None):
    z = argv[0] if argv else "bnb"
    if z not in ZINCIRLER: sys.exit("zincir: bnb ya da base")
    c = ZINCIRLER[z]; rpc = rpc or EvmRpc(os.getenv(c["rpc_env"]) or c["rpc"]); s = s or requests.Session()
    ist = {}
    tok = K.sicak_tokenler(s, z, TOKEN, istatistik=ist)
    print(f"Kaynaklar: DexScreener {ist.get('dexscreener', 0)} token, GeckoTerminal {ist.get('geckoterminal', 0)} token; "
          f"filtreden geçen {len(tok)} (likidite ≥ 50 bin $, hacim ≥ 50 bin $, son 30 gün)", flush=True)
    if not tok: sys.exit("Uygun yükselen token bulunamadı.")
    print(f"{c['ad']}: {len(tok)} yükselen token, her birinin ilk ~30 dakikasındaki alıcılar inceleniyor…", flush=True)
    mevcut = ekosistem.cuzdanlar(z)
    gruplar = []
    adaylar, say = K.kesfet(rpc, tok, EN_AZ, bilinen=mevcut, gruplar=gruplar)
    print(f"{len(say)} farklı erken alıcı; {len(adaylar)} kullanıcı cüzdanı en az {EN_AZ} yükselen token'ı erken aldı", flush=True)
    secilen = K.analiz_adaylari(rpc, gruplar, say, mevcut, ANALIZ)
    blok = int(GUN * 86400 / A.BLOK_SURESI[z]); son = rpc.blok()
    print(f"{len(secilen)} aday analiz ediliyor: her birinin son {GUN} günlük alım-satımı zincirden okunuyor (birkaç dakika sürebilir)…", flush=True)
    try:
        yerel = A.yerel_fiyat(KyberTeklif(z), z)
    except Exception as ex:
        sys.exit(f"Yerel coin fiyatı alınamadı: {ex}")
    sonuc = []
    for i, w in enumerate(secilen, 1):
        try:
            m = A.analiz(A.swaplar(rpc, w, z, son - blok, son), rpc, z, yerel, w)
        except Exception as ex:
            m = dict(wallet=w, karar="hata", gerekce=f"{type(ex).__name__}: {str(ex)[:60]}", kapanan=0, gerceklesen_usd=0.0)
        sonuc.append(m)
        print(f"  {i:>2}/{len(secilen)} {w[:6]}…{w[-4:]}  {m['karar']:<15} K/Z {m.get('gerceklesen_usd', 0):+.0f}$  "
              f"{m.get('kapanan', 0)} kapanan  kazanma %{100 * (m.get('kazanma_orani') or 0):.0f}  kalite {m.get('kalite_puani', '—')}", flush=True)
    iyi = sorted((m for m in sonuc if m["karar"] == "kopyalanabilir"), key=lambda m: -m.get("skor", 0))
    with open(f"wallets_{z}_onerilen.txt", "w") as f:
        f.write("# Kârlılık analizinden geçen cüzdanlar (en iyisi önce)\n"); f.writelines(m["wallet"] + "\n" for m in iyi)
    with open(f"evm_analiz_{z}.json", "w") as f: json.dump(sonuc, f, ensure_ascii=False, indent=1, default=str)
    kararlar = Counter(m["karar"] for m in sonuc)
    print("Sonuç: " + ", ".join(f"{k}: {v}" for k, v in kararlar.most_common()) + f" -> wallets_{z}_onerilen.txt")
    if "--ekle" in argv and iyi:
        hedef = ekosistem.bul(z)["cuzdan_dosyasi"]
        if os.path.exists(hedef): shutil.copy(hedef, hedef + ".yedek")
        yeni = [m["wallet"] for m in iyi if m["wallet"] not in mevcut][:EKLE]
        with open(hedef, "a") as f: f.writelines(w + "\n" for w in yeni)
        print(f"{hedef} dosyasına {len(yeni)} kopyalanabilir cüzdan eklendi; {c['ad']} takibi bir dakika içinde başlar (paper).")
    return iyi


if __name__ == "__main__":
    main(sys.argv[1:])

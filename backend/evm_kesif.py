"""EVM cüzdan keşfi (PAPER, salt okunur): yükselen token'ları erken alan gerçek kullanıcı cüzdanları.
  python evm_kesif.py bnb                 # adaylar -> wallets_bnb_kesif.txt (takip listesine DOKUNMAZ)
  python evm_kesif.py bnb --ekle          # ilk 5 adayı wallets_bnb.txt'e ekler (yedekli); takip kendiliğinden başlar
  EVM_KESIF_TOKEN=15 EVM_KESIF_EN_AZ=2 python evm_kesif.py bnb
Not: kârlılık analizi henüz yok (cüzdan işlem geçmişi için NodeReal anahtarı gerekir); eklenenler paper'da ölçülür."""
import os, shutil, sys
import requests
from nexora import ekosistem
from nexora.evm import ZINCIRLER, EvmRpc
from nexora import evm_kesif as K

TOKEN = int(os.getenv("EVM_KESIF_TOKEN", "15")); EN_AZ = int(os.getenv("EVM_KESIF_EN_AZ", "2")); EKLE = 5


def main(argv, rpc=None, s=None):
    z = argv[0] if argv else "bnb"
    if z not in ZINCIRLER: sys.exit("zincir: bnb ya da base")
    c = ZINCIRLER[z]; rpc = rpc or EvmRpc(os.getenv(c["rpc_env"]) or c["rpc"]); s = s or requests.Session()
    tok = K.sicak_tokenler(s, z, TOKEN)
    if not tok: sys.exit("Uygun yükselen token bulunamadı (DexScreener yanıtı boş ya da filtreler sıkı).")
    print(f"{c['ad']}: {len(tok)} yükselen token, her birinin ilk ~30 dakikasındaki alıcılar inceleniyor…", flush=True)
    mevcut = ekosistem.cuzdanlar(z)
    adaylar, say = K.kesfet(rpc, tok, EN_AZ, bilinen=mevcut)
    dosya = f"wallets_{z}_kesif.txt"
    with open(dosya, "w") as f: f.writelines(w + "\n" for w in adaylar)
    print(f"{len(say)} farklı erken alıcı; {len(adaylar)} kullanıcı cüzdanı en az {EN_AZ} yükselen token'ı erken aldı -> {dosya}")
    for w in adaylar[:10]: print(f"   {w}  ({say[w]} token)")
    if "--ekle" in argv and adaylar:
        hedef = ekosistem.bul(z)["cuzdan_dosyasi"]
        if os.path.exists(hedef): shutil.copy(hedef, hedef + ".yedek")
        yeni = [w for w in adaylar if w not in mevcut][:EKLE]
        with open(hedef, "a") as f: f.writelines(w + "\n" for w in yeni)
        print(f"{hedef} dosyasına {len(yeni)} cüzdan eklendi; {c['ad']} takibi bir dakika içinde başlar (paper).")
    return adaylar


if __name__ == "__main__":
    main(sys.argv[1:])

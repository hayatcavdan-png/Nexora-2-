"""EVM ekosistemi takibi (PAPER): BNB Chain ya da Base cüzdanlarını izler ve ayrı sanal portföyde kopyalar.
  python evm_takip.py bnb        # cüzdanlar wallets_bnb.txt'ten, portföy nexora_bnb.db
  python evm_takip.py base       # cüzdanlar wallets_base.txt'ten, portföy nexora_base.db
Düğüm adresi: BNB_RPC_URL / BASE_RPC_URL (yoksa zincirin herkese açık düğümü). Gerçek emir YOK."""
import os, sys, time
from nexora import gizle as _gizle
_gizle.kur()
from nexora.core import Paper
from nexora import ekosistem
from nexora.evm import ZINCIRLER, EvmRpc, KyberTeklif, GoPlus, EvmHatasi
from nexora.evm_motor import EvmKarar, EvmTakip

ARALIK = int(os.getenv("EVM_ARALIK", "6"))
DEGERLE_SN = 120


def main(argv):
    z = argv[0] if argv else "bnb"
    if z not in ZINCIRLER: sys.exit(f"bilinmeyen zincir: {z} (bnb ya da base)")
    c = ZINCIRLER[z]
    rpc = EvmRpc(os.getenv(c["rpc_env"]) or c["rpc"])
    paper = Paper(f"nexora_{z}.db", kayma=0.0, ekosistem=z)
    k = EvmKarar(paper, rpc, KyberTeklif(z), GoPlus(z), z)
    son_deger, t = 0.0, None
    print(f"{c['ad']} takibi başladı (PAPER, gerçek emir KAPALI)", flush=True)
    while True:
        cuz = ekosistem.cuzdanlar(z)                       # dosya her turda okunur: cüzdan eklemek yeniden başlatma gerektirmez
        if not cuz:
            time.sleep(60); continue
        bas = time.time()
        try:
            if t is None or t.w != [w.lower() for w in cuz]: t = EvmTakip(rpc, k, cuz, z)
            for o in t.tur():
                print(f"  SİNYAL {o['yon']} {o['token'][:6]}…{o['token'][-4:]} cüzdan {o['cuzdan'][:6]}…{o['cuzdan'][-4:]} "
                      f"gecikme {o['yas']:.0f} sn -> {o['karar']} ({o['neden']})", flush=True)
            if time.time() - son_deger > DEGERLE_SN:
                k.degerle(); son_deger = time.time()
                for t, karar, neden in k.zaman_asimi():
                    print(f"  zaman aşımı: {t[:10]} -> {karar} ({neden})", flush=True)
            paper.nabiz()
        except EvmHatasi as e:
            print(f"  tur hatası: {e}", flush=True)
        except Exception as e:
            print(f"  beklenmeyen hata: {type(e).__name__}: {str(e)[:120]}", flush=True)
        time.sleep(max(1, ARALIK - (time.time() - bas)))


if __name__ == "__main__":
    main(sys.argv[1:])

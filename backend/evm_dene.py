"""EVM bağdaştırıcısı canlı denemesi (salt okunur): düğüm, KyberSwap teklifi ve GoPlus güvenlik yanıtlarının biçimini doğrular.
  python evm_dene.py bnb
Hiçbir işlem gönderilmez, anahtar kullanılmaz."""
import os, sys
from nexora.evm import ZINCIRLER, EvmRpc, KyberTeklif, GoPlus, EvmHatasi

ORNEK_CUZDAN = {"base": "0x3304e22ddaa22bcdc5fca2269b418046ae7b566a"}   # Base üzerinde bilinen etkin bir adres (yalnızca okuma denemesi)
ORNEK = {"bnb": "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82", "base": "0x940181a94a35a4569e4529a3cdfb74e38fd98631"}   # CAKE / AERO


def main(argv):
    z = argv[0] if argv else "bnb"; c = ZINCIRLER[z]; tamam = True
    rpc = EvmRpc(os.getenv(c["rpc_env"]) or c["rpc"])
    try:
        zid = int(rpc.call("eth_chainId", []), 16); n = rpc.blok()
        print(f"1) Düğüm: zincir {zid} ({'doğru' if zid == c['zincir_id'] else 'YANLIŞ'}), son blok {n}")
        tamam &= zid == c["zincir_id"]
        print(f"   Örnek token ondalığı: {rpc.ondalik(ORNEK[z])}")
    except EvmHatasi as e:
        print(f"1) Düğüm: HATA ({e})"); tamam = False
    try:
        q = KyberTeklif(z).teklif(c["usd"], ORNEK[z], 10 * 10 ** c["usd_ondalik"])
        print(f"2) KyberSwap: 10 USD -> {q['cikis_raw']} birim (girdi ≈ {q['giris_usd']:.2f} $, çıktı ≈ {q['cikis_usd']:.2f} $)")
    except EvmHatasi as e:
        print(f"2) KyberSwap: HATA ({e})"); tamam = False
    gp = GoPlus(z); g = gp.kontrol(ORNEK[z])
    print(f"3) GoPlus: {'uygun' if g['uygun'] else 'uygun değil'} · {', '.join(g['gerekceler'])} · likidite ≈ {g['likidite_usd']:,.0f} $")
    ham = gp.son_ham or {}
    dex = ham.get("dex")
    print(f"   GoPlus dex alanı: {type(dex).__name__}, {len(dex) if isinstance(dex, list) else '-'} öğe"
          + (f", ilk öğe anahtarları: {sorted(dex[0].keys())}" if isinstance(dex, list) and dex and isinstance(dex[0], dict) else ""))
    from nexora.evm import dexscreener_likidite
    import requests
    ds = dexscreener_likidite(requests.Session(), z, ORNEK[z])
    print(f"4) DexScreener likidite: {'HATA' if ds is None else f'≈ {ds:,.0f} $'}")
    tamam &= g["likidite_usd"] > 0
    if c.get("gezgin"):
        from nexora.evm import gezgin_islemleri
        try:
            son = rpc.blok()
            gi = gezgin_islemleri(requests.Session(), z, ORNEK_CUZDAN[z], son - 200_000, en_cok_sayfa=2)
            print(f"5) Gezgin (Blockscout): {'HATA (yanıt yok)' if gi is None else f'{len(gi)} işlem okundu'}")
        except Exception as ex:
            print(f"5) Gezgin (Blockscout): HATA ({type(ex).__name__})")
    tamam &= g["gerekceler"] != ["güvenlik bilgisi alınamadı"]
    print("SONUÇ: " + ("tüm parçalar çalışıyor" if tamam else "eksik parça var (yukarıdaki HATA satırları)"))
    return tamam


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1:]) else 1)

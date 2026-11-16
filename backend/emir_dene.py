"""N11 · Emir hattı denemesi (İMZASIZ, GÖNDERİMSİZ): Jupiter'den pilot cüzdan için işlem oluşturur, yapısını denetler,
zincirde simüle eder. Hiçbir emir gönderilmez, anahtar dosyası okunmaz.
  python emir_dene.py                    # 1 USDC -> SOL
  python emir_dene.py TOKEN_MINT 1.5     # 1.5 USDC -> token
Boş cüzdanda Jupiter işlem oluşturmaz ("bakiye yetersiz"): bu beklenen sonuçtur; hat yine de uçtan uca sınanmış olur."""
import os, sys

from nexora.constants import USDC_MINT, WSOL_MINT
from nexora.emir import EmirHazirlayici, EmirHatasi, denetle
from nexora.helius_client import HeliusClient, HeliusRPCError
import pilot_cuzdan


def main(argv, helius=None, session=None):
    taker = pilot_cuzdan.adres()
    cikis = argv[0] if argv else WSOL_MINT
    usd = float(argv[1]) if len(argv) > 1 else 1.0
    if not 0 < usd <= 5: sys.exit("deneme tutarı 0-5 USDC arası olmalı")
    h = EmirHazirlayici(helius or HeliusClient(max_retries=2), api_key=os.getenv("JUPITER_API_KEY", ""), session=session)
    print(f"Pilot cüzdan {taker[:4]}…{taker[-4:]} · {usd} USDC -> {cikis[:4]}…{cikis[-4:]} (GÖNDERİM YOK)")
    try:
        o = h.hazirla(USDC_MINT, cikis, int(round(usd * 10 ** 6)), taker)
    except EmirHatasi as e:
        print(f"  1) İşlem oluşturma: HATA ({e})"); return dict(asama="hazirla", hata=str(e))
    if not o["transaction"]:
        print(f"  1) İşlem oluşturma: Jupiter işlem vermedi: {o['hata']} (yönlendirici {o['router']})")
        print("     Boş cüzdanda beklenen sonuç. Hat çalışıyor; simülasyon için cüzdanda bakiye gerekir.")
        return dict(asama="hazirla", **{k: o[k] for k in ("hata", "router")})
    print(f"  1) İşlem oluşturma: tamam (yönlendirici {o['router']}, beklenen çıktı {o['out_amount']}, ücret {o['ucret_bps']} bps)")
    sorun, c = denetle(o["transaction"], taker)
    print(f"  2) Yapı denetimi: " + ("geçti" if not sorun else "SORUN: " + "; ".join(sorun))
          + f" (sürüm {c['surum']}, {len(c['hesaplar'])} hesap, {c['imzaci_sayisi']} imzacı)")
    if sorun: return dict(asama="denetle", sorun=sorun)
    try:
        s = h.simule(o["transaction"])
    except (EmirHatasi, HeliusRPCError) as e:
        print(f"  3) Simülasyon: HATA ({str(e)[:100]})"); return dict(asama="simule", hata=str(e))
    print(f"  3) Simülasyon: {'BAŞARILI' if s['basarili'] else 'başarısız: ' + str(s['hata'])[:100]} ({s['birim']} hesaplama birimi)")
    if not s["basarili"]:
        for l in s["gunluk"]: print("     " + l[:110])
    return dict(asama="simule", basarili=s["basarili"])


if __name__ == "__main__":
    main(sys.argv[1:])

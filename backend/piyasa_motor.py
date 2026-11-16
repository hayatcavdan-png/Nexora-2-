"""Platform 2 · piyasa stratejileri motoru (PAPER). Sunucuda nexora-piyasa servisi olarak sürekli çalışır.
  python piyasa_motor.py            # her 60 sn bir tur
  python piyasa_motor.py --tek      # tek tur (deneme)
Her strateji ayrı veritabanında: nexora_strateji_<ad>.db. Gerçek emir yok."""
import os, sys, time
from nexora import gizle as _gizle
_gizle.kur()
from nexora.core import Paper
from nexora import piyasa

ARALIK = int(os.getenv("PIYASA_ARALIK", "60"))


def portfoyler():
    return {st.ad: Paper(f"nexora_strateji_{st.ad}.db", kayma=piyasa.KAYMA, ucret_orani=piyasa.UCRET) for st in piyasa.STRATEJILER}


def main(argv):
    m = piyasa.Motor(portfoyler())
    print(f"Piyasa motoru başladı: {', '.join(s.ad for s in piyasa.STRATEJILER)} (PAPER, gerçek emir KAPALI)", flush=True)
    while True:
        bas = time.time()
        try:
            olay, d = m.tur()
            for ad, yon, token, neden in olay: print(f"  [{ad}] {yon.upper()} {token} · {neden}", flush=True)
            if int(bas) % 900 < ARALIK:
                print(f"  evren {d['evren']} coin · borsalar {d['borsalar']} · BTC kıyas {d['kiyas_btc_pct']}", flush=True)
        except Exception as e:
            print(f"  tur hatası: {type(e).__name__}: {str(e)[:120]}", flush=True)
        if "--tek" in argv: return
        time.sleep(max(5, ARALIK - (time.time() - bas)))


if __name__ == "__main__":
    main(sys.argv[1:])

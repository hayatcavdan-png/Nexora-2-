"""Hyperliquid gölge takip servisi (nexora-hl). SALT OKUNUR: işlem yok, anahtar yok, yalnızca herkese açık info API.
  python3 hl_takip.py            # servis döngüsü
  python3 hl_takip.py kesif      # liderlik tablosundan cüzdan listesini yenile (hl_cuzdanlar.txt) ve yazdır
  python3 hl_takip.py rapor      # ölçüm raporu
Liste günde bir kez otomatik yenilenir; listeden çıkan cüzdanın açık ölçümleri kapanana kadar izlenmeye devam eder."""
import os, sys, time

from nexora import hl

TUR_SN = int(os.getenv("HL_TUR_SN", "75"))
LISTE = "hl_cuzdanlar.txt"
DB = os.getenv("HL_DB", "nexora_hl.db")


def kesif(ist=None):
    ist = ist or hl.Istemci()
    sec = hl.sec(ist.lider(), n=int(os.getenv("HL_CUZDAN", "40")))
    if sec: hl.liste_yaz(sec, LISTE)
    return sec


def main(argv):
    if argv[:1] == ["kesif"]:
        s = kesif(); print(f"{len(s)} cüzdan seçildi -> {LISTE}"); [print(" ", w) for w in s]; return
    if argv[:1] == ["rapor"]:
        print("\n".join(hl.satirlar(hl.rapor(DB)))); return
    o = hl.Olcer(DB); son_kesif = 0; son_yaz = 0
    print("Hyperliquid gölge takip başladı (PAPER ölçüm, işlem yok)", flush=True)
    while True:
        now = time.time()
        if now - son_kesif > 86400 or not hl.liste_oku(LISTE):
            try:
                s = kesif(o.ist); print(f"Liste yenilendi: {len(s)} cüzdan", flush=True)
            except Exception as e:
                print(f"Liste yenilenemedi: {type(e).__name__}: {str(e)[:80]}", flush=True)
            son_kesif = now
        acik = [r[0] for r in o.db.execute("SELECT DISTINCT wallet FROM hl_sinyal WHERE durum='acik'")]
        cuz = list(dict.fromkeys(hl.liste_oku(LISTE) + acik))
        try:
            r = o.tur(cuz)
            if now - son_yaz > 1800 or r["acilan"] or r["kapanan"]:
                print(f"{time.strftime('%H:%M')} {len(cuz)} cüzdan: açılan {r['acilan']}, kapanan {r['kapanan']}, hata {r['hata']}", flush=True)
                son_yaz = now
        except Exception as e:
            print(f"Tur hatası: {type(e).__name__}: {str(e)[:100]}", flush=True)
        time.sleep(max(5, TUR_SN - (time.time() - now)))


if __name__ == "__main__":
    main(sys.argv[1:])

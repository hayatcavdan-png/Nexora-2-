"""Veri yedeği (N13): paper ve takip veritabanlarının tutarlı kopyası + cüzdan listeleri, tek .tar.gz dosyası.
Çalışırken alınabilir (SQLite yedek API'si). Anahtarlar YEDEĞE GİRMEZ.
Çalıştır (backend klasöründe): python yedek.py            -> yedekler/nexora_YYYYmmdd_HHMMSS.tar.gz
                               python yedek.py --geri DOSYA -> yedeği bu klasöre açar (takip ve sunucu DURMUŞ olmalı)"""
import glob, os, sqlite3, sys, tarfile, tempfile, time

DBLER = ["nexora_paper.db", "nexora_tracker.db", "nexora_etiket.db"]
DOSYALAR = ["wallets.txt", "kara_liste.txt", "cuzdan_analiz.csv", "cuzdan_tarama.csv", "takip_kaybi.json", "wallets_onerilen.txt"]
SAKLA = int(os.getenv("YEDEK_SAKLA", "14"))


def yedekle(kok=".", hedef="yedekler", sakla=SAKLA, simdi=None):
    os.makedirs(os.path.join(kok, hedef), exist_ok=True)
    ad = time.strftime("nexora_%Y%m%d_%H%M%S", time.localtime(simdi if simdi is not None else time.time()))
    yol = os.path.join(kok, hedef, ad + ".tar.gz")
    with tempfile.TemporaryDirectory() as gecici, tarfile.open(yol, "w:gz") as tar:
        for db in DBLER:
            kaynak = os.path.join(kok, db)
            if not os.path.exists(kaynak): continue
            kopya = os.path.join(gecici, db)
            src = sqlite3.connect(f"file:{kaynak}?mode=ro", uri=True, timeout=10)
            dst = sqlite3.connect(kopya)
            try:
                src.backup(dst)
            finally:
                dst.close(); src.close()
            tar.add(kopya, arcname=db)
        for f in DOSYALAR:
            if os.path.exists(os.path.join(kok, f)): tar.add(os.path.join(kok, f), arcname=f)
    eski = sorted(glob.glob(os.path.join(kok, hedef, "nexora_*.tar.gz")))
    for f in eski[:-sakla] if sakla > 0 else []: os.remove(f)
    return yol


def geri_yukle(dosya, kok="."):
    izinli = set(DBLER) | set(DOSYALAR)
    with tarfile.open(dosya, "r:gz") as tar:
        uyeler = [m for m in tar.getmembers() if m.isfile() and m.name in izinli]   # yol hilesine karşı yalnız bilinen adlar
        for m in uyeler:
            hedef = os.path.join(kok, m.name)
            if os.path.exists(hedef): os.replace(hedef, hedef + ".once")
            with tar.extractfile(m) as kaynak, open(hedef, "wb") as cikti: cikti.write(kaynak.read())
    return [m.name for m in uyeler]


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--geri":
        adlar = geri_yukle(sys.argv[2])
        print("Geri yüklendi:", ", ".join(adlar) or "(hiçbiri)", "· eski dosyalar .once uzantısıyla saklandı")
    else:
        y = yedekle()
        print(f"Yedek alındı: {y} ({os.path.getsize(y) // 1024} KB)")

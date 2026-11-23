"""N11 · Pilot (bot) cüzdanı: anahtar SUNUCUDA üretilir ve sunucudan çıkmaz. Ekrana yalnızca açık adres yazılır.
  python pilot_cuzdan.py olustur     # yeni anahtar; dosya zaten varsa ASLA üzerine yazmaz
  python pilot_cuzdan.py adres       # açık adresi gösterir
Anahtar dosyası Solana CLI biçimindedir (64 baytlık JSON dizi), izni 600, yolu PILOT_ANAHTAR (varsayılan /var/lib/nexora/pilot.json).
Açık adres ayrıca pilot_adres.txt'e yazılır (simülasyon araçları anahtar dosyasını hiç okumaz).
Bu cüzdana para göndermek ve ilk gerçek emir ayrı kararlardır (N12)."""
from nexora.dosya import json_oku, metin_oku, bayt_oku
import json, os, sys

from nexora.ed25519 import acik_anahtar, b58

ANAHTAR = os.getenv("PILOT_ANAHTAR", "/var/lib/nexora/pilot.json")
ADRES = os.getenv("PILOT_ADRES", "pilot_adres.txt")


def olustur(anahtar=ANAHTAR, adres_yolu=ADRES, rastgele=os.urandom):
    if os.path.exists(anahtar):
        raise SystemExit(f"{anahtar} zaten var: üzerine yazılmadı. Adres için: python pilot_cuzdan.py adres")
    klasor = os.path.dirname(anahtar)
    if klasor and not os.path.isdir(klasor):
        raise SystemExit(f"{klasor} yok. Önce: sudo install -d -o nexora -g nexora -m 700 {klasor}")
    tohum = rastgele(32)
    acik = acik_anahtar(tohum)
    fd = os.open(anahtar, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # yarış durumunda da üzerine yazmaz
    with os.fdopen(fd, "w") as f: json.dump(list(tohum + acik), f)
    adres = b58(acik)
    with open(adres_yolu, "w") as f: f.write(adres + "\n")
    return adres


def adres(anahtar=ANAHTAR, adres_yolu=ADRES):
    if os.path.exists(adres_yolu):
        return metin_oku(adres_yolu).strip()
    if not os.path.exists(anahtar): raise SystemExit("Pilot cüzdan yok. Oluşturmak için: python pilot_cuzdan.py olustur")
    b = bytes(json_oku(anahtar))
    if len(b) != 64 or acik_anahtar(b[:32]) != b[32:]: raise SystemExit("anahtar dosyası bozuk")
    a = b58(b[32:])
    with open(adres_yolu, "w") as f: f.write(a + "\n")
    return a


if __name__ == "__main__":
    komut = sys.argv[1] if len(sys.argv) > 1 else "adres"
    if komut == "olustur":
        a = olustur()
        print(f"Pilot cüzdan oluşturuldu.\nAçık adres: {a}\nGizli anahtar yalnızca sunucuda: {ANAHTAR} (izin 600). Kimseyle paylaşmayın.")
    elif komut == "adres":
        print(adres())
    else:
        sys.exit("Kullanım: python pilot_cuzdan.py olustur | adres")

"""Platform 2 (borsa) cüzdan keşfi: dört borsada listeli Solana token'larını SON SAATLERDE alan cüzdanları bulur,
birden çok listeli token'da görünenleri kârlılık analizinden geçirir. Takip listesine DOKUNMAZ; öneri üretir.

  python borsa_liste.py          # önce: borsa_tokenleri.json (günde bir)
  python borsa_kesif.py          # sonra: wallets_borsa_onerilen.txt
  BORSA_KESIF_TOKEN=20 BORSA_KESIF_SAAT=6 BORSA_KESIF_EN_AZ=2 python borsa_kesif.py
Eklemek için wallets_borsa.txt'e elle kopyalayın (ya da: python borsa_kesif.py --ekle  -> en fazla 5, yedekli).
Maliyet: token başına ≈ 10 Helius kredisi + aday başına ≈ 20 (analiz)."""
import os, shutil, sys
from collections import Counter

from nexora import borsa_liste
from nexora.helius_client import HeliusClient, HeliusRPCError
import cuzdan_kesif, cuzdan_analiz

TOKEN = int(os.getenv("BORSA_KESIF_TOKEN", "20"))
SAAT = int(os.getenv("BORSA_KESIF_SAAT", "6"))
EN_AZ = int(os.getenv("BORSA_KESIF_EN_AZ", "2"))
ADAY, ONERI, LISTE = "wallets_borsa_kesif.txt", "wallets_borsa_onerilen.txt", "wallets_borsa.txt"
EKLE_EN_FAZLA = 5


def secilen_tokenler(liste, n):
    """En hacimli n token (tüm borsalardaki toplam 24 saat hacmi)."""
    hacim = lambda t: sum(b.get("hacim_usd") or 0 for b in t["borsalar"].values())
    return sorted(liste, key=lambda m: -hacim(liste[m]))[:n]


def kesfet(client, liste, n=TOKEN, saat=SAAT, en_az=EN_AZ, now=None, alicilar=None):
    import time
    now = now or time.time()
    alicilar = alicilar or (lambda m: cuzdan_kesif.erken_alicilar(client, m, int(now), pencere=saat * 3600)[0])
    say, bilinen = Counter(), set(cuzdan_kesif.read_list(LISTE)) | set(cuzdan_kesif.read_list("wallets.txt")) \
                                | set(cuzdan_kesif.read_list("kara_liste.txt"))
    for m in secilen_tokenler(liste, n):
        try:
            for w in alicilar(m): say[w] += 1
        except (HeliusRPCError, ValueError, OSError) as e:
            print(f"  {liste[m]['sembol']}: okunamadı ({str(e)[:60]})", flush=True)
    aday = [w for w, c in say.most_common() if c >= en_az and w not in bilinen]
    return aday, say


def ekle(oneriler, en_fazla=EKLE_EN_FAZLA):
    mevcut = cuzdan_kesif.read_list(LISTE)
    yeni = [w for w in oneriler if w not in mevcut][:en_fazla]
    if not yeni: return []
    if os.path.exists(LISTE): shutil.copy(LISTE, LISTE + ".yedek")
    with open(LISTE, "a") as f:
        for w in yeni: f.write(w + "\n")
    return yeni


def main(argv=(), client=None, analiz=None):
    liste = borsa_liste.yukle()
    if not liste: sys.exit("borsa_tokenleri.json yok: önce  python borsa_liste.py")
    if client is None and not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil")
    client = client or HeliusClient(max_retries=2)
    print(f"{min(TOKEN, len(liste))} listeli token, son {SAAT} saatin alıcıları (≈ {min(TOKEN, len(liste)) * 10} Helius kredisi)", flush=True)
    aday, say = kesfet(client, liste)
    with open(ADAY, "w") as f: f.writelines(w + "\n" for w in aday)
    print(f"{len(say)} farklı alıcı; {len(aday)} aday en az {EN_AZ} listeli token'da göründü", flush=True)
    if not aday: return []
    rows = (analiz or (lambda: cuzdan_analiz.main(list_path=ADAY, yaz_oneri=False)))() or []
    iyi = sorted((r for r in rows if r.get("karar") == "kopyalanabilir"), key=lambda r: -(r.get("skor") or 0))
    with open(ONERI, "w") as f:
        f.write("# Platform 2 (borsa) için kârlılık analizinden geçen cüzdanlar. wallets_borsa.txt'e eklemeden önce gözden geçirin.\n")
        f.writelines(r["wallet"] + "\n" for r in iyi)
    print(f"Borsa platformu için {len(iyi)} kopyalanabilir cüzdan -> {ONERI}", flush=True)
    if "--ekle" in argv:
        yeni = ekle([r["wallet"] for r in iyi])
        print(f"wallets_borsa.txt'e {len(yeni)} cüzdan eklendi (yedek: {LISTE}.yedek). Etkin olması için: takibi yeniden başlatın (guncelle)."
              if yeni else "Eklenecek yeni cüzdan yok.", flush=True)
    return iyi


if __name__ == "__main__":
    main(sys.argv[1:])

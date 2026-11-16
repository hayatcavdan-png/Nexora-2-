"""Analizden geçen cüzdanları takibe ekler (N3). Yalnızca paper takibini etkiler.

Varsayılan KURU çalışmadır: ne ekleneceğini gösterir, hiçbir dosyayı değiştirmez.
  python cuzdan_ekle.py                 # wallets_onerilen.txt'ten ilk EKLE_EN_FAZLA aday, kuru
  python cuzdan_ekle.py --uygula        # wallets.txt'in yedeğini alıp ekler
  python cuzdan_ekle.py --geri          # son yedeği geri yükler
Kurallar: adres biçimi geçerli, kara listede değil, zaten takipte değil, cuzdan_analiz.csv'de karar 'kopyalanabilir'.
Takip servisinin yeni listeyi okuması için yeniden başlatılması gerekir (sunucuda: sudo systemctl restart nexora-takip)."""
import csv, os, re, shutil, sys, time

ADDR = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
EN_FAZLA = int(os.getenv("EKLE_EN_FAZLA", "5"))
TAKIP_SINIRI = int(os.getenv("TAKIP_SINIRI", "25"))


def oku(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]


def onayli(csv_path):
    if not os.path.exists(csv_path): return {}
    with open(csv_path, newline="") as f:
        return {r["wallet"]: r for r in csv.DictReader(f) if r.get("karar") == "kopyalanabilir"}


def secim(oneriler, mevcut, kara, analiz, en_fazla=EN_FAZLA, sinir=TAKIP_SINIRI):
    """(eklenecekler, atlananlar[(adres, neden)])"""
    ekle, atla, gorulen = [], [], set(mevcut)
    for w in oneriler:
        if not ADDR.match(w): atla.append((w, "geçersiz adres")); continue
        if w in gorulen: atla.append((w, "zaten takipte")); continue
        if w in kara: atla.append((w, "kara listede")); continue
        if w not in analiz: atla.append((w, "analizde kopyalanabilir değil")); continue
        if len(ekle) >= en_fazla: atla.append((w, f"tur sınırı ({en_fazla})")); continue
        if len(mevcut) + len(ekle) >= sinir: atla.append((w, f"takip sınırı ({sinir})")); continue
        ekle.append(w); gorulen.add(w)
    return ekle, atla


def main(argv, kok="."):
    p = lambda n: os.path.join(kok, n)
    hedef, yedek = p("wallets.txt"), p("wallets.txt.yedek")
    if "--geri" in argv:
        if not os.path.exists(yedek): sys.exit("Yedek yok.")
        shutil.copy2(yedek, hedef); print("wallets.txt yedekten geri yüklendi."); return []
    mevcut, kara = oku(hedef), set(oku(p("kara_liste.txt")))
    analiz = onayli(p("cuzdan_analiz.csv"))
    ekle, atla = secim(oku(p("wallets_onerilen.txt")), mevcut, kara, analiz)
    print(f"Takipte {len(mevcut)} cüzdan. Eklenecek {len(ekle)}:")
    for w in ekle:
        r = analiz[w]
        print(f"  + {w[:4]}…{w[-4:]}  K/Z {float(r.get('gerceklesen_usd') or 0):+.0f}$  {r.get('kapanan')} satış  "
              f"kazanma %{100 * float(r.get('kazanma_orani') or 0):.0f}  KF {r.get('kar_faktoru')}  skor {r.get('skor')}")
    for w, neden in atla: print(f"  - {w[:4]}…{w[-4:]}  atlandı: {neden}")
    if not ekle: print("Eklenecek cüzdan yok."); return []
    if "--uygula" not in argv:
        print("\nKuru çalışma: hiçbir şey değişmedi. Eklemek için --uygula ile çalıştırın."); return ekle
    if os.path.exists(hedef): shutil.copy2(hedef, yedek)
    with open(hedef, "a") as f:
        f.write(f"# {time.strftime('%Y-%m-%d %H:%M')} keşif + analizle eklendi\n")
        for w in ekle: f.write(w + "\n")
    print(f"\n{len(ekle)} cüzdan eklendi (yedek: wallets.txt.yedek). Takibi yeniden başlatın.")
    return ekle


if __name__ == "__main__":
    main(sys.argv[1:])

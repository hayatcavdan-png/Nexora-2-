"""Takip listesindeki adreslerin gerçek kullanıcı cüzdanı olup olmadığını denetler (N3). Salt okunur.
  python hesap_denetim.py                # wallets.txt
  python hesap_denetim.py liste.txt
Maliyet: 100 adres başına tek getMultipleAccounts isteği. Etiketli adresler için bilinen_hesaplar.txt ('adres # etiket')."""
import os, sys
from nexora import hesap_turu
from nexora.helius_client import HeliusClient, HeliusRPCError


def oku(path):
    if not os.path.exists(path): sys.exit(f"{path} yok")
    with open(path) as f: return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def main(argv, client=None):
    liste = argv[0] if argv else "wallets.txt"
    adresler = oku(liste)
    client = client or HeliusClient(max_retries=2)
    try:
        s = hesap_turu.siniflandir(client, adresler, hesap_turu.bilinenler())
    except (HeliusRPCError, ValueError) as e:
        sys.exit(f"Denetlenemedi: {str(e)[:80]}")
    sorunlu = {a: t for a, t in s.items() if t[0] != hesap_turu.KULLANICI}
    print(f"{liste}: {len(s)} adres, {len(s) - len(sorunlu)} kullanıcı cüzdanı")
    for a, (t, why) in s.items():
        print(f"  {'✓' if t == hesap_turu.KULLANICI else '✗'} {a[:4]}…{a[-4:]}  {t}" + ("" if t == hesap_turu.KULLANICI else f" ({why})"))
    if sorunlu: print("\nKullanıcı cüzdanı olmayan adresler kopyalanmamalı: wallets.txt'ten çıkarmayı düşünün (otomatik çıkarılmaz).")
    return s


if __name__ == "__main__":
    main(sys.argv[1:])

"""Token özelliklerine göre sonuçlar: yaş, likidite, organik skor, sahip yoğunlaşması (salt okunur).
Kopyalanan pozisyonlar ve gölge işlemler birlikte sayılır. Yalnızca ölçümdür; işlem kuralı değişmez.
Çalıştır (backend klasöründe): python token_filtre.py"""
import os, sys

from nexora.rapor import _ro, _rows, bilgi_summary


def report(path):
    c = _ro(path)
    if c is None: return "Paper veritabanı yok: önce takip çalışmalı."
    try:
        iz = _rows(c, "SELECT * FROM pos_iz"); sh = _rows(c, "SELECT * FROM shadow"); b = _rows(c, "SELECT * FROM token_bilgi")
    finally:
        c.close()
    if not b: return "Henüz ölçüm yok: yeni sürüm takip çalışırken yapılan alımlar ölçülmeye başlar."
    t = bilgi_summary(iz, sh, b)
    L = [f"Ölçülen alım: {t['olculen']} (bilgi alınamayan {t['hatali']}, Jupiter'in şüpheli işaretlediği {t['sus']})",
         f"Sonucu belli olan (kapanmış) örnek: {t['kapanan_ornek']}"]
    for bo in t["boyutlar"]:
        if not bo["gruplar"]: continue
        L += ["", bo["boyut"], f"  {'grup':<16}{'örnek':>6}{'kopya':>6}{'gölge':>6}{'kazanan':>8}{'ort. getiri':>12}"]
        for x in bo["gruplar"]:
            L.append(f"  {x['grup']:<16}{x['ornek']:>6}{x['kopya']:>6}{x['golge']:>6}{x['kazanan']:>8}{x['ort_getiri']:>+11.1f}%")
    L += ["", "Not: bir grupta 20 kapanmış örnek olmadan filtre kararı verilmez. Bu yalnızca ölçümdür."]
    return "\n".join(L)


if __name__ == "__main__":
    print(report(sys.argv[1] if len(sys.argv) > 1 else os.getenv("NEXORA_DB", "nexora_paper.db")))

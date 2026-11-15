"""Zarar kesme (stop-loss) ölçüm raporu: kopyalanan pozisyonlarda "%X zararda satsaydık ne olurdu?" (salt okunur).
İşlem davranışını değiştirmez; yalnızca takip sırasında kaydedilen değerlemeleri okur.
Çalıştır (backend klasöründe): python zarar_kesme.py"""
import os, sys

from nexora.rapor import _ro, _rows, stop_summary


def report(path):
    c = _ro(path)
    if c is None: return "Paper veritabanı yok: önce takip çalışmalı."
    try:
        iz = _rows(c, "SELECT * FROM pos_iz ORDER BY id")
        tetik = _rows(c, "SELECT * FROM stop_tetik")
    finally:
        c.close()
    if not iz: return "Henüz ölçüm yok: yeni sürüm takip çalışırken açılan pozisyonlar ölçülmeye başlar."
    z = stop_summary(iz, tetik)
    L = [f"Ölçülen pozisyon: {z['kapanan']} kapanmış, {z['acik']} açık"
         + (f" ({z['eksik']} tanesi bu sürümden önce açıldı, başlangıcı eksik)" if z["eksik"] else ""),
         f"Gerçekleşen toplam K/Z (kaynak satınca satarak): {z['gercek_kz']:+.2f}$"]
    if z["en_dusuk_ort"] is not None:
        L.append(f"Pozisyon başına ortalama en kötü an %{z['en_dusuk_ort']:+.1f}, en iyi an %{z['en_yuksek_ort']:+.1f}")
    L += ["", f"{'Eşik':<7}{'tetik':>6}{'korudu':>8}{'kaçırdı':>9}{'stoplu K/Z':>12}{'fark':>9}"]
    for x in z["esikler"]:
        L.append(f"%{x['esik']:<6}{x['tetiklenen']:>6}{x['korudu']:>8}{x['kacirdi']:>9}{x['stoplu_kz']:>+11.2f}${x['fark']:>+8.2f}$")
    if z["acik_tetik"]:
        L.append(f"\nAçık pozisyonlarda {z['acik_tetik']} eşik tetiği var (pozisyon kapanınca sonuca katılır).")
    L += ["", "korudu: zarar kesme daha az zararla çıkardı. kaçırdı: fiyat sonradan toparlandı, zarar kesme daha kötü olurdu.",
          "Değerleme 2 dakikada bir yapılır; gerçek zarar kesme eşiğin biraz altında da dolabilir.",
          "Not: 20 kapanmış pozisyondan önce sonuç güvenilir değildir; bu yalnızca ölçümdür, işlem kuralı değişmedi."]
    return "\n".join(L)


if __name__ == "__main__":
    print(report(sys.argv[1] if len(sys.argv) > 1 else os.getenv("NEXORA_DB", "nexora_paper.db")))

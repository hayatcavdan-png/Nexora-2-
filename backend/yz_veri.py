"""N17 · Yapay zekâ verisi raporu (salt okunur): veri kalitesi, temel çizgiler ve CSV dışa aktarımı.
Çalıştır (backend klasöründe): python yz_veri.py            -> rapor + yz_veri.csv
Ufuk seçimi: YZ_UFUK=kaynak (varsayılan) | 30dk | 5dk"""
import csv, os, sys

from nexora.ozellik import veri_seti, temel_cizgiler, kalite, OZELLIKLER


def rapor(db, ufuk="kaynak", csv_yol="yz_veri.csv"):
    v = veri_seti(db, ufuk)
    if not v: return "Henüz etiketli veri yok: N16 etiketleme motoru veri topladıkça dolacak."
    q = kalite(v)
    L = [f"Ufuk: {ufuk} · etiketli örnek {q['n']} · kazanan %{q['kazanan_pct']} · {q['cuzdan_sayisi']} cüzdan, {q['gun_sayisi']} gün",
         f"En çok örnek veren cüzdanın payı %{q['en_cok_cuzdan_payi']}" + ("  (UYARI: tek cüzdan baskın)" if q["en_cok_cuzdan_payi"] > 40 else ""),
         "", "Temel çizgiler (maliyet dahil ortalama getiri):"]
    for t in temel_cizgiler(v):
        L.append(f"  {t['yontem']:<36} n={t['n']:<5} ort. %{t['ort_getiri'] if t['ort_getiri'] is not None else '—'}  kazanan %{t['kazanan_pct']}")
    yuksek = [(k, p) for k, p in q["eksik_pct"].items() if p > 10]
    L += ["", "Eksik değeri %10'u aşan özellikler: " + (", ".join(f"{k} %{p}" for k, p in yuksek) if yuksek else "yok")]
    with open(csv_yol, "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["ts", "event_id", "wallet"] + OZELLIKLER + ["getiri_pct"])
        for ts, e, w, o, y in v: wr.writerow([ts, e, w] + [o[k] for k in OZELLIKLER] + [y])
    L.append(f"\nDışa aktarıldı: {csv_yol}")
    return "\n".join(L)


if __name__ == "__main__":
    print(rapor(os.getenv("ETIKET_DB", "nexora_etiket.db"), os.getenv("YZ_UFUK", "kaynak")))

"""Yapay zekâ yönlendirici turu (N28): saatlik zamanlayıcıyla çalışır. Kaynak defterlerini yalnızca OKUR.
  python3 yonlendirici.py          tur at ve özeti yazdır
  python3 yonlendirici.py durum    yalnızca son durumu yazdır"""
import json, sys

from nexora.yonlendirici import Yonlendirici, kaynaklar


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    y, k = Yonlendirici(), kaynaklar()
    d = y.durum(k) if argv[:1] == ["durum"] else y.tur(k)
    if d.get("bos"): print("Henüz tur yok."); return d
    print(f"Yönlendirici: {d['deger']:.2f} (başlangıç 100) · getiri %{d['getiri_pct']:+.2f} · zirveden düşüş %{d['zirveden_dusus_pct']:.2f}"
          f" · nakit %{100 * d['nakit_pay']:.0f} · {d['olcum_gun']} gün")
    for s in d["kaynaklar"]:
        kr = s["karne"] or {}
        g = "—" if s["getiri_pct"] is None else f"%{s['getiri_pct']:+.2f}"
        print(f"  {s['ad']:<32} pay %{100 * s['pay']:>4.0f}  getiri {g:>8}  kapanan {kr.get('n', 0):>3}  "
              f"kazanma %{100 * kr.get('kazanma', 0):.0f}  ort. işlem %{100 * kr.get('ort_getiri', 0):+.2f}")
    with open("yonlendirici_durum.json", "w") as f: json.dump(d, f, ensure_ascii=False)
    return d


if __name__ == "__main__":
    main()

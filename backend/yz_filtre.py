"""N19/N20 · Model filtresi: gölge sonucu, aç/kapat (yalnızca paper kopyalamasını etkiler).
  python yz_filtre.py            # durum + gölge karar raporu (N19)
  python yz_filtre.py ac         # N19 kabulü sağlandıysa filtreyi açar; takip yeniden başlatılmadan da etkili olur
  python yz_filtre.py kapat      # geri alma: filtre kapanır, 'hepsini kopyala' davranışına dönülür
Kabul (ac için): en az 14 gün ve 100 etiketli gölge karar, seçilenlerin getirisi hepsininkinden iyi, belirgin kayma yok."""
import os, sys

from nexora import model_kapisi as mk


def metin(d):
    g = d["golge"]
    L = [f"Model filtresi: {'AÇIK' if d['acik'] else 'kapalı'}" + ("" if not d["acik"] or d["etkin"] else " (model yok: uygulanmıyor)"),
         f"Model: {d['model'] or 'yok (N18 kabul edilmiş model gerekir: yz_model.py)'}" + (f", eşik {d['esik']:.3f}" if d["esik"] is not None else "")]
    if not g.get("n"):
        L.append("Gölge karar (N19): henüz yok (model kaydedilince her yeni sinyal için yazılır)")
    else:
        f = lambda v: "—" if v is None else f"%{v:+.2f}"
        L += [f"Gölge karar (N19): {g['n']} sinyal, {g['etiketli']} etiketli, {g['gun']} gün, seçim oranı %{100 * g['secim_orani']:.0f}",
              f"  hepsi {f(g['hepsi_ort'])} · modelin seçtikleri {f(g['secili_ort'])} · seçmedikleri {f(g['secilmeyen_ort'])}",
              f"  kayma: {'—' if g['kayma'] is None else g['kayma']} · kabul için yeterli: {'evet' if g['yeterli'] else 'hayır'}"]
        L += [f"  kalibrasyon {k['aralik']}: n={k['n']} tahmin {k['tahmin']} gerçek {k['gercek']}" for k in g["kalibrasyon"]]
    return "\n".join(L)


def main(argv, etiket_db=None):
    etiket_db = etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db")
    komut = argv[0] if argv else "durum"
    if komut == "kapat":
        mk.filtre_kapat(); print("Model filtresi kapatıldı: kopyalama 'hepsini kopyala' kuralına döndü.")
    elif komut == "ac":
        try:
            mk.filtre_ac(mk.golge_rapor(etiket_db))
        except ValueError as e:
            sys.exit(f"Açılmadı: {e}")
        print("Model filtresi açıldı (paper). Geri almak için: python yz_filtre.py kapat (ya da uygulamadan).")
    elif komut != "durum":
        sys.exit("Kullanım: python yz_filtre.py [durum|ac|kapat]")
    d = dict(mk.ModelKapisi().durum(), golge=mk.golge_rapor(etiket_db))
    print(metin(d))
    return d


if __name__ == "__main__":
    main(sys.argv[1:])

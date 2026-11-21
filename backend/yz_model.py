"""N18 · Seçim modeli: zamana göre eğit/sına, maliyet sonrası 'hepsini kopyala' ile karşılaştır.
Çalıştır (backend klasöründe): python yz_model.py        # gece sınamasının kayıtlı raporu (anında)
                                python yz_model.py yeni   # şimdi yeniden sına (sunucuda birkaç dakika sürer)
En az 500 etiketli örnek gerekir (YZ_ZORLA=1 yalnızca deneme içindir; sonucu karar için kullanılmaz).
Kabul edilirse model yz_model.json'a yazılır (N19 gölge kararı bunu kullanır). İşlem kuralını DEĞİŞTİRMEZ."""
import os, sys, time

RAPOR = "yz_model_rapor.txt"

from nexora.ozellik import veri_seti
from nexora.model import degerlendir


def calistir(db, ufuk="kaynak", zorla=False, yol="yz_model.json"):
    v = veri_seti(db, ufuk)
    s, m = degerlendir(v, zorla=zorla)
    if s["karar"] == "yetersiz veri":
        return f"Yetersiz veri: {s['n']}/{s['gerekli']} etiketli örnek. N16 veri topladıkça yeniden deneyin."
    L = [f"Karar: {s['karar'].upper()}" + ("  (DENEME: örnek sayısı yetersiz)" if zorla and s["n"] < 500 else ""),
         f"Örnek {s['n']} (eğitim {s['egitim']}, sınama {s['sinama']} · zamana göre bölündü)",
         f"Sınamada 'hepsini kopyala' ortalaması %{s['sinama_hepsi_ort']:+.2f}",
         f"Model seçtiklerinin ({s['secilen']}) ortalaması " + ("—" if s["sinama_secili_ort"] is None else f"%{s['sinama_secili_ort']:+.2f}"),
         f"Farkın %95 güven aralığı: {s['fark_guven_araligi']}",
         (lambda k: f"Yalnızca kopyalanan cüzdanlar (canlı filtre bunlara uygulanır): {k['n']} sinyal, hepsi "
                    + ("—" if k["hepsi"] is None else f"%{k['hepsi']:+.2f}") + f"; model seçtikleri ({k['secilen']}) "
                    + ("—" if k["secili"] is None else f"%{k['secili']:+.2f}"))(s.get("kopya") or dict(n=0, hepsi=None, secilen=0, secili=None)),
         f"Olasılık doğruluğu (Brier, düşük iyi): model {s['brier']} · sabit tahmin {s['brier_taban']}",
         "Yürüyen sınama (dilim: seçilen − hepsi): " + (", ".join(
             f"%{int(100 * x['kesim'])}→ {'—' if x['fark'] is None else f'{x['fark']:+.2f}'} ({x['secilen']})" for x in s.get("ileri") or []) or "—"),
         f"Şans sınaması: etiketleri karıştırılmış modellerin gerçek farka ulaşma oranı p={s.get('p_sahte')} (0,1'den küçük olmalı)",
         "", "En etkili özellikler (standart etki; + kârlılık olasılığını artırır):"]
    L += [f"  {k:<16} {w:+.3f}" for k, w in s["agirliklar"]]
    L += ["", "Kalibrasyon (tahmin edilen / gerçekleşen kazanma oranı):"]
    L += [f"  {x['aralik']}  n={x['n']:<4} tahmin {x['tahmin']:.2f}  gerçek {x['gercek']:.2f}" for x in s["kalibrasyon"]]
    if m is not None and not zorla:
        m.kaydet(yol, dict(ufuk=ufuk, esik=s["esik"], sonuc={k: s[k] for k in ("n", "sinama_hepsi_ort", "sinama_secili_ort", "fark_guven_araligi")}))
        L.append(f"\nModel kaydedildi: {yol} (sıradaki adım N19: gölge karar)")
    elif s["karar"] != "avantaj var":
        L.append("\nModel kaydedilmedi: avantaj kanıtlanmadı. Bu geçerli bir sonuçtur; gerçek parayı korur.")
        if os.path.exists(yol):
            L.append(f"Not: {yol} daha önce kabul edilmiş eski bir model. Yalnızca gölge karar ölçümü için kalır; "
                     "bugünkü sınamayı geçemediği için canlı filtreye (N20) önerilmez.")
    metin = "\n".join(L)
    if not zorla:
        try:
            with open(RAPOR + ".tmp", "w") as f: f.write(f"Sınama zamanı: {time.strftime('%d.%m.%Y %H:%M', time.gmtime())} UTC\n{metin}\n")
            os.replace(RAPOR + ".tmp", RAPOR)
        except OSError:
            pass
    return metin


if __name__ == "__main__":
    if "yeni" not in sys.argv[1:] and os.path.exists(RAPOR) and os.getenv("YZ_ZORLA") != "1":
        print(open(RAPOR).read().rstrip()); print("\n(Gece sınamasının kayıtlı raporu. Şimdi yeniden sınamak için: yz_model.py yeni — birkaç dakika sürer)")
    else:
        print("Sınanıyor, sunucuda birkaç dakika sürebilir…", flush=True)
        print(calistir(os.getenv("ETIKET_DB", "nexora_etiket.db"), os.getenv("YZ_UFUK", "kaynak"), os.getenv("YZ_ZORLA") == "1"))

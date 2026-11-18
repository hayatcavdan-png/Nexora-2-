"""N18 zamanda ileri sınama ve kabul edilen kaynak modeli için yerel gölge çıktısı."""
import os
import time
from pathlib import Path

from nexora.model import degerlendir
from nexora.model_kapisi import GOLGE_MODEL_YOLU, MODEL_YOLU
from nexora.olcum import UFUKLAR
from nexora.ozellik import sinyalleri_oku


def calistir(db, ufuk="kaynak", zorla=False, yol=GOLGE_MODEL_YOLU):
    if ufuk not in (*UFUKLAR, "kaynak"):
        raise ValueError("ufuk geçersiz")
    sinyaller, _ = sinyalleri_oku(db)
    now = time.time()
    s, m = degerlendir(sinyaller, ufuk, zorla=zorla, now=now)
    if s["karar"] == "yetersiz veri":
        return f"Yetersiz veri: {s['n']}/{s['gerekli']} doğrulanmış etiketli örnek. Avantaj doğrulanamadı."
    L = [f"Karar: {s['karar'].upper()}" + (" (deneme)" if zorla else ""),
         f"Doğrulanmış örnek {s['n']} / olgun {s['olgun']} · {s['aile_n']} token ailesi"]
    if "egitim" in s:
        L.append(f"Eğitim {s['egitim']} · sınama {s['sinama']} · arındırılan {s['ayiklanan']}")
    if "brier" in s:
        L += [f"İşlem başına getiri farkının %95 blok aralığı {s['fark_guven_araligi']}",
              f"Brier {s['brier']:.4f} · sabit tahmin {s['brier_taban']:.4f} · kalibrasyon hatası {s['ece']:.4f}",
              f"Bot kararı dahil ablation Brier {s['bot_dahil_ablation']['brier']:.4f}"]
        for ad in ("model", "hepsi", "alim_yok", "ortak_model", "ortak_bot"):
            net = s["net"][ad]
            L.append(f"  {ad} · {net['secili']} seçim · sinyal başına {net['sinyal_basi_usdc']} USDC")
        L.extend(f"  Özellik {k} · standart etki {w:+.3f}" for k, w in s["agirliklar"])
        L.extend(f"  Kalibrasyon {b['aralik']} · n={b['n']} · tahmin {b['tahmin']} · gerçek {b['gercek']}"
                 for b in s["kalibrasyon"])
        L += [f"İleri pencere {i} · {p['egitim']} eğitim / {p['sinama']} sınama · {p['aile_n']} token ailesi"
              for i, p in enumerate(s["ileri_pencereler"], 1)]
    L += [f"  Yetersiz kanıt: {g}" for g in s["gerekceler"]]
    if m is not None and ufuk == "kaynak":
        if Path(yol).name == MODEL_YOLU or Path(yol).resolve() == Path(MODEL_YOLU).resolve():
            raise ValueError("N20 model dosyası V1 gölge çıktısı için kullanılamaz")
        m.kaydet(yol, dict(golge_v1=True, ufuk=ufuk, esik=s["esik"], son_veri_ts=now,
                           sonuc={k: s[k] for k in ("n", "sinama_hepsi_ort", "sinama_secili_ort", "fark_guven_araligi")}))
        L.append("Kaynak ufku modeli N19 V1 gölge ölçümü için kaydedildi.")
    return "\n".join(L)


if __name__ == "__main__":
    print(calistir(os.getenv("ETIKET_DB", "nexora_etiket.db"), os.getenv("YZ_UFUK", "kaynak"), os.getenv("YZ_ZORLA") == "1"))

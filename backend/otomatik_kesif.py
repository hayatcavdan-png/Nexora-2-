"""Günlük otomatik cüzdan keşfi (N3). Takip listesine DOKUNMAZ; yalnızca öneri üretir ve uygulamaya bildirir.

Sıra: keşif (KESIF_TOKEN=40, KESIF_SAYFA=5) -> hesap türü + kârlılık analizi -> ekleme ön izlemesi -> kesif_son.json.
Son 14 günde analiz edilmiş adaylar yeniden analiz edilmez (kesif_gorulen.json), böylece kredi boşa gitmez.
Tahmini maliyet: keşif ≈ 2.000 + yeni aday başına ≈ 20 Helius kredisi.
Sunucuda systemd zamanlayıcısı (nexora-kesif.timer) her gün çalıştırır. Elle:  python otomatik_kesif.py"""
import json, os, sys, time

os.environ.setdefault("KESIF_TOKEN", "40")
os.environ.setdefault("KESIF_SAYFA", "5")
import cuzdan_kesif, cuzdan_analiz, cuzdan_ekle  # noqa: E402

GORULEN, SON = "kesif_gorulen.json", "kesif_son.json"
GORULEN_TXT = "kesif_gorulen.txt"           # cuzdan_kesif.py bu listedekileri aday saymaz
TEKRAR_GUN = 14


def _oku_json(path, varsayilan):
    try:
        with open(path) as f: return json.load(f)
    except (OSError, ValueError):
        return varsayilan


def _yaz_json(path, veri):
    gecici = path + ".tmp"
    with open(gecici, "w") as f: json.dump(veri, f, ensure_ascii=False, indent=1)
    os.replace(gecici, path)


def calistir(kesif=None, analiz=None, now=None):
    now = now if now is not None else time.time()
    kesif = kesif or cuzdan_kesif.main
    analiz = analiz or (lambda: cuzdan_analiz.main(list_path=cuzdan_kesif.OUT_TXT))
    gorulen = {w: t for w, t in _oku_json(GORULEN, {}).items() if now - t < TEKRAR_GUN * 86400}
    with open(GORULEN_TXT, "w") as f:
        f.write("# otomatik_kesif.py: son 14 günde analiz edilen adaylar\n"); f.writelines(w + "\n" for w in gorulen)
    sonuc = dict(ts=now, durum="tamam", aday=0, analiz_edilen=0, kopyalanabilir=[], hata=None)
    try:
        aday = kesif() or []
        sonuc["aday"] = len(aday)
        if aday:
            rows = analiz() or []
            sonuc["analiz_edilen"] = len(rows)
            for r in rows: gorulen[r["wallet"]] = now
            kararlar = {}
            for r in rows: kararlar[r.get("karar", "?")] = kararlar.get(r.get("karar", "?"), 0) + 1
            sonuc["kararlar"] = kararlar
            mevcut = cuzdan_ekle.oku("wallets.txt")
            analiz_ok = cuzdan_ekle.onayli("cuzdan_analiz.csv")
            ekle, _ = cuzdan_ekle.secim([r["wallet"] for r in rows if r.get("karar") == "kopyalanabilir"],
                                        mevcut, set(cuzdan_ekle.oku("kara_liste.txt")), analiz_ok)
            for w in ekle:
                r = analiz_ok[w]
                sonuc["kopyalanabilir"].append(dict(
                    wallet=w, gerceklesen_usd=float(r.get("gerceklesen_usd") or 0), kapanan=int(float(r.get("kapanan") or 0)),
                    kazanma_orani=float(r.get("kazanma_orani") or 0), kar_faktoru=float(r.get("kar_faktoru") or 0),
                    medyan_tutma_sn=r.get("medyan_tutma_sn"), skor=float(r.get("skor") or 0)))
    except SystemExit as e:                     # araçlar "yapılacak iş yok" durumunda sys.exit ile çıkar
        sonuc["durum"], sonuc["hata"] = "atlandı", str(e.code)[:200] if e.code else None
    except Exception as e:                      # zamanlayıcıda çalışır: hata kaydedilir, bildirime düşer
        sonuc["durum"], sonuc["hata"] = "hata", f"{type(e).__name__}: {str(e)[:160]}"
    _yaz_json(GORULEN, gorulen)
    _yaz_json(SON, sonuc)
    print(f"Otomatik keşif: {sonuc['durum']}, {sonuc['aday']} aday, {sonuc['analiz_edilen']} analiz, "
          f"{len(sonuc['kopyalanabilir'])} yeni kopyalanabilir" + (f" ({sonuc['hata']})" if sonuc["hata"] else ""), flush=True)
    return sonuc


if __name__ == "__main__":
    s = calistir()
    sys.exit(1 if s["durum"] == "hata" else 0)

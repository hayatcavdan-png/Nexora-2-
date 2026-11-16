"""Günlük otomatik cüzdan keşfi (N3). Takip listesine DOKUNMAZ; yalnızca öneri üretir ve uygulamaya bildirir.

Sıra: keşif (KESIF_TOKEN=40, KESIF_SAYFA=5) -> hesap türü + kârlılık analizi -> ekleme ön izlemesi -> kesif_son.json.
Son 14 günde analiz edilmiş adaylar yeniden analiz edilmez (kesif_gorulen.json), böylece kredi boşa gitmez.
Tahmini maliyet: keşif ≈ 2.000 + yeni aday başına ≈ 20 Helius kredisi.
Sunucuda systemd zamanlayıcısı (nexora-kesif.timer) her gün çalıştırır. Elle:  python otomatik_kesif.py"""
import json, os, sys, time

os.environ.setdefault("KESIF_TOKEN", "40")
os.environ.setdefault("KESIF_SAYFA", "5")
import cuzdan_kesif, cuzdan_analiz, cuzdan_ekle  # noqa: E402
from nexora import analiz_gecmis  # noqa: E402

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


def takip_denetimi(analiz=None, gecmis_db=None):
    """Takipteki cüzdanları yeniden analiz eder (≈ cüzdan başına 20 kredi) ve bozulanları bildirir.
    Listeden kimseyi ÇIKARMAZ: karar sizde. wallets_onerilen.txt'e dokunmaz."""
    gecmis_db = gecmis_db or os.getenv("DNA_DB", "nexora_dna.db")
    takip = [w for w in cuzdan_ekle.oku("wallets.txt") if w not in set(cuzdan_ekle.oku("kara_liste.txt"))]
    if not takip: return dict(denetlenen=0, bozulan=[], iyi=0)
    analiz = analiz or (lambda: cuzdan_analiz.main(list_path="wallets.txt", yaz_oneri=False, gecmis_db=gecmis_db))
    rows = {r["wallet"]: r for r in (analiz() or [])}
    bozulan = []
    for w in takip:
        r = rows.get(w)
        if r is None or r.get("karar") in ("kopyalanabilir", "hata"): continue
        e = analiz_gecmis.egilim(gecmis_db, w)
        bozulan.append(dict(wallet=w, karar=r.get("karar"), gerekce=(r.get("gerekce") or "")[:160], kalite=r.get("kalite_puani"),
                            yeni=bool(e and e["durum"] == "bozuldu")))
    return dict(denetlenen=len(rows), bozulan=bozulan, iyi=sum(1 for r in rows.values() if r.get("karar") == "kopyalanabilir"))


def calistir(kesif=None, analiz=None, now=None, denetim=None, liste=None):
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
    try:                                        # keşif sonuç vermese de takip listesi her gün denetlenir
        sonuc["takip"] = (denetim or takip_denetimi)()
    except SystemExit as e:
        sonuc["takip"] = dict(denetlenen=0, bozulan=[], hata=str(e.code)[:160] if e.code else None)
    except Exception as e:
        sonuc["takip"] = dict(denetlenen=0, bozulan=[], hata=f"{type(e).__name__}: {str(e)[:120]}")
    try:                                        # Platform 2: borsa token listesi günde bir yenilenir
        from nexora import borsa_liste
        if not os.path.exists(borsa_liste.DOSYA) or now - os.path.getmtime(borsa_liste.DOSYA) > 20 * 3600:
            if (liste or borsa_liste.olustur)() is not None: sonuc["borsa_liste"] = "yenilendi"
    except Exception as e:
        sonuc["borsa_liste"] = f"yenilenemedi: {type(e).__name__}"
    _yaz_json(GORULEN, gorulen)
    _yaz_json(SON, sonuc)
    print(f"Otomatik keşif: {sonuc['durum']}, {sonuc['aday']} aday, {sonuc['analiz_edilen']} analiz, "
          f"{len(sonuc['kopyalanabilir'])} yeni kopyalanabilir" + (f" ({sonuc['hata']})" if sonuc["hata"] else "")
          + f"; takip denetimi: {sonuc['takip'].get('denetlenen', 0)} cüzdan, {len(sonuc['takip'].get('bozulan', []))} eşik altı", flush=True)
    return sonuc


if __name__ == "__main__":
    s = calistir()
    sys.exit(1 if s["durum"] == "hata" else 0)

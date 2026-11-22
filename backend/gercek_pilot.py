"""N12 · Gerçek pilotun kumandası (kurucunun KENDİ pilot cüzdanı; emanet yok).
  python3 gercek_pilot.py durum
  python3 gercek_pilot.py ac --islem 20 --butce 100 --poz 5 --gunluk 15 --durdurma 40 --onay GERCEK-PARA
  python3 gercek_pilot.py kapat              # yeni alım durur; açık gerçek pozisyonlar paper kapandıkça satılır
  python3 gercek_pilot.py sat-hepsi --onay GERCEK-PARA   # tüm gerçek pozisyonları hemen sat (acil çıkış)
Alım için ÇİFT KİLİT: /etc/nexora.env içinde GERCEK_ISLEM=1 (takip servisi bunu görünce pilotu bağlar) VE 'ac' komutu.
Pilot cüzdana USDC (işlemler için) ve biraz SOL (ağ ücreti, ~0,05 SOL) göndermek kullanıcının işidir; adres: durum."""
import argparse, os, sys, time

from nexora import gercek as G


def _pilot():
    from nexora.core import Paper
    from nexora.helius_client import HeliusClient
    return G.GercekPilot(Paper(os.getenv("NEXORA_DB", "nexora_paper.db")), HeliusClient(max_retries=2))


def durum_metni(o):
    a = o["ayar"]
    L = [f"Pilot cüzdan: {o['adres']}",
         f"Durum: {'AÇIK (gerçek alım yapıyor)' if o['etkin'] else 'KAPALI'}"
         + ("" if o["ortam"] else "  [GERCEK_ISLEM=1 değil: takip servisi pilotu bağlamaz]"),
         f"Ayar: işlem {a['islem_usd']}$, bütçe {a['butce_usd']}$, en fazla {a['en_fazla_poz']} pozisyon, "
         f"günlük zarar sınırı {a['gunluk_zarar_usd']}$, toplam zararda durdurma {a['durdurma_usd']}$",
         f"Açık gerçek pozisyon: {len(o['acik_poz'])} (maliyet {o['acik_maliyet']}$)",
         f"Kapanan: {o['kapanan']} (kazanan {o['kazanan']}) · gerçekleşen K/Z {o['toplam_kz']:+.2f}$ · bugün {o['bugun_kz']:+.2f}$"
         f" · başarısız/hatali deneme {o['basarisiz']}"]
    for s in o["son"][:10]:
        L.append(f"  {time.strftime('%d.%m %H:%M', time.localtime(s['ts']))} {s['yon']:<4} {s['token'][:6]}… {s['durum']:<9}"
                 + (f" {s['usd']:.2f}$" if s.get("usd") else "") + (f" K/Z {s['kz']:+.2f}$" if s.get("kz") is not None else "")
                 + (f" ({(s.get('hata') or '')[:60]})" if s["durum"] != "tamam" else ""))
    return "\n".join(L)


def main(argv):
    ap = argparse.ArgumentParser(); ap.add_argument("komut", choices=["durum", "ac", "kapat", "sat-hepsi"])
    for k in ("islem", "butce", "poz", "gunluk", "durdurma"): ap.add_argument("--" + k, type=float)
    ap.add_argument("--onay", default="")
    a = ap.parse_args(argv)
    if a.komut == "kapat":
        d = G.ayar_oku(); d["acik"] = False; G.ayar_yaz(d); print("Pilot KAPATILDI: yeni gerçek alım yok."); return
    if a.komut == "ac":
        if a.onay != "GERCEK-PARA": sys.exit("Gerçek para onayı gerekli: --onay GERCEK-PARA")
        d = G.ayar_oku()
        for k, alan in (("islem", "islem_usd"), ("butce", "butce_usd"), ("gunluk", "gunluk_zarar_usd"), ("durdurma", "durdurma_usd")):
            if getattr(a, k) is not None: d[alan] = float(getattr(a, k))
        if a.poz is not None: d["en_fazla_poz"] = int(a.poz)
        d["acik"] = True; d["acilis_ts"] = time.time()
        try:
            G.ayar_yaz(d)
        except G.GercekHata as e:
            sys.exit(f"Hata: {e}")
        print("Pilot AÇILDI." + ("" if os.getenv("GERCEK_ISLEM") == "1" else
                                 "\nUYARI: GERCEK_ISLEM=1 /etc/nexora.env'de yok; eklenip guncelle yapılmadan alım olmaz."))
    p = _pilot()
    if a.komut == "sat-hepsi":
        if a.onay != "GERCEK-PARA": sys.exit("Onay gerekli: --onay GERCEK-PARA")
        for r in p.db.execute("SELECT token FROM gercek_poz").fetchall():
            print(r["token"][:8], p.sat(f"elle:{r['token']}:{int(time.time())}", r["token"]))
    print(durum_metni(p.ozet()))


if __name__ == "__main__":
    main(sys.argv[1:])

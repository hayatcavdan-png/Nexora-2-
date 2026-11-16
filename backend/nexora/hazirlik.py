"""Gerçek paraya geçiş için HAZIRLIK KARNESİ (salt okunur).

Amaç: "hazır mıyız?" sorusuna duygusal değil ölçülebilir cevap vermek. Her ölçüt paper verisinden hesaplanır.
Karne asla "gerçek emre geç" demez: tüm teknik ölçütler geçse bile gerçek emir ayrıca açık onay ister (N12).
Küçük örneklemde sonuç "bekliyor" kalır; şans eseri iyi görünen kısa bir seri ölçütü geçirmez."""
import math, sqlite3, time

from nexora import panel

MIN_ISLEM, MIN_GUN, MIN_PF, MAX_DUSUS_PCT = 30, 14, 1.3, 10.0
MIN_CALISMA_GUN, MIN_CALISMA_PCT, MIN_ETIKET = 7, 99.5, 500
GUVEN_Z = 1.645                                   # tek yönlü %95


def islem_istatistigi(pnller):
    """Kapanan işlem K/Z listesinden: n, kazanma, ortalama, standart hata, güven alt sınırı, profit factor."""
    n = len(pnller)
    if n == 0: return dict(n=0)
    ort = sum(pnller) / n
    kazanc = sum(p for p in pnller if p > 0); kayip = -sum(p for p in pnller if p < 0)
    sd = math.sqrt(sum((p - ort) ** 2 for p in pnller) / (n - 1)) if n > 1 else None
    se = sd / math.sqrt(n) if sd is not None else None
    return dict(n=n, kazanma_pct=round(sum(p > 0 for p in pnller) * 100 / n, 1), ort=round(ort, 4),
                guven_alt=round(ort - GUVEN_Z * se, 4) if se is not None else None,
                profit_factor=round(kazanc / kayip, 2) if kayip > 0 else (None if kazanc == 0 else 99.0), toplam=round(sum(pnller), 4))


def _olc(kod, ad, hedef, deger, gecti, bekliyor=False):
    return dict(kod=kod, ad=ad, hedef=hedef, deger=deger, durum="bekliyor" if bekliyor else ("gecti" if gecti else "gecmedi"))


def hazirlik(paper_path, etiket_ozeti=None, now=None):
    now = now if now is not None else time.time()
    c = panel._ro(paper_path)
    pnller, ilk = [], None
    if c is not None:
        try:
            rows = panel._rows(c, "SELECT ts, pnl FROM trades WHERE decision='KOPYALANDI' AND side='sell' ORDER BY id")
            pnller = [r["pnl"] or 0.0 for r in rows]
            ilk_r = panel._rows(c, "SELECT MIN(ts) t FROM trades WHERE decision='KOPYALANDI'")
            ilk = ilk_r[0]["t"] if ilk_r else None
        finally:
            c.close()
    ist = islem_istatistigi(pnller)
    gun = (now - ilk) / 86400 if ilk else 0.0
    g = panel.gecmis(paper_path, now)
    dusus = g.get("max_dusus_pct", 0.0)
    kar = panel.saglik(paper_path, "", now=now).get("kararlilik")
    n = ist["n"]
    o = []
    o.append(_olc("islem", "Kapanan işlem sayısı", f"≥ {MIN_ISLEM}", n, n >= MIN_ISLEM, bekliyor=n < MIN_ISLEM))
    o.append(_olc("sure", "Paper süresi (gün)", f"≥ {MIN_GUN}", round(gun, 1), gun >= MIN_GUN, bekliyor=gun < MIN_GUN))
    yeterli = n >= MIN_ISLEM
    o.append(_olc("beklenen", "İşlem başına ortalama K/Z (USDC)", "> 0", ist.get("ort"), (ist.get("ort") or 0) > 0, bekliyor=not yeterli))
    o.append(_olc("guven", "Ortalamanın %95 güven alt sınırı (USDC)", "> 0 (şans değil)", ist.get("guven_alt"),
                  (ist.get("guven_alt") or 0) > 0, bekliyor=not yeterli or ist.get("guven_alt") is None))
    o.append(_olc("pf", "Profit factor (kazanç/kayıp)", f"≥ {MIN_PF}", ist.get("profit_factor"), (ist.get("profit_factor") or 0) >= MIN_PF, bekliyor=not yeterli))
    o.append(_olc("dusus", "En büyük düşüş (%)", f"≤ {MAX_DUSUS_PCT:.0f}", dusus, dusus <= MAX_DUSUS_PCT, bekliyor=ilk is None))
    cg = (kar or {}).get("izleme_gun") or 0; cp = (kar or {}).get("calisma_pct")
    o.append(_olc("calisma", "Kesintisiz çalışma (%)", f"≥ {MIN_CALISMA_PCT} ({MIN_CALISMA_GUN}+ gün)", cp,
                  cp is not None and cp >= MIN_CALISMA_PCT, bekliyor=cg < MIN_CALISMA_GUN or cp is None))
    et = (etiket_ozeti or {}).get("etiketli", 0)
    o.append(_olc("etiket", "Etiketli sinyal (yapay zekâ verisi)", f"≥ {MIN_ETIKET}", et, et >= MIN_ETIKET, bekliyor=et < MIN_ETIKET))
    gecti = sum(x["durum"] == "gecti" for x in o); bek = sum(x["durum"] == "bekliyor" for x in o)
    kotu = [x["ad"] for x in o if x["durum"] == "gecmedi"]
    if kotu: sonuc, aciklama = "gecmedi", "Başarısız ölçüt var: " + ", ".join(kotu) + ". Gerçek paraya geçilmez."
    elif bek: sonuc, aciklama = "bekliyor", f"{bek} ölçüt için yeterli veri yok. Gerçek paraya geçilmez."
    else: sonuc, aciklama = "teknik_tamam", "Teknik ölçütler geçti. Gerçek emir yine de yalnızca ayrı, açık onayla açılır (N12)."
    return dict(olcutler=o, gecen=gecti, toplam=len(o), sonuc=sonuc, aciklama=aciklama, istatistik=ist, ts=now,
                manuel=["Gerçek emir simülasyonu başarılı (N11)", "Hukuki kontrol tamamlandı", "Açık onay (N12)"])

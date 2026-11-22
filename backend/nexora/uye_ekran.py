"""Üye ekranları için salt okunur özet (5.26.0, yeni arayüz).

Üye takip listesinin adreslerini görmez (takip listesi kurucunundur). Bu yüzden kopyalanan cüzdanlar
kalıcı bir takma adla ("Trader #7F3A") gösterilir: adresin özetinden üretilir, adrese geri çevrilemez.
"""
import hashlib, sqlite3, time

from nexora import panel


def takma_ad(wallet):
    return "Trader #" + hashlib.sha256(("nexora:" + (wallet or "")).encode()).hexdigest()[:4].upper()


def _bizim(paper_path, gun, now):
    """Son `gun` gündeki kapanan kopyalar, cüzdan başına: kapanan, kazanan, K/Z."""
    out = {}
    try:
        c = sqlite3.connect(f"file:{paper_path}?mode=ro", uri=True, timeout=5)
        rows = c.execute("SELECT wallet, pnl FROM trades WHERE side='sell' AND decision='KOPYALANDI' AND ts>=?",
                         (now - gun * 86400,)).fetchall()
        c.close()
    except sqlite3.Error:
        return out
    for w, pnl in rows:
        d = out.setdefault(w, dict(kapanan=0, kazanan=0, kz=0.0))
        d["kapanan"] += 1; d["kazanan"] += 1 if (pnl or 0) > 0 else 0; d["kz"] += pnl or 0
    return out


def _etiketler(r):
    e = []
    t = r.get("medyan_tutma_sn")
    if t is not None:
        e.append("Hızlı al-sat" if t < 1800 else "Kısa tutar" if t < 4 * 3600 else "Uzun tutar")
    k = r.get("kazanma_orani")
    if k is not None and k >= 60: e.append("İsabetli")
    if (r.get("paper_acik") or 0) > 0: e.append("Şu an pozisyonda")
    return e


def kopya_ozet(paper_path, tracker_path, gun=30, now=None):
    now = now or time.time()
    c = panel.cuzdanlar(paper_path, tracker_path)
    biz = _bizim(paper_path, gun, now)
    liste, deneniyor = [], []
    for r in c.get("cuzdanlar", []):
        if not r.get("takipte"):
            if r.get("karar") == "kopyalanabilir":
                deneniyor.append(dict(ad=takma_ad(r["wallet"]), trader_kazanma=r.get("kazanma_orani"), etiketler=_etiketler(r)))
            continue
        b = biz.get(r["wallet"], dict(kapanan=0, kazanan=0, kz=0.0))
        liste.append(dict(
            ad=takma_ad(r["wallet"]), durum=r.get("durum"),
            kapanan=b["kapanan"], kazanan=b["kazanan"], kz=round(b["kz"], 2),
            bizim_kazanma=round(100.0 * b["kazanan"] / b["kapanan"], 1) if b["kapanan"] else None,
            trader_kazanma=r.get("kazanma_orani"), acik=r.get("paper_acik") or 0, etiketler=_etiketler(r)))
    liste.sort(key=lambda x: (-x["kz"], -x["kapanan"]))
    return dict(gun=gun, kopyalanan=liste, deneniyor=len(deneniyor), deneniyor_liste=deneniyor)

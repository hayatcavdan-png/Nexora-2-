"""Uygulama paneli için salt okunur veri (N14). Ağ isteği yapmaz; yerel dosya ve veritabanlarını okur."""
import csv, json, os, sqlite3, time

from nexora.core import CFG
from nexora.rapor import build_report


def _ro(path):
    if not path or not os.path.exists(path): return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _rows(conn, sql, args=()):
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    except sqlite3.OperationalError:
        return []


def _read_list(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]


def gecmis(paper_path, now=None):
    """Portföy değer eğrisi. Her kopyalanan işlemden sonra gerçekleşen değer; son nokta, açık
    pozisyonların son değerlemesiyle güncel toplam değer. Alımda ödenen ağ ücreti de düşülür."""
    now = now if now is not None else time.time()
    start = CFG["start_cash"]
    c = _ro(paper_path)
    if c is None:
        return dict(baslangic=start, noktalar=[dict(ts=now, deger=start)], guncel=start)
    try:
        trades = _rows(c, "SELECT ts, side, pnl, fee FROM trades WHERE decision='KOPYALANDI' ORDER BY id")
        state = {r["k"]: r["v"] for r in _rows(c, "SELECT k, v FROM state")}
        pos_value = sum((r["qty"] or 0) * (r["last_price"] or 0) for r in _rows(c, "SELECT qty, last_price FROM positions"))
    finally:
        c.close()
    value, pts = start, []
    if trades: pts.append(dict(ts=trades[0]["ts"] - 1, deger=round(start, 4)))
    for t in trades:
        if t["side"] == "buy": value -= t["fee"] or 0
        else: value += t["pnl"] or 0
        pts.append(dict(ts=t["ts"], deger=round(value, 4)))
    guncel = float(state.get("cash", start) or start) + pos_value
    pts.append(dict(ts=now, deger=round(guncel, 4)))
    return dict(baslangic=start, noktalar=pts, guncel=round(guncel, 4))


def cuzdanlar(paper_path, tracker_path, analiz_csv="cuzdan_analiz.csv", tarama_csv="cuzdan_tarama.csv"):
    """Takip edilen ve analiz edilen cüzdanlar: analiz metrikleri + takip durumu + paper performansı."""
    tracked = [w for w in _read_list("wallets.txt") if w not in set(_read_list("kara_liste.txt"))]
    black = _read_list("kara_liste.txt")
    analiz = {}
    if os.path.exists(analiz_csv):
        for r in csv.DictReader(open(analiz_csv, newline="")): analiz[r["wallet"]] = r
    taranan = sum(1 for _ in csv.DictReader(open(tarama_csv, newline=""))) if os.path.exists(tarama_csv) else 0

    status = {}
    tc = _ro(tracker_path)
    if tc is not None:
        try:
            for r in _rows(tc, "SELECT wallet, quarantined, last_error FROM tracker_wallets"):
                status[r["wallet"]] = r
        finally:
            tc.close()
    perf = {r["wallet"]: r for r in build_report(paper_path, None).get("cuzdanlar", [])}

    def num(r, k, cast=float):
        try: return cast(r.get(k)) if r and r.get(k) not in (None, "") else None
        except ValueError: return None

    out = []
    for w in dict.fromkeys(tracked + [w for w, r in analiz.items() if r.get("karar") == "kopyalanabilir"]):
        a, s, p = analiz.get(w), status.get(w), perf.get(w, {})
        q = (s or {}).get("quarantined") or 0
        out.append(dict(
            wallet=w, takipte=w in tracked,
            durum="bot" if q == 2 else "karantina" if q == 1 else ("aktif" if w in tracked else "takip dışı"),
            karar=(a or {}).get("karar", "analiz yok"),
            kazanma_orani=num(a, "kazanma_orani"), kar_faktoru=num(a, "kar_faktoru"),
            kaynak_kz=num(a, "gerceklesen_usd"), ort_getiri=num(a, "ort_getiri"),
            medyan_tutma_sn=num(a, "medyan_tutma_sn", lambda v: int(float(v))),
            kapanan_kaynak=num(a, "kapanan", lambda v: int(float(v))),
            skor=num(a, "skor") or 0.0,
            paper_sinyal=p.get("sinyal", 0), paper_kopyalanan=p.get("kopyalanan", 0),
            paper_kapanan=p.get("kapanan", 0), paper_kz=p.get("gerceklesen_kz", 0.0), paper_acik=p.get("acik", 0)))
    out.sort(key=lambda r: (not r["takipte"], -(r["skor"] or 0)))
    kararlar = {}
    for r in analiz.values(): kararlar[r.get("karar", "?")] = kararlar.get(r.get("karar", "?"), 0) + 1
    return dict(ozet=dict(taranan=taranan, analiz=len(analiz), kopyalanabilir=kararlar.get("kopyalanabilir", 0),
                          takipte=len(tracked), kara_liste=len(black), kararlar=kararlar),
                cuzdanlar=out)


def asamalar(path="asamalar.json"):
    if not os.path.exists(path): return dict(rows=[], guncelleme=None)
    d = json.load(open(path, encoding="utf-8"))
    meta = (d.get("meta") or [{}])[0].get("value")
    return dict(rows=d.get("rows", []), guncelleme=meta)

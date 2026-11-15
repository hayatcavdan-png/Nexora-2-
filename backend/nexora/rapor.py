"""Günlük paper raporu (N9). Paper ve takip veritabanlarını SALT OKUNUR okur.

İçerik: bugünkü kararlar ve red gerekçeleri, kapanan işlemlerin K/Z'si, portföy,
gölge işlem sonuçları (al-sat kaybı aralıklarına göre) ve cüzdan bazında performans."""
import os, re, sqlite3, time
from collections import Counter, defaultdict

SHADOW_BUCKETS = [("al-sat %6-8", 6, 8), ("al-sat %8-10", 8, 10), ("al-sat %10-15", 10, 15), ("al-sat %15+", 15, 1e9)]

def _ro(path):
    if not path or not os.path.exists(path): return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c

def _rows(conn, sql, args=()):
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    except sqlite3.OperationalError:          # tablo henüz yok (eski veritabanı)
        return []

def reason_group(reason):
    """'al-sat kaybı yüksek (%8.1)' -> 'al-sat kaybı yüksek': sayılar gruplamayı bölmesin."""
    return re.sub(r"\s*\(%?-?[\d.,]+\)", "", reason or "").strip() or "?"

def start_of_local_day(now=None):
    t = time.localtime(now if now is not None else time.time())
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))

def shadow_summary(shadows):
    groups = [(name, [r for r in shadows if r.get("rt_loss_pct") is not None and lo <= r["rt_loss_pct"] < hi])
              for name, lo, hi in SHADOW_BUCKETS]
    groups.append(("fiyat etkisi yüksek", [r for r in shadows if r.get("rt_loss_pct") is None]))
    out = []
    for name, rs in groups:
        if not rs: continue
        closed = [r for r in rs if r["status"] != "open"]
        out.append(dict(
            grup=name, kapanan=len(closed), acik=len(rs) - len(closed),
            kazanan=sum(1 for r in closed if (r["pnl_usd"] or 0) > 0),
            toplam_kz=round(sum(r["pnl_usd"] or 0 for r in closed), 2),
            ort_getiri=round(sum((r["pnl_usd"] or 0) / r["size_usd"] for r in closed) / len(closed) * 100, 1) if closed else 0.0,
            satilamadi=sum(1 for r in rs if r["status"] == "satilamadi")))
    return out

def build_report(paper_path, tracker_path=None, now=None):
    now = now if now is not None else time.time()
    since = start_of_local_day(now)
    p = _ro(paper_path)
    if p is None:
        return dict(gun=time.strftime("%Y-%m-%d", time.localtime(now)), hazir=False,
                    mesaj="Paper veritabanı henüz yok: takip çalışınca oluşur.")
    try:
        trades = _rows(p, "SELECT * FROM trades ORDER BY id")
        positions = _rows(p, "SELECT * FROM positions")
        shadows = _rows(p, "SELECT * FROM shadow ORDER BY id")
        state = {r["k"]: r["v"] for r in _rows(p, "SELECT k, v FROM state")}
    finally:
        p.close()

    today = [t for t in trades if (t["ts"] or 0) >= since]
    copied_buys = [t for t in today if t["decision"] == "KOPYALANDI" and t["side"] == "buy"]
    closed = [t for t in today if t["decision"] == "KOPYALANDI" and t["side"] == "sell"]
    rejected = [t for t in today if t["decision"] == "REDDEDİLDİ"]
    reasons = Counter(reason_group(t["reason"]) for t in rejected).most_common(6)

    cash = float(state.get("cash", 0) or 0)
    pos_value = sum((r["qty"] or 0) * (r["last_price"] or 0) for r in positions)
    start_cash = 100.0
    try:
        from nexora.core import CFG
        start_cash = CFG["start_cash"]
    except Exception:
        pass

    wallets = defaultdict(lambda: dict(sinyal=0, kopyalanan=0, kapanan=0, gerceklesen_kz=0.0, acik=0,
                                       golge_kapanan=0, golge_kz=0.0))
    for t in trades:
        if not t["wallet"]: continue
        w = wallets[t["wallet"]]; w["sinyal"] += 1
        if t["decision"] == "KOPYALANDI" and t["side"] == "buy": w["kopyalanan"] += 1
        if t["decision"] == "KOPYALANDI" and t["side"] == "sell":
            w["kapanan"] += 1; w["gerceklesen_kz"] += t["pnl"] or 0
    for r in positions:
        if r.get("wallet"): wallets[r["wallet"]]["acik"] += 1
    for s in shadows:
        if s["status"] != "open":
            w = wallets[s["wallet"]]; w["golge_kapanan"] += 1; w["golge_kz"] += s["pnl_usd"] or 0
    wallet_rows = sorted(({"wallet": k, **{a: (round(b, 2) if isinstance(b, float) else b) for a, b in v.items()}}
                          for k, v in wallets.items()), key=lambda r: (-r["kapanan"], -r["sinyal"]))

    gecikme = {}
    tc = _ro(tracker_path)
    if tc is not None:
        try:
            from nexora.live_tracker import latency_from_db
            gecikme = latency_from_db(tc)
        except sqlite3.OperationalError:
            gecikme = {}
        finally:
            tc.close()

    return dict(
        gun=time.strftime("%Y-%m-%d", time.localtime(now)), hazir=True,
        bugun=dict(karar=len(today), kopyalanan_alim=len(copied_buys), kapanan=len(closed), reddedilen=len(rejected),
                   gerceklesen_kz=round(sum(t["pnl"] or 0 for t in closed), 2),
                   red_gerekceleri=[dict(gerekce=r, adet=n) for r, n in reasons]),
        portfoy=dict(nakit=round(cash, 2), pozisyon_degeri=round(pos_value, 2), toplam=round(cash + pos_value, 2),
                     kz=round(cash + pos_value - start_cash, 2), acik_pozisyon=len(positions),
                     acil_durdurma=state.get("kill") == "1"),
        golge=dict(toplam=len(shadows), acik=sum(1 for s in shadows if s["status"] == "open"),
                   gruplar=shadow_summary(shadows)),
        cuzdanlar=wallet_rows,
        gecikme=gecikme,
    )

def as_text(r):
    if not r.get("hazir"): return r.get("mesaj", "Rapor hazır değil.")
    b, pf, g = r["bugun"], r["portfoy"], r["golge"]
    L = [f"NEXORA günlük rapor · {r['gun']}", "",
         f"Portföy: toplam {pf['toplam']:.2f} USDC (nakit {pf['nakit']:.2f}, pozisyon {pf['pozisyon_degeri']:.2f}), "
         f"K/Z {pf['kz']:+.2f} USDC, {pf['acik_pozisyon']} açık pozisyon" + (" · ACİL DURDURMA AKTİF" if pf["acil_durdurma"] else ""),
         f"Bugün: {b['karar']} karar, {b['kopyalanan_alim']} alım kopyalandı, {b['kapanan']} işlem kapandı "
         f"(K/Z {b['gerceklesen_kz']:+.2f}), {b['reddedilen']} red"]
    if b["red_gerekceleri"]:
        L.append("En sık red gerekçeleri:")
        L += [f"  {x['adet']:>3} × {x['gerekce']}" for x in b["red_gerekceleri"]]
    L += ["", f"Gölge işlemler: {g['toplam']} (açık {g['acik']})"]
    for x in g["gruplar"]:
        L.append(f"  {x['grup']:<20} kapanan {x['kapanan']:>3}, kazanan {x['kazanan']:>3}, "
                 f"K/Z {x['toplam_kz']:+.2f}$, ort. {x['ort_getiri']:+.1f}%, açık {x['acik']}"
                 + (f", satılamadı {x['satilamadi']}" if x["satilamadi"] else ""))
    if r["cuzdanlar"]:
        L += ["", "Cüzdan bazında (tüm zamanlar):"]
        for w in r["cuzdanlar"]:
            L.append(f"  {w['wallet'][:4]}…{w['wallet'][-4:]}  sinyal {w['sinyal']:>3}  kopyalanan {w['kopyalanan']:>2}  "
                     f"kapanan {w['kapanan']:>2} K/Z {w['gerceklesen_kz']:+.2f}  açık {w['acik']}  "
                     f"gölge {w['golge_kapanan']} ({w['golge_kz']:+.2f})")
    if r["gecikme"]:
        L += [""] + [f"Gecikme ({k}): {v['n']} sinyal, P50 {v['p50']:.0f} sn, P95 {v['p95']:.0f} sn" for k, v in r["gecikme"].items()]
    return "\n".join(L)

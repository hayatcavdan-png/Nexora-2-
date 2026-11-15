"""Gölge işlem raporu: reddedilen alımlara girseydik ne olurdu? (salt okunur)
Çalıştır (backend klasöründe): python golge_rapor.py"""
import os, sqlite3, sys

BUCKETS = [("al-sat %6-8", 6, 8), ("al-sat %8-10", 8, 10), ("al-sat %10-15", 10, 15), ("al-sat %15+", 15, 1e9)]

def report(path):
    if not os.path.exists(path): return "Paper veritabanı yok: önce takip çalışmalı."
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in c.execute("SELECT * FROM shadow")]
    except sqlite3.OperationalError:
        return "Henüz gölge işlem yok (yeni sürüm takip başlatılınca kaydedilmeye başlar)."
    real = [dict(r) for r in c.execute("SELECT pnl FROM trades WHERE side='sell' AND decision='KOPYALANDI'")]
    lines = [f"Gölge işlem: {len(rows)} (açık {sum(r['status'] == 'open' for r in rows)}, "
             f"kapanmış {sum(r['status'] != 'open' for r in rows)})", ""]
    groups = [(name, [r for r in rows if r["rt_loss_pct"] is not None and lo <= r["rt_loss_pct"] < hi]) for name, lo, hi in BUCKETS]
    groups.append(("fiyat etkisi yüksek", [r for r in rows if r["rt_loss_pct"] is None]))
    lines.append(f"{'Grup':<20}{'kapanan':>8}{'kazanan':>9}{'toplam K/Z':>12}{'ort. getiri':>12}{'açık':>6}")
    for name, rs in groups:
        closed = [r for r in rs if r["status"] != "open"]
        if not rs: continue
        tot = sum(r["pnl_usd"] for r in closed)
        avg = (sum(r["pnl_usd"] / r["size_usd"] for r in closed) / len(closed) * 100) if closed else 0
        wins = sum(1 for r in closed if r["pnl_usd"] > 0)
        lines.append(f"{name:<20}{len(closed):>8}{wins:>9}{tot:>+11.2f}${avg:>+11.1f}%{len(rs) - len(closed):>6}")
    stuck = [r for r in rows if r["status"] == "satilamadi"]
    if stuck: lines.append(f"\nUyarı: {len(stuck)} gölge pozisyon satış anında satılamadı (bunlara girseydik takılıp kalırdık).")
    if real:
        lines.append(f"\nKarşılaştırma, gerçek paper işlemler: {len(real)} kapanmış, toplam K/Z {sum(r['pnl'] for r in real):+.2f}$")
    lines.append("\nNot: Kapanan örnek sayısı 20'nin altındaysa sonuç güvenilir değildir; eşik kararı için bekleyin.")
    return "\n".join(lines)

if __name__ == "__main__":
    print(report(sys.argv[1] if len(sys.argv) > 1 else os.getenv("NEXORA_DB", "nexora_paper.db")))

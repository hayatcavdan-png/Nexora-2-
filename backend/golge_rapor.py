"""Gölge işlem raporu: reddedilen alımlara girseydik ne olurdu? (salt okunur)
Çalıştır (backend klasöründe): python golge_rapor.py"""
import os, sqlite3, sys

from nexora.rapor import shadow_summary

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
    lines.append(f"{'Grup':<20}{'kapanan':>8}{'kazanan':>9}{'toplam K/Z':>12}{'ort. getiri':>12}{'açık':>6}")
    for g in shadow_summary(rows):
        lines.append(f"{g['grup']:<20}{g['kapanan']:>8}{g['kazanan']:>9}{g['toplam_kz']:>+11.2f}${g['ort_getiri']:>+11.1f}%{g['acik']:>6}")
    stuck = [r for r in rows if r["status"] == "satilamadi"]
    if stuck: lines.append(f"\nUyarı: {len(stuck)} gölge pozisyon satış anında satılamadı (bunlara girseydik takılıp kalırdık).")
    if real:
        lines.append(f"\nKarşılaştırma, gerçek paper işlemler: {len(real)} kapanmış, toplam K/Z {sum(r['pnl'] for r in real):+.2f}$")
    lines.append("\nNot: Kapanan örnek sayısı 20'nin altındaysa sonuç güvenilir değildir; eşik kararı için bekleyin.")
    return "\n".join(lines)

if __name__ == "__main__":
    print(report(sys.argv[1] if len(sys.argv) > 1 else os.getenv("NEXORA_DB", "nexora_paper.db")))

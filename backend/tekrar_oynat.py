"""Yaklaşık tekrar oynatma: paper 'trades' tablosundaki KOPYALANDI alım/satımları sırayla yeniden oynatır ve
POZISYON_MOD='token' ile 'cuzdan' modlarını aynı girdide karşılaştırır.

SINIR (önemli): ham sinyal fiyatı ve likidite saklanmadığı için girdi, gerçekleşen (kaymalı) işlem fiyatlarıdır.
Boyutlandırma güncel motor kuralıyla yeniden hesaplanır. Sonuç mod farkının YÖNÜNÜ ve BÜYÜKLÜĞÜNÜ gösterir;
mutlak kâr/zarar rakamı olarak kullanılmamalıdır.

Kullanım (salt okuma; kaynak veritabanı değiştirilmez):
  python3 tekrar_oynat.py /opt/nexora/backend/nexora_paper.db
"""
import os, sqlite3, sys

from nexora import core as C


def olaylar(yol):
    c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=10)
    try:
        rows = c.execute("SELECT ts, event_id, wallet, token, side, price FROM trades WHERE decision='KOPYALANDI' ORDER BY ts, id").fetchall()
    finally:
        c.close()
    return [dict(ts=r[0], event_id=r[1], wallet=r[2], token=r[3], side=r[4], price=float(r[5] or 0)) for r in rows if (r[5] or 0) > 0]


def oynat(olay_listesi, mod):
    eski = C.POZISYON_MOD
    C.POZISYON_MOD = mod
    try:
        p = C.Paper(":memory:")
        kapanan = 0; net = 0.0; red = 0
        for o in olay_listesi:
            r = p.handle_signal(o["event_id"], o["wallet"], o["token"], o["side"], o["price"], 1e6, 1)
            if r["decision"] != "KOPYALANDI": red += 1; continue
            if o["side"] == "sell":
                kapanan += 1; net += r["pnl"]
        return dict(mod=mod, kapanan=kapanan, net=round(net, 4), reddedilen=red)
    finally:
        C.POZISYON_MOD = eski


if __name__ == "__main__":
    yol = sys.argv[1] if len(sys.argv) > 1 else os.getenv("PAPER_DB", "nexora_paper.db")
    ev = olaylar(yol)
    print(f"Girdi: {len(ev)} olay (gerçekleşen işlem fiyatları; yaklaşık)")
    for m in ("token", "cuzdan"):
        r = oynat(ev, m)
        print(f"  {r['mod']:7s} kapanan={r['kapanan']:4d}  net={r['net']:+.2f}$  reddedilen={r['reddedilen']}")
    print("Not: yaklaşık ölçüm; mutlak rakam olarak değil, modlar arası fark olarak yorumlayın.")

"""Canlı takip. Çalıştır (backend klasöründe):
  export HELIUS_API_KEY=...    (anahtar koda/loga yazılmaz)
  python tracker.py            (cüzdanlar wallets.txt'ten, her satıra bir adres)"""
import os, sys, time
from nexora.helius_client import HeliusClient, HeliusRPCError
from nexora.core import Paper
from nexora.live_tracker import LiveTracker

INTERVAL = int(os.getenv("TRACK_INTERVAL", "20"))

def short(a): return a[:4] + "…" + a[-4:]

def main():
    if not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil: export HELIUS_API_KEY=...")
    if not os.path.exists("wallets.txt"):
        sys.exit("wallets.txt yok: her satıra bir cüzdan adresi yazın")
    wallets = [l.strip() for l in open("wallets.txt") if l.strip() and not l.startswith("#")]
    if not wallets: sys.exit("wallets.txt boş")
    client = HeliusClient(max_retries=2)
    try:
        client.get_health()
    except HeliusRPCError as e:
        sys.exit(f"Helius bağlantısı başarısız: {e}")
    paper = Paper(os.getenv("NEXORA_DB", "nexora_paper.db"))
    tr = LiveTracker(client, paper, os.getenv("TRACKER_DB", "nexora_tracker.db"), wallets)
    print(f"Takip başladı: {len(wallets)} cüzdan, {INTERVAL} sn aralık (PAPER, gerçek işlem KAPALI)")
    last_id = 0
    while True:
        rep = tr.poll_all()
        summary = ", ".join(f"{short(w)}={v}" for w, v in rep.items())
        print(time.strftime("%H:%M:%S"), summary, flush=True)
        for s in tr.signals(5)[::-1]:
            if s["ts"] > last_id:
                print(f"  SİNYAL {s['side']} {short(s['token'])} cüzdan {short(s['wallet'])} "
                      f"gecikme {s['latency_s']:.0f} sn -> {s['decision']} ({s['reason']})", flush=True)
        sigs = tr.signals(1)
        if sigs: last_id = sigs[0]["ts"]
        time.sleep(INTERVAL)

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nDurduruldu.")

"""Canlı takip: WebSocket (anlık) + yoklama (yedek, kaçanları tamamlar).
Çalıştır (backend klasöründe):
  read -s HELIUS_API_KEY && export HELIUS_API_KEY   (anahtar ekrana/loga yazılmaz)
  python tracker.py                                  (cüzdanlar wallets.txt'ten)
Ayarlar (isteğe bağlı):
  TRACK_WS=0          WebSocket'i kapatır, yalnızca yoklama
  TRACK_INTERVAL=60   yoklama aralığı (sn); WebSocket açıkken varsayılan 60, kapalıyken 20"""
import os, sys, threading, time
from nexora import settings
from nexora.helius_client import HeliusClient, HeliusRPCError
from nexora.core import Paper
from nexora.live_tracker import LiveTracker
from nexora.ws_listener import WSListener
from nexora.market import JupiterQuoter
from nexora.token_safety import TokenSafety
from nexora.decision import Decider

USE_WS = os.getenv("TRACK_WS", "1") != "0"
PAPER_TRADE = os.getenv("PAPER_TRADE", "1") != "0"    # 0: eski davranış (fiyat bilinmiyor -> hepsi engellenir)

def read_list(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]
INTERVAL = int(os.getenv("TRACK_INTERVAL", "60" if USE_WS else "20"))
MARK_EVERY = int(os.getenv("MARK_INTERVAL", "300"))   # açık pozisyonları 5 dakikada bir gerçek teklifle değerle

def short(a): return a[:4] + "…" + a[-4:]

def show(r):
    print(f"  SİNYAL [{r['source']}] {r['side']} {short(r['token'])} cüzdan {short(r['wallet'])} "
          f"gecikme {r['latency_s']:.0f} sn -> {r['decision']} ({r['reason']})", flush=True)

def main():
    if not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil: read -s HELIUS_API_KEY && export HELIUS_API_KEY")
    if not os.path.exists("wallets.txt"):
        sys.exit("wallets.txt yok: her satıra bir cüzdan adresi yazın")
    wallets = read_list("wallets.txt")
    black = set(read_list("kara_liste.txt"))
    for w in [w for w in wallets if w in black]:
        print(f"  {short(w)}: kara listede (bilinen bot), izlenmeyecek", flush=True)
    wallets = [w for w in wallets if w not in black]
    if not wallets: sys.exit("wallets.txt boş (ya da hepsi kara listede)")

    client = HeliusClient(max_retries=2)
    try:
        client.get_health()
    except HeliusRPCError as e:
        sys.exit(f"Helius bağlantısı başarısız: {e}")
    paper = Paper(os.getenv("NEXORA_DB", "nexora_paper.db"))
    decider = None
    if PAPER_TRADE:
        quoter = JupiterQuoter()
        decider = Decider(paper, quoter, TokenSafety(client))
        if not quoter.api_key:
            print("  Not: JUPITER_API_KEY yok, teklifler anahtarsız (0.5 istek/sn). Ücretsiz anahtar hızlandırır.", flush=True)
    tr = LiveTracker(client, paper, os.getenv("TRACKER_DB", "nexora_tracker.db"), wallets, decider=decider)
    n = tr.reset_quarantine()
    if n: print(f"{n} cüzdan karantinadan çıkarıldı (yeniden deneniyor)", flush=True)
    if os.getenv("CLEAR_BOT") == "1":
        for w in tr.bot_wallets(): tr.clear_bot_flag(w)
    for w in tr.bot_wallets():
        print(f"  {short(w)}: yüksek frekans (bot) işaretli, izlenmiyor. "
              f"wallets.txt'ten çıkarın ya da CLEAR_BOT=1 ile yeniden deneyin.", flush=True)
    tr.poll_all()                                     # başlangıç noktası / kaçanları tamamla

    stop = threading.Event()
    listener = None
    if USE_WS:
        ws_url = settings.SOLANA_RPC_URL.replace("https://", "wss://", 1)
        def on_sig(wallet, sig):
            r = tr.handle_signature(wallet, sig, source="ws")
            if r: show(r)
            while tr.flagged:
                print(f"  UYARI {short(tr.flagged.pop())}: 10 dk içinde 30+ işlem, bot olabilir. "
                      f"Takip durduruldu (API kotası korunuyor).", flush=True)
        listener = WSListener(ws_url, tr.active_wallets(), on_sig,
                              log=lambda m: print("  [ws]", m, flush=True))
        threading.Thread(target=listener.run_forever, args=(stop,), daemon=True).start()

    mode = ("WebSocket + yedek yoklama" if USE_WS else "yalnızca yoklama") + \
           (", gerçek Jupiter teklifleriyle paper işlem" if PAPER_TRADE else ", paper işlem kapalı")
    print(f"Takip başladı: {len(wallets)} cüzdan, {mode}, yoklama {INTERVAL} sn "
          f"(PAPER, gerçek işlem KAPALI)", flush=True)
    last_mark = time.time()
    try:
        while True:
            stop.wait(INTERVAL)
            if decider and time.time() - last_mark >= MARK_EVERY:
                last_mark = time.time()
                ok, bad = decider.mark_to_market()
                if bad: print(f"  değerleme: {ok} pozisyon güncellendi, {bad} için teklif alınamadı", flush=True)
            for w, res in tr.poll_all().items():
                if res == "hata": print(f"  {short(w)}: hata (karantinaya yaklaşıyor olabilir)", flush=True)
            for r in tr.last_poll_rows:                 # WebSocket'in kaçırıp yoklamanın bulduğu
                show(r)
            st = tr.latency_stats()
            ws_state = ("bağlı" if listener and listener.connected else "bağlı değil") if USE_WS else "kapalı"
            parts = [f"{k}: n={v['n']} P50={v['p50']:.0f}s P95={v['p95']:.0f}s" for k, v in st.items()]
            nf = tr.failed_count()
            extra = f" | okunamayan işlem: {nf}" if nf else ""
            pf = paper.portfolio()
            extra += f" | paper: nakit {pf['cash']:.2f} pozisyon {len(pf['positions'])} K/Z {pf['pnl']:+.2f} USDC"
            print(time.strftime("%H:%M:%S"), f"ws {ws_state} |", (" | ".join(parts) or "henüz sinyal yok") + extra, flush=True)
    finally:
        stop.set()

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nDurduruldu.")

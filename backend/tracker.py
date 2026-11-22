"""Canlı takip: WebSocket (anlık) + yoklama (yedek, kaçanları tamamlar).
Çalıştır (backend klasöründe):
  read -s HELIUS_API_KEY && export HELIUS_API_KEY   (anahtar ekrana/loga yazılmaz)
  python tracker.py                                  (cüzdanlar wallets.txt'ten)
Ayarlar (isteğe bağlı):
  TRACK_WS=0          WebSocket'i kapatır, yalnızca yoklama
  TRACK_INTERVAL=60   yoklama aralığı (sn); WebSocket açıkken varsayılan 60, kapalıyken 20"""
import os, sys, threading, time
from nexora import settings
from nexora import gizle as _gizle
_gizle.kur()
from nexora.helius_client import HeliusClient, HeliusRPCError
from nexora.core import Paper
from nexora.live_tracker import LiveTracker
from nexora.ws_listener import WSListener
from nexora.market import JupiterQuoter
from nexora.token_safety import TokenSafety
from nexora.model_kapisi import ModelDosyasi, ModelKapisi
from nexora.decision import Decider, kaynak_bakiyesi
from nexora.token_bilgi import TokenBilgi, Toplayici
from nexora.yurutme import YurutmeOlcer
from nexora.etiket import Etiketci

USE_WS = os.getenv("TRACK_WS", "1") != "0"
PAPER_TRADE = os.getenv("PAPER_TRADE", "1") != "0"    # 0: eski davranış (fiyat bilinmiyor -> hepsi engellenir)

def read_list(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]
INTERVAL = int(os.getenv("TRACK_INTERVAL", "60" if USE_WS else "20"))
MARK_EVERY = int(os.getenv("MARK_INTERVAL", "120"))   # açık pozisyonları 2 dakikada bir gerçek teklifle değerle
KAYNAK_KONTROL = int(os.getenv("KAYNAK_KONTROL_SN", "900"))
SEVIYE_YENILE = 1800                                   # cüzdan seviyeleri (kadro ölçümü) yarım saatte bir yenilenir   # 15 dk'da bir: kaynak token'ı satmadan elden çıkardı mı?

def short(a): return a[:4] + "…" + a[-4:]

def show(r):
    print(f"  SİNYAL [{r['source']}] {r['side']} {short(r['token'])} cüzdan {short(r['wallet'])} "
          f"gecikme {r['latency_s']:.0f} sn -> {r['decision']} ({r['reason']})", flush=True)

BASLANGIC = time.time()

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
    from nexora import ekosistem as _eko                 # N23: bu takip yalnızca Solana adreslerini izler
    yanlis = [w for w in wallets if _eko.tespit(w) != "solana"]
    for w in yanlis:
        print(f"  {short(w)}: Solana adresi değil, izlenmeyecek (BNB/Base cüzdanları wallets_bnb.txt / wallets_base.txt'e, N24 ile)", flush=True)
    wallets = [w for w in wallets if w not in yanlis]
    # Platform 2: borsa cüzdanları (wallets_borsa.txt) da izlenir; platform 1'de yalnızca izlenir, alımları kopyalanmaz
    borsa_cuz = [w for w in read_list("wallets_borsa.txt") if w not in black and w not in wallets]
    wallets += borsa_cuz
    # Gölge havuz (golge_listesi.txt): yalnızca izlenir ve etiketlenir, KOPYALANMAZ (yapay zekâ verisi, teyit ölçümü)
    golge_cuz = [w for w in dict.fromkeys(read_list("golge_listesi.txt")) if w not in black and w not in wallets and _eko.tespit(w) == "solana"]
    wallets += golge_cuz
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
        bilgi = Toplayici(TokenBilgi(api_key=quoter.api_key, throttle=quoter._throttle), paper).baslat()
        puanlar, cuzdan_ist = {}, {}
        if os.path.exists("cuzdan_analiz.csv"):
            import csv
            for r in csv.DictReader(open("cuzdan_analiz.csv", newline="")):
                try: puanlar[r["wallet"]] = float(r.get("skor") or 0)
                except ValueError: pass
                cuzdan_ist[r["wallet"]] = {k: r.get(k) for k in ("karar", "kazanma_orani", "kar_faktoru", "ort_getiri", "kapanan",
                                                                  "medyan_tutma_sn", "skor", "dusus_kazanc_orani", "sifir_tur_orani")}
        izle = [w for w in read_list("izle_listesi.txt") if w in wallets] + borsa_cuz + golge_cuz
        model = ModelDosyasi()                            # N19/N20: yz_model.json (yalnızca N18'de kabul edilmiş model)
        kapi = ModelKapisi(model, bilgi=TokenBilgi(api_key=quoter.api_key, throttle=quoter._throttle), cuzdanlar=cuzdan_ist)
        decider = Decider(paper, quoter, TokenSafety(client), bilgi=bilgi, yurutme=YurutmeOlcer(quoter, paper).baslat(),
                          puanlar=puanlar, izle=izle, kapi=kapi)
        kd = kapi.durum()
        if kd["acik"]: print(f"  Model filtresi AÇIK (model {kd['model'] or 'YOK: filtre uygulanmıyor'})", flush=True)
        if izle: print(f"  {len(izle)} cüzdan yalnızca izleniyor (izle listesi, borsa, gölge havuz {len(golge_cuz)}): "
                       f"sinyalleri etiketlenir, alımları kopyalanmaz", flush=True)
        if not quoter.api_key:
            print("  Not: JUPITER_API_KEY yok, teklifler anahtarsız (0.5 istek/sn). Ücretsiz anahtar hızlandırır.", flush=True)
    etiketci = None
    if decider and os.getenv("ETIKET", "1") != "0":       # N16: her sinyali etiketle (yalnızca ölçüm)
        etiketci = Etiketci(os.getenv("ETIKET_DB", "nexora_etiket.db"), quoter, bilgi=TokenBilgi(api_key=quoter.api_key),
                            cuzdanlar=cuzdan_ist, model=model).baslat()
    borsa = None
    # 22.11.2026 (genel onay): Platform 2 borsa portföyü 14 günde %-23,5 (79 kapanan, 100$ -> 80$). Solana sinyalini borsa
    # fiyatıyla uygulamak kazandırmıyor -> varsayılan KAPALI; geçmiş veri korunur. Yeniden açmak: BORSA=1.
    if os.getenv("BORSA", "0") == "1":                    # Platform 2 (borsa): liste varsa ayrı paper portföy
        from nexora import borsa_liste
        from nexora.borsa_motor import BorsaMotoru
        bl = borsa_liste.yukle()
        if bl:
            borsa = BorsaMotoru(Paper(os.getenv("BORSA_DB", "nexora_borsa.db"), kayma=0.0005, ucret_orani=0.001, ekosistem="borsa"), bl).baslat()
            print(f"  Platform 2 (borsa): {len(bl)} listeli token, {len(borsa_cuz)} borsa cüzdanı (paper)", flush=True)
    tr = LiveTracker(client, paper, os.getenv("TRACKER_DB", "nexora_tracker.db"), wallets, decider=decider, etiketci=etiketci,
                     borsa=borsa)
    n = tr.reset_quarantine()
    if n: print(f"{n} cüzdan karantinadan çıkarıldı (yeniden deneniyor)", flush=True)
    if os.getenv("CLEAR_BOT") == "1":
        for w in tr.bot_wallets(): tr.clear_bot_flag(w)
    for w in tr.bot_wallets():
        print(f"  {short(w)}: yüksek frekans (bot) işaretli, izlenmiyor. "
              f"wallets.txt'ten çıkarın ya da CLEAR_BOT=1 ile yeniden deneyin.", flush=True)
    paper.nabiz()
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
    def seviye_yenile():
        if os.getenv("SEVIYE", "1") == "0": return
        try:
            from nexora import kadro
            paper.seviye = kadro.seviyeler(kadro.olcum(os.getenv("ETIKET_DB", "nexora_etiket.db")))
            say = {}
            for w in wallets:
                if paper.seviye: say[paper.cuzdan_seviyesi(w)] = say.get(paper.cuzdan_seviyesi(w), 0) + 1
            if say: print("  Cüzdan seviyeleri: " + ", ".join(f"{k} {v}" for k, v in sorted(say.items())), flush=True)
            elif kadro.MOD == "herkes": print("  Kadro modu 'herkes': seviyeler kapalı, boyut ve sınır ayarlardan", flush=True)
            from nexora.decision import Decider as _D
            print(f"  Güçlendirme {_D.GUC_KAT:g}x; gölge havuz teyidi {'AÇIK' if _D.GOLGE_TEYIT else 'kapalı (yalnızca ölçülüyor)'}", flush=True)
        except Exception as e:
            print(f"  seviyeler okunamadı ({type(e).__name__}): eski seviyeler geçerli", flush=True)
    seviye_yenile()
    last_mark = last_kaynak = last_seviye = time.time()
    liste_izi = {f: (os.path.getmtime(f) if os.path.exists(f) else None) for f in ("wallets.txt", "izle_listesi.txt", "golge_listesi.txt")}
    try:
        while True:
            stop.wait(INTERVAL)
            if any((os.path.getmtime(f) if os.path.exists(f) else None) != v for f, v in liste_izi.items()):
                print("Takip listesi değişti (kadro): yeni listeyle yeniden başlatılıyor.", flush=True)
                raise SystemExit(0)                     # systemd (Restart=always) birkaç saniyede yeniden başlatır
            st0 = tr.latency_stats()
            paper.nabiz(saglik=dict(
                baslangic=BASLANGIC, ws=("kapalı" if not USE_WS else "bağlı" if listener and listener.connected else "bağlı değil"),
                ws_kopma=listener.kopma if listener else 0, ws_son_mesaj=listener.son_mesaj if listener else None,
                okunamayan=tr.failed_count(), cuzdan=len(tr.active_wallets()), bot=len(tr.bot_wallets()),
                gecikme={k: dict(n=v["n"], p50=v["p50"], p95=v["p95"]) for k, v in st0.items()}))
            if decider and time.time() - last_mark >= MARK_EVERY:
                last_mark = time.time()
                ok, bad = decider.mark_to_market()
                if bad: print(f"  değerleme: {ok} pozisyon güncellendi, {bad} için teklif alınamadı", flush=True)
                if borsa is not None:
                    try: borsa.degerle()
                    except Exception: pass
            if time.time() - last_seviye >= SEVIYE_YENILE:
                last_seviye = time.time(); seviye_yenile()
            if decider and time.time() - last_kaynak >= KAYNAK_KONTROL:
                last_kaynak = time.time()
                try:
                    for t, karar, neden in decider.kaynak_denetimi(lambda w, t: kaynak_bakiyesi(client, w, t)):
                        print(f"  kaynakta token kalmadı: {short(t)} -> {karar} ({neden})", flush=True)
                    decider.kismi_zaman_asimi()
                    for t, karar, neden in decider.zaman_asimi():
                        print(f"  zaman aşımı: {short(t)} -> {karar} ({neden})", flush=True)
                except Exception as e:
                    print(f"  kaynak denetimi yapılamadı: {type(e).__name__}", flush=True)
            for w, res in tr.poll_all().items():
                if res == "hata": print(f"  {short(w)}: hata (karantinaya yaklaşıyor olabilir)", flush=True)
            for r in tr.last_poll_rows:                 # WebSocket'in kaçırıp yoklamanın bulduğu
                show(r)
            try:                                        # N2: erken sinyallerin zincirde kesinleşmesi
                k = tr.verify_finality()
                for u in k["uyarilar"]:
                    print(f"  UYARI kesinlik: kopyalanan {u['side']} {short(u['token'])} ({short(u['wallet'])}) "
                          f"zincirde {'başarısız' if u['kesinlik'] == 'hatali' else 'kesinleşmedi'}", flush=True)
            except Exception as e:
                print(f"  kesinlik kontrolü yapılamadı: {e}", flush=True)
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

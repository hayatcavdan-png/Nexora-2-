"""Aday cüzdanların kârlılık analizi. Salt okunur; wallets.txt'e dokunmaz.

Cüzdan başına TEK istek: Helius getTransactionsForAddress (tam işlem, son ANALIZ_LIMIT işlem).
Maliyet: 100 işlem başına 10 kredi (varsayılan 200 işlem = cüzdan başına 20 kredi).

Çalıştır (backend klasöründe, HELIUS_API_KEY tanımlıyken):
  python cuzdan_analiz.py              # cuzdan_tarama.csv'deki ölçülü adaylar + wallets.txt
  python cuzdan_analiz.py liste.txt    # belirli bir liste
  ANALIZ_HEPSI=1 python cuzdan_analiz.py   # tüm adaylar (daha fazla kredi)
Çıktılar: cuzdan_analiz.csv (tüm sonuçlar; önceki analizlerle birleştirilir, aynı cüzdanın satırı güncellenir), wallets_onerilen.txt (kopyalanabilirler, en iyisi önce)"""
import csv, os, re, sys, time
from nexora.helius_client import HeliusClient, HeliusRPCError
from nexora.market import JupiterQuoter, QuoteError
from nexora.constants import WSOL_MINT, USDC_MINT
from nexora.wallet_analysis import analyze, verdict, score, THRESHOLDS
from nexora import hesap_turu

LIMIT = int(os.getenv("ANALIZ_LIMIT", "200"))
OUT_CSV, OUT_TXT = "cuzdan_analiz.csv", "wallets_onerilen.txt"
ADDR = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
FIELDS = ["wallet", "karar", "gerekce", "gerceklesen_usd", "kapanan", "kazanma_orani", "kar_faktoru", "ort_getiri",
          "medyan_tutma_sn", "en_buyuk_token_payi", "token_sayisi", "swap", "alis", "satis", "eslesmeyen_satis",
          "acik_pozisyon", "ort_alis_usd", "pencere_gun", "islem", "hesap_ac_kapa", "sifir_tur_orani", "tek_token_tur", "skor",
          "max_dusus_usd", "dusus_kazanc_orani"]

def read_list(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]

def candidates(path=None):
    if path: return read_list(path)
    out = []
    if os.path.exists("cuzdan_tarama.csv"):
        hepsi = os.getenv("ANALIZ_HEPSI") == "1"
        for r in csv.DictReader(open("cuzdan_tarama.csv")):
            if r["durum"] != "aday": continue
            n, peak = int(r["islem_24s"] or 0), int(r["max_10dk"] or 0)
            if hepsi or (5 <= n < 60 and peak <= 10): out.append(r["wallet"])
    out += read_list("wallets.txt")
    return out

def sol_price(quoter):
    env = os.getenv("SOL_USD")
    if env: return float(env)
    q = quoter.quote(WSOL_MINT, USDC_MINT, 10 ** 9)
    return q["out_amount"] / 10 ** 6

def fetch(client, wallet):
    res = client.call("getTransactionsForAddress", [wallet, {
        "transactionDetails": "full", "limit": LIMIT, "sortOrder": "desc", "commitment": "confirmed",
        "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1,
        "filters": {"status": "succeeded", "tokenAccounts": "balanceChanged"}}])
    if not isinstance(res, dict) or not isinstance(res.get("data"), list):
        raise ValueError("geçersiz yanıt")
    return res["data"]

def main(client=None, quoter=None, sleep=time.sleep, list_path=None):
    if client is None and not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil: read -s HELIUS_API_KEY && export HELIUS_API_KEY")
    black = set(read_list("kara_liste.txt"))
    wallets = [w for w in dict.fromkeys(candidates(list_path)) if ADDR.match(w) and w not in black]
    if not wallets: sys.exit("Analiz edilecek cüzdan yok (önce cuzdan_tarama.py çalıştırın)")
    try:
        price = sol_price(quoter or JupiterQuoter())
    except (QuoteError, ValueError) as e:
        sys.exit(f"SOL fiyatı alınamadı ({e}). Elle verin: SOL_USD=140 python cuzdan_analiz.py")
    print(f"{len(wallets)} cüzdan, cüzdan başına son {LIMIT} işlem, SOL ≈ {price:.2f} USD "
          f"(tahmini maliyet ≈ {len(wallets) * max(10, -(-LIMIT // 100) * 10)} Helius kredisi)", flush=True)
    client = client or HeliusClient(max_retries=2)
    rows = []
    try:                                                            # N3: borsa/protokol/program hesaplarını ayır (100 adres = 1 istek)
        turler = hesap_turu.siniflandir(client, wallets, hesap_turu.bilinenler())
    except (HeliusRPCError, ValueError, OSError) as e:
        turler = {}; print(f"  Not: hesap türü denetlenemedi ({str(e)[:60]}); analiz türsüz sürüyor", flush=True)
    disla = {w: t for w, t in turler.items() if t[0] != hesap_turu.KULLANICI}
    for w, (t, why) in disla.items():
        rows.append(dict(wallet=w, karar="kullanıcı değil", gerekce=f"{t}: {why}"))
    if disla: print(f"  {len(disla)} adres kullanıcı cüzdanı değil, analiz edilmeyecek", flush=True)
    wallets = [w for w in wallets if w not in disla]
    for i, w in enumerate(wallets, 1):
        try:
            m = analyze(fetch(client, w), w, price)
            karar, why = verdict(m)
            rows.append(dict(m, karar=karar, gerekce="; ".join(why), skor=round(score(m), 4) if karar == "kopyalanabilir" else 0))
        except (HeliusRPCError, ValueError, OSError) as e:
            rows.append(dict(wallet=w, karar="hata", gerekce=str(e)[:80]))
        if i % 5 == 0 or i == len(wallets): print(f"  {i}/{len(wallets)} analiz edildi", flush=True)
        sleep(0.2)

    birlesik = {}                                                    # önceki sonuçlar korunur (takip ve etiketleme bu dosyayı okur)
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("wallet"): birlesik[r["wallet"]] = r
    for r in rows: birlesik[r["wallet"]] = r
    with open(OUT_CSV, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore"); wr.writeheader(); wr.writerows(birlesik.values())
    good = sorted((r for r in rows if r["karar"] == "kopyalanabilir"), key=lambda r: -r["skor"])
    with open(OUT_TXT, "w") as f:
        f.write("# Kârlılık analizinden geçen cüzdanlar (en iyisi önce). wallets.txt'e kopyalamadan önce gözden geçirin.\n")
        for r in good: f.write(r["wallet"] + "\n")

    counts = {}
    for r in rows: counts[r["karar"]] = counts.get(r["karar"], 0) + 1
    print("\nSonuç:", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
    print(f"Eşikler: en az {THRESHOLDS['min_closed']} kapanmış satış, kazanma ≥ %{THRESHOLDS['min_win_rate']*100:.0f}, "
          f"kâr faktörü ≥ {THRESHOLDS['min_profit_factor']}, işlem başı getiri ≥ %{THRESHOLDS['min_mean_return']*100:.0f}, "
          f"medyan tutma ≥ {THRESHOLDS['min_hold_s']} sn")
    show = good[:10] or sorted((r for r in rows if r.get("kapanan")), key=lambda r: -r.get("gerceklesen_usd", 0))[:5]
    print("\nKopyalanabilir cüzdanlar:" if good else "\nKopyalanabilir cüzdan çıkmadı. En yüksek gerçekleşen K/Z'ye sahip 5 cüzdan:")
    for r in show:
        print(f"  {r['wallet'][:4]}…{r['wallet'][-4:]}  K/Z {r['gerceklesen_usd']:+.0f}$  {r['kapanan']} satış  "
              f"kazanma %{100 * r['kazanma_orani']:.0f}  KF {r['kar_faktoru']}  ort %{100 * r['ort_getiri']:.0f}  "
              f"tutma {r['medyan_tutma_sn']} sn  [{r['karar']}]")
    if not good: print("  (gerekçeler cuzdan_analiz.csv dosyasında)")
    if disla:
        print(f"\nKullanıcı cüzdanı olmayan adresler ({len(disla)}):")
        for w, (t, why) in disla.items(): print(f"  {w[:4]}…{w[-4:]}  {t} ({why})")
    bots = [r for r in rows if r["karar"] == "bot şüphesi"]
    if bots:
        print(f"\nHacim botu şüphesi ({len(bots)}): kara_liste.txt'e eklemeyi düşünün (otomatik eklenmez):")
        for r in bots: print(f"  {r['wallet']}  ({r['gerekce']})")
    sw = sum(r.get("swap", 0) for r in rows); ak = sum(r.get("hesap_ac_kapa", 0) for r in rows)
    print(f"\nVeri kalitesi: {sw} swap çözüldü, {ak} işlem token hesabı açma/kapama nedeniyle atlandı"
          + (" (yüksek: çözücü iyileştirmesi gerekebilir)" if sw and ak > sw * 0.3 else ""))
    return rows

if __name__ == "__main__":
    try: main(list_path=sys.argv[1] if len(sys.argv) > 1 else None)
    except KeyboardInterrupt: print("\nDurduruldu.")

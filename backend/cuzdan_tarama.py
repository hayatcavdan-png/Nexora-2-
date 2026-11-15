"""413 cüzdanın son aktivitesini tarar; pasif, bot ve aday cüzdanları ayırır.
Cüzdan başına TEK hafif istek (getSignaturesForAddress, son 100 imza). Salt okunur.
Kaldığı yerden devam eder: sonuçlar CSV'ye satır satır yazılır.

Çalıştır (backend klasöründe, HELIUS_API_KEY tanımlıyken):
  python cuzdan_tarama.py [giriş_dosyası]
Çıktılar:
  cuzdan_tarama.csv   tüm sonuçlar
  wallets_aday.txt    takip için önerilen adaylar (wallets.txt'e kendiniz kopyalarsınız)"""
import csv, os, re, sys, time
from nexora.helius_client import HeliusClient, HeliusRPCError

INPUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/storage/downloads/NEXORA_413_WALLETS.txt")
OUT_CSV, OUT_ADAY = "cuzdan_tarama.csv", "wallets_aday.txt"
FIELDS = ["wallet", "durum", "islem_24s", "islem_7g", "son_islem_saat", "max_10dk", "hatali_orani", "not"]
ADDR = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

PASIF_SAAT = 72        # son 3 gündür işlem yoksa pasif
BOT_10DK = 30          # 10 dakikada 30+ işlem: bot (canlı takipteki sınırla aynı)
BOT_24S = 300          # 24 saatte 300+ işlem: bot
ADAY_MIN_24S = 2       # aday için 24 saatte en az 2 işlem
PAUSE = float(os.getenv("TARAMA_BEKLEME", "0.15"))

def classify(sigs, now):
    times = sorted((s["blockTime"] for s in sigs if isinstance(s.get("blockTime"), int)), reverse=True)
    if not times:
        return dict(durum="pasif", islem_24s=0, islem_7g=0, son_islem_saat="", max_10dk=0, hatali_orani=0, **{"not": "işlem yok"})
    n24 = sum(1 for t in times if now - t <= 86400)
    n7 = sum(1 for t in times if now - t <= 7 * 86400)
    last_h = (now - times[0]) / 3600
    asc = times[::-1]; j = 0; peak = 0
    for i, t in enumerate(asc):                     # kayan 10 dk penceresinde en yüksek işlem sayısı
        while t - asc[j] > 600: j += 1
        peak = max(peak, i - j + 1)
    errs = sum(1 for s in sigs if s.get("err") is not None) / len(sigs)
    note = ""
    if len(times) >= 100 and now - times[-1] < 86400:
        n24 = max(n24, 100); note = "son 100 işlem 24 saatten kısa sürede (en az 100/gün)"
    if peak >= BOT_10DK or n24 >= BOT_24S:
        durum = "bot"
    elif last_h > PASIF_SAAT:
        durum = "pasif"
    elif errs > 0.5:
        durum = "şüpheli"; note = note or "işlemlerin yarısından fazlası başarısız"
    elif n24 >= ADAY_MIN_24S:
        durum = "aday"
    else:
        durum = "düşük aktivite"
    return dict(durum=durum, islem_24s=n24, islem_7g=n7, son_islem_saat=round(last_h, 1),
                max_10dk=peak, hatali_orani=round(errs, 2), **{"not": note})

def load_done():
    if not os.path.exists(OUT_CSV): return {}
    with open(OUT_CSV, newline="") as f:
        rows = {r["wallet"]: r for r in csv.DictReader(f)}     # son satır geçerli
    return {w: r for w, r in rows.items() if r["durum"] != "hata"}   # hatalılar yeniden denenir

def main(client=None, now_fn=time.time, sleep=time.sleep):
    if client is None and not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil: read -s HELIUS_API_KEY && export HELIUS_API_KEY")
    if not os.path.exists(INPUT): sys.exit(f"Giriş dosyası yok: {INPUT}")
    raw = [l.strip() for l in open(INPUT) if l.strip()]
    wallets = list(dict.fromkeys(w for w in raw if ADDR.match(w)))
    bad = len(raw) - len(wallets)
    print(f"{len(wallets)} geçerli cüzdan" + (f", {bad} geçersiz/yinelenen satır atlandı" if bad else ""))
    done = load_done()
    todo = [w for w in wallets if w not in done]
    if done: print(f"{len(done)} cüzdan daha önce taranmış, {len(todo)} kaldı")
    client = client or HeliusClient(max_retries=2)
    new_file = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file: wr.writeheader()
        for i, w in enumerate(todo, 1):
            try:
                sigs = client.call("getSignaturesForAddress", [w, {"limit": 100, "commitment": "confirmed"}])
                if not isinstance(sigs, list): raise ValueError("geçersiz yanıt")
                row = dict(wallet=w, **classify(sigs, now_fn()))
            except (HeliusRPCError, ValueError, OSError) as e:
                row = dict(wallet=w, durum="hata", islem_24s="", islem_7g="", son_islem_saat="",
                           max_10dk="", hatali_orani="", **{"not": str(e)[:80]})
            wr.writerow(row); f.flush(); done[w] = row
            if i % 25 == 0 or i == len(todo): print(f"  {i}/{len(todo)} tarandı", flush=True)
            sleep(PAUSE)

    rows = [done[w] for w in wallets if w in done]
    counts = {}
    for r in rows: counts[r["durum"]] = counts.get(r["durum"], 0) + 1
    print("\nSonuç:", ", ".join(f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
    aday = sorted((r for r in rows if r["durum"] == "aday"), key=lambda r: -int(r["islem_24s"] or 0))
    with open(OUT_ADAY, "w") as f:
        f.write("# Aktif ve bot olmayan adaylar (24 saatteki işlem sayısına göre). wallets.txt'e kopyalamadan önce gözden geçirin.\n")
        for r in aday: f.write(r["wallet"] + "\n")
    print(f"\nEn aktif 10 aday (toplam {len(aday)}, hepsi {OUT_ADAY} dosyasında):")
    for r in aday[:10]:
        print(f"  {r['wallet'][:4]}…{r['wallet'][-4:]}  24s: {r['islem_24s']:>3}  7g: {r['islem_7g']:>3}  "
              f"son işlem: {r['son_islem_saat']} sa önce  10dk tepe: {r['max_10dk']}")
    hata = counts.get("hata", 0)
    if hata: print(f"\n{hata} cüzdanda hata oldu. Komutu tekrar çalıştırın: yalnızca hatalı ve kalan cüzdanlar denenir.")
    return counts

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nDurduruldu. Tekrar çalıştırınca kaldığı yerden devam eder.")

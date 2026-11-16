"""Zincirden yeni cüzdan keşfi (N3). Salt okunur; wallets.txt'e DOKUNMAZ.

Fikir: Takip ettiğimiz cüzdanların aldığı token'ları, onlardan ÖNCE (KESIF_PENCERE_SN içinde) alan cüzdanlar
iyi token'ları erken bulanlar olabilir. Birden çok token'da erken alıcı olarak görünen cüzdanlar aday sayılır.
Adaylar daha sonra kârlılık analizinden geçmelidir:  python cuzdan_analiz.py wallets_kesif.txt

Maliyet: token başına TEK istek (Helius getTransactionsForAddress, en fazla KESIF_LIMIT işlem; 100 işlem = 10 kredi).
Varsayılan 10 token x 100 işlem = yaklaşık 100 kredi. Başlamadan önce tahmini maliyet yazılır.

Çalıştır (backend klasöründe, HELIUS_API_KEY tanımlıyken):  python cuzdan_kesif.py
Ayarlar: KESIF_TOKEN=10  KESIF_LIMIT=100  KESIF_SAYFA=1  KESIF_PENCERE_SN=3600  KESIF_EN_AZ=2
Hızlı al-satçılar (aynı token'ı KESIF_MIN_TUTMA_SN içinde satanlar; çoğu sniper bot) aday sayılmaz: kopyalanamazlar.
Çıktılar: kesif_adaylar.csv (tüm erken alıcılar), wallets_kesif.txt (en az KESIF_EN_AZ token'da görünenler)"""
import csv, os, sqlite3, sys
from collections import defaultdict

from nexora.helius_client import HeliusClient, HeliusRPCError
from nexora.swap_decoder import decode_swap
from nexora.hesap_turu import egri_ustunde

TOKEN_SAYI = int(os.getenv("KESIF_TOKEN", "10"))
LIMIT = int(os.getenv("KESIF_LIMIT", "100"))
PENCERE = int(os.getenv("KESIF_PENCERE_SN", "3600"))
EN_AZ = int(os.getenv("KESIF_EN_AZ", "2"))
SAYFA = max(1, int(os.getenv("KESIF_SAYFA", "1")))
MIN_TUTMA = int(os.getenv("KESIF_MIN_TUTMA_SN", "60"))
OUT_CSV, OUT_TXT = "kesif_adaylar.csv", "wallets_kesif.txt"


def read_list(path):
    if not os.path.exists(path): return []
    return [l.strip() for l in open(path) if l.strip() and not l.lstrip().startswith("#")]


def kaynak_alimlar(tracker_db, n):
    """Takipteki cüzdanların en son n FARKLI token alımı: (token, kaynak cüzdan, blok zamanı)."""
    if not os.path.exists(tracker_db): return []
    c = sqlite3.connect(f"file:{tracker_db}?mode=ro", uri=True)
    try:
        rows = c.execute("""SELECT token, wallet, block_time FROM tracker_signals WHERE side='BUY' AND block_time > 0
                            ORDER BY id DESC""").fetchall()
    finally:
        c.close()
    out, gorulen = [], set()
    for token, wallet, bt in rows:
        if token in gorulen: continue
        gorulen.add(token); out.append((token, wallet, int(bt)))
        if len(out) >= n: break
    return out


def odeyici(tx):
    keys = ((tx.get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    if not keys: return None
    k = keys[0]
    return k.get("pubkey") if isinstance(k, dict) else k


def erken_alicilar(client, token, bt, pencere=PENCERE, limit=LIMIT, sayfa=SAYFA, min_tutma=MIN_TUTMA):
    """Token'ı [bt-pencere, bt) aralığında alan cüzdanlar, hızlı al-satçılar hariç.
    Dönüş: (alıcılar, işlem sayısı, elenen hızlı al-satçı sayısı). Helius zaman filtresini desteklemezse istemci tarafında süzülür."""
    opts = {"transactionDetails": "full", "limit": limit, "sortOrder": "desc", "commitment": "confirmed",
            "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1,
            "filters": {"status": "succeeded", "blockTime": {"gte": bt - pencere, "lt": bt}}}
    txs = []
    for _ in range(sayfa):
        try:
            res = client.call("getTransactionsForAddress", [token, dict(opts)])
        except HeliusRPCError as e:
            if getattr(e, "rpc_code", None) != -32602: raise
            opts["filters"] = {"status": "succeeded"}               # filtre desteklenmiyorsa: son işlemler
            res = client.call("getTransactionsForAddress", [token, dict(opts)])
        veri = res.get("data") if isinstance(res, dict) else None
        if not isinstance(veri, list): raise ValueError("geçersiz yanıt")
        txs += veri
        sonraki = res.get("paginationToken") if isinstance(res, dict) else None
        if not sonraki or not veri: break
        opts["paginationToken"] = sonraki
    alis, satis = defaultdict(list), defaultdict(list)
    for tx in txs:
        if not isinstance(tx, dict): continue
        t = tx.get("blockTime") or 0
        if not (bt - pencere <= t < bt): continue
        w = odeyici(tx)
        if not w: continue
        try:
            r = decode_swap(tx, w)
        except (TypeError, ValueError):
            continue
        if r.get("token_mint") != token: continue
        if r.get("event_type") == "BUY": alis[w].append(t)
        elif r.get("event_type") == "SELL": satis[w].append(t)
    hizli = {w for w, ts in alis.items() if any(0 <= s - min(ts) < min_tutma for s in satis.get(w, ()))}
    return set(alis) - hizli, len(txs), len(hizli)


def main(client=None, tracker_db=None, out_dir="."):
    if client is None and not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil")
    alimlar = kaynak_alimlar(tracker_db or os.getenv("TRACKER_DB", "nexora_tracker.db"), TOKEN_SAYI)
    if not alimlar: sys.exit("Takip veritabanında henüz kaynak alımı yok: takip bir süre çalışmalı.")
    print(f"{len(alimlar)} token incelenecek, token başına en fazla {LIMIT} işlem "
          f"x {SAYFA} sayfa (tahmini en fazla {len(alimlar) * SAYFA * ((LIMIT + 99) // 100) * 10} Helius kredisi).", flush=True)
    client = client or HeliusClient(max_retries=2)
    bilinen = set(read_list("wallets.txt")) | set(read_list("kara_liste.txt")) | set(read_list("kesif_gorulen.txt"))
    for f in ("cuzdan_analiz.csv",):
        if os.path.exists(f): bilinen |= {r["wallet"] for r in csv.DictReader(open(f, newline=""))}
    gorulme = defaultdict(set)
    for token, kaynak, bt in alimlar:
        try:
            alicilar, n, elenen = erken_alicilar(client, token, bt)
        except (HeliusRPCError, ValueError) as e:
            print(f"  {token[:4]}…{token[-4:]}: atlandı ({e})", flush=True); continue
        alicilar -= {kaynak}
        print(f"  {token[:4]}…{token[-4:]}: {n} işlem, {len(alicilar)} erken alıcı"
              + (f" ({elenen} hızlı al-satçı elendi)" if elenen else ""), flush=True)
        for w in alicilar: gorulme[w].add(token)
    satir = sorted(((w, len(t), ";".join(sorted(t))) for w, t in gorulme.items()), key=lambda x: -x[1])
    with open(os.path.join(out_dir, OUT_CSV), "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["wallet", "token_sayisi", "tokenler", "yeni"])
        for w, n, t in satir: wr.writerow([w, n, t, int(w not in bilinen)])
    aday = [w for w, n, _ in satir if n >= EN_AZ and w not in bilinen and egri_ustunde(w)]
    with open(os.path.join(out_dir, OUT_TXT), "w") as f:
        f.write("# cuzdan_kesif.py çıktısı: analiz için  python cuzdan_analiz.py wallets_kesif.txt\n")
        f.writelines(w + "\n" for w in aday)
    print(f"\n{len(gorulme)} farklı erken alıcı; {len(aday)} yeni aday en az {EN_AZ} token'da göründü -> {OUT_TXT}")
    print("Sonraki adım: python cuzdan_analiz.py wallets_kesif.txt  (kopyalanabilir çıkanlar wallets_onerilen.txt'e yazılır)")
    return aday


if __name__ == "__main__":
    main()

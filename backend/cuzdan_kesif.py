"""Zincirden yeni cüzdan keşfi (N3). Salt okunur; wallets.txt'e DOKUNMAZ.

Fikir: Takip ettiğimiz cüzdanların aldığı token'ları, onlardan ÖNCE (KESIF_PENCERE_SN içinde) alan cüzdanlar
iyi token'ları erken bulanlar olabilir. Birden çok token'da erken alıcı olarak görünen cüzdanlar aday sayılır.
Adaylar daha sonra kârlılık analizinden geçmelidir:  python cuzdan_analiz.py wallets_kesif.txt

Maliyet: token başına TEK istek (Helius getTransactionsForAddress, en fazla KESIF_LIMIT işlem; 100 işlem = 10 kredi).
Varsayılan 10 token x 100 işlem = yaklaşık 100 kredi. Başlamadan önce tahmini maliyet yazılır.

Çalıştır (backend klasöründe, HELIUS_API_KEY tanımlıyken):  python cuzdan_kesif.py
Ayarlar: KESIF_TOKEN=10  KESIF_LIMIT=100  KESIF_SAYFA=1  KESIF_PENCERE_SN=3600  KESIF_EN_AZ=2
Hızlı al-satçılar (aynı token'ı KESIF_MIN_TUTMA_SN içinde satanlar; çoğu sniper bot) aday sayılmaz: kopyalanamazlar.
Sniperlar (token oluştuktan sonraki KESIF_SNIPER_SN içinde alanlar) da aday sayılmaz: o hızla girilemez.
Kazanan token'lar: takip edilen bir cüzdanın aldığı ve kopyasının (kaynak satınca çıkış) en az %KAZANAN_ESIK kazandırdığı
token'lar (etiket ölçümü) ayrıca incelenir (KESIF_KAZANAN=10 token): iyi token'ı erken bulanlar burada aranır.
Piyasa kazananları (22.11.2026): takip listemizden BAĞIMSIZ olarak Solana'da son günlerde en çok yükselen token'lar
(GeckoTerminal, anahtarsız) da incelenir (KESIF_PIYASA=25 token): her birinin havuzu açıldıktan sonraki ilk
KESIF_PIYASA_SAAT=4 saatte alan cüzdanlar (sniperlar ve hızlı al-satçılar hariç, en eskiden başlayarak) aday olur.
Böylece aday havuzu yalnızca bizim takip ettiklerimizin gezdiği token'larla sınırlı kalmaz.
Çıktılar: kesif_adaylar.csv (tüm erken alıcılar), wallets_kesif.txt (en az KESIF_EN_AZ token'da görünenler)"""
import csv, datetime, os, sqlite3, sys, time
from collections import defaultdict

import requests

from nexora.helius_client import HeliusClient, HeliusRPCError
from nexora.swap_decoder import decode_swap
from nexora.hesap_turu import egri_ustunde

TOKEN_SAYI = int(os.getenv("KESIF_TOKEN", "10"))
LIMIT = int(os.getenv("KESIF_LIMIT", "100"))
PENCERE = int(os.getenv("KESIF_PENCERE_SN", "3600"))
EN_AZ = int(os.getenv("KESIF_EN_AZ", "2"))
SAYFA = max(1, int(os.getenv("KESIF_SAYFA", "1")))
MIN_TUTMA = int(os.getenv("KESIF_MIN_TUTMA_SN", "60"))
SNIPER_SN = int(os.getenv("KESIF_SNIPER_SN", "120"))
KAZANAN = int(os.getenv("KESIF_KAZANAN", "10"))
KAZANAN_ESIK, KAZANAN_GUN = 20.0, 7
PIYASA = int(os.getenv("KESIF_PIYASA", "25"))
PIYASA_SAAT = float(os.getenv("KESIF_PIYASA_SAAT", "4"))
PIYASA_LIK, PIYASA_HACIM, PIYASA_YUKSELIS = 30_000.0, 100_000.0, 50.0     # en az likidite $, 24s hacim $, yükseliş %
PIYASA_YAS = (2 * 3600, 7 * 86400)                                       # havuz yaşı: 2 saat - 7 gün
GT_SOL = "https://api.geckoterminal.com/api/v2/networks/solana/"
TEMEL = {"So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
         "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}                   # SOL, USDC, USDT: kazanan token sayılmaz
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


def kazanan_alimlar(etiket_db, n, now=None, esik=KAZANAN_ESIK, gun=KAZANAN_GUN):
    """Kopyası en az %esik kazandıran son alımlar (en kazandıran önce, token başına bir): (token, kaynak, blok zamanı, oluşma zamanı)."""
    import time as _t
    now = now if now is not None else _t.time()
    if not n or not etiket_db or not os.path.exists(etiket_db): return []
    c = sqlite3.connect(f"file:{etiket_db}?mode=ro", uri=True)
    try:
        rows = c.execute("""SELECT o.token, o.wallet, o.block_time, o.ts, o.tb_yas_sn FROM etiket_olay o
            JOIN etiket_sonuc s ON s.event_id=o.event_id WHERE s.ufuk='kaynak' AND s.getiri_pct >= ? AND o.ts >= ?
            AND o.block_time > 0 ORDER BY s.getiri_pct DESC""", (esik, now - gun * 86400)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        c.close()
    out, gorulen = [], set()
    for token, wallet, bt, ts, yas in rows:
        if token in gorulen: continue
        gorulen.add(token)
        out.append((token, wallet, int(bt), (ts - yas) if yas is not None else None))
        if len(out) >= n: break
    return out


def _iso(v):
    try: return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError): return 0.0


def _f(v):
    try: return float(v or 0)
    except (TypeError, ValueError): return 0.0


def piyasa_kazananlari(n=PIYASA, s=None, now=None, uyku=time.sleep, timeout=15):
    """Solana'da son günlerde en çok yükselen token'lar (GeckoTerminal yükselen + en hacimli havuzlar).
    Dönüş: [(token, None, pencere_sonu, havuz_açılışı)] en çok yükselen önce, token başına bir."""
    if n <= 0: return []
    s = s or requests.Session(); now = now if now is not None else time.time()
    adaylar = {}
    for i, yol in enumerate(("trending_pools?duration=24h", "trending_pools?duration=24h&page=2", "trending_pools?duration=6h",
                             "pools?sort=h24_volume_usd_desc", "pools?sort=h24_volume_usd_desc&page=2")):
        if i: uyku(2.1)                                          # herkese açık hız sınırı (dakikada ~30 istek)
        try: d = s.get(GT_SOL + yol, timeout=timeout).json()
        except (requests.RequestException, ValueError): continue
        for p in (d.get("data") or []) if isinstance(d, dict) else []:
            a = p.get("attributes") or {}
            tid = ((((p.get("relationships") or {}).get("base_token") or {}).get("data") or {}).get("id") or "")
            tok = tid.split("_", 1)[-1]
            acilis = _iso(a.get("pool_created_at"))
            pc = a.get("price_change_percentage") or {}
            yuk = max(_f(pc.get("h24")), _f(pc.get("h6")))
            if (not tok or tok in TEMEL or not acilis or not (PIYASA_YAS[0] <= now - acilis <= PIYASA_YAS[1])
                    or _f(a.get("reserve_in_usd")) < PIYASA_LIK or _f((a.get("volume_usd") or {}).get("h24")) < PIYASA_HACIM
                    or yuk < PIYASA_YUKSELIS): continue
            if tok not in adaylar or yuk > adaylar[tok][0]: adaylar[tok] = (yuk, acilis)
    sirali = sorted(adaylar.items(), key=lambda x: -x[1][0])[:n]
    return [(tok, None, int(acilis + PIYASA_SAAT * 3600), acilis) for tok, (_, acilis) in sirali]


def odeyici(tx):
    keys = ((tx.get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    if not keys: return None
    k = keys[0]
    return k.get("pubkey") if isinstance(k, dict) else k


def erken_alicilar(client, token, bt, pencere=PENCERE, limit=LIMIT, sayfa=SAYFA, min_tutma=MIN_TUTMA, olusma=None,
                   sniper_sn=SNIPER_SN, sira="desc"):
    """Token'ı [bt-pencere, bt) aralığında alan cüzdanlar, hızlı al-satçılar ve (oluşma zamanı biliniyorsa) sniperlar hariç.
    Dönüş: (alıcılar, işlem sayısı, elenen hızlı al-satçı sayısı). Helius zaman filtresini desteklemezse istemci tarafında süzülür."""
    opts = {"transactionDetails": "full", "limit": limit, "sortOrder": sira, "commitment": "confirmed",
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
    if olusma is not None:
        hizli |= {w for w, ts in alis.items() if min(ts) - olusma < sniper_sn}
    return set(alis) - hizli, len(txs), len(hizli)


def main(client=None, tracker_db=None, out_dir=".", etiket_db=None, piyasa=None):
    if client is None and not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil")
    son = [(t, w, bt, None) for t, w, bt in kaynak_alimlar(tracker_db or os.getenv("TRACKER_DB", "nexora_tracker.db"), TOKEN_SAYI)]
    kaz = kazanan_alimlar(etiket_db or os.getenv("ETIKET_DB", "nexora_etiket.db"), KAZANAN)
    kaz_tok = {x[0] for x in kaz}
    alimlar = kaz + [x for x in son if x[0] not in kaz_tok]
    try: piy = (piyasa or piyasa_kazananlari)()
    except Exception as e:
        piy = []; print(f"Piyasa kazananları alınamadı ({type(e).__name__}); yalnızca takip kaynaklı keşif.", flush=True)
    piy = [x for x in piy if x[0] not in {a[0] for a in alimlar}]
    piy_tok = {x[0] for x in piy}
    alimlar += piy
    if not alimlar: sys.exit("Takip veritabanında henüz kaynak alımı yok: takip bir süre çalışmalı.")
    if kaz: print(f"{len(kaz)} kazanan token (kopyası en az %{KAZANAN_ESIK:.0f} kazandıran) incelenecek.", flush=True)
    if piy: print(f"{len(piy)} piyasa kazananı (son günlerde en az %{PIYASA_YUKSELIS:.0f} yükselen) incelenecek: "
                  f"havuz açıldıktan sonraki ilk {PIYASA_SAAT:g} saatin alıcıları.", flush=True)
    print(f"{len(alimlar)} token incelenecek, token başına en fazla {LIMIT} işlem "
          f"x {SAYFA} sayfa (tahmini en fazla {len(alimlar) * SAYFA * ((LIMIT + 99) // 100) * 10} Helius kredisi).", flush=True)
    client = client or HeliusClient(max_retries=2)
    bilinen = set(read_list("wallets.txt")) | set(read_list("kara_liste.txt")) | set(read_list("kesif_gorulen.txt"))
    for f in ("cuzdan_analiz.csv",):
        if os.path.exists(f): bilinen |= {r["wallet"] for r in csv.DictReader(open(f, newline=""))}
    gorulme = defaultdict(set)
    for token, kaynak, bt, olusma in alimlar:
        try:
            if token in piy_tok:
                alicilar, n, elenen = erken_alicilar(client, token, bt, pencere=int(PIYASA_SAAT * 3600), olusma=olusma, sira="asc")
            else:
                alicilar, n, elenen = erken_alicilar(client, token, bt, olusma=olusma)
        except (HeliusRPCError, ValueError) as e:
            print(f"  {token[:4]}…{token[-4:]}: atlandı ({e})", flush=True); continue
        alicilar -= {kaynak}
        print(f"  {'[piyasa] ' if token in piy_tok else ''}{token[:4]}…{token[-4:]}: {n} işlem, {len(alicilar)} erken alıcı"
              + (f" ({elenen} hızlı al-satçı/sniper elendi)" if elenen else ""), flush=True)
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

"""Takipçi kaybı raporu: kopyalanan her işlemde kaynağa göre ne kadar kaybettik? (salt okunur)
Çalıştır (backend klasöründe, HELIUS_API_KEY tanımlıyken): python takip_kaybi.py
Kaynak işlem başına bir Helius isteği (getTransaction). Sonuç: takip_kaybi.json (uygulama okur)."""
import json, os, sqlite3, sys, time
from nexora.helius_client import HeliusClient
from nexora.market import JupiterQuoter, QuoteError
from nexora.constants import WSOL_MINT, USDC_MINT
from nexora.takip_kaybi import analyze, teshis

def pct(x): return "—" if x is None else f"%{100 * x:+.1f}"

def main(client=None, quoter=None, paper_path=None, out="takip_kaybi.json"):
    paper_path = paper_path or os.getenv("NEXORA_DB", "nexora_paper.db")
    if not os.path.exists(paper_path): sys.exit("Paper veritabanı yok.")
    if client is None and not os.getenv("HELIUS_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
        sys.exit("HELIUS_API_KEY tanımlı değil: read -s HELIUS_API_KEY && export HELIUS_API_KEY")
    c = sqlite3.connect(f"file:{paper_path}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    trades = [dict(r) for r in c.execute("SELECT * FROM trades WHERE decision='KOPYALANDI' ORDER BY id")]; c.close()
    if not trades: sys.exit("Henüz kopyalanan işlem yok.")
    try:
        q = (quoter or JupiterQuoter()).quote(WSOL_MINT, USDC_MINT, 10 ** 9); sol = q["out_amount"] / 1e6
    except (QuoteError, KeyError):
        sol = float(os.getenv("SOL_USD", "0") or 0)
        if sol <= 0: sys.exit("SOL fiyatı alınamadı. Elle verin: SOL_USD=140 python takip_kaybi.py")
    client = client or HeliusClient(max_retries=2)
    res = analyze(trades, client.get_transaction, sol)
    res["olusturma"] = time.time()
    with open(out, "w") as f: json.dump(res, f, ensure_ascii=False, indent=1)

    print(f"SOL ≈ {sol:.2f} USD · {len(res['islemler'])} kopya tur\n")
    for r in res["islemler"]:
        kz = "" if r["bizim_kz"] is None else f"  bizim K/Z {r['bizim_kz']:+.2f}$ ({pct(r['bizim_getiri'])})"
        print(f"{r['cuzdan'][:4]}…{r['cuzdan'][-4:]}  {r['token'][:4]}…{r['token'][-4:]}  [{r['durum']}]{kz}")
        print(f"   {teshis(r)}" + (f", tutma {int(r['tutma_sn'])} sn" if r["tutma_sn"] is not None else ""))
    print("\nCüzdan bazında ortalama:")
    for w in res["cuzdanlar"]:
        print(f"  {w['cuzdan'][:4]}…{w['cuzdan'][-4:]}  {w['islem']} tur ({w['kapanan']} kapanan)  giriş kaybı {pct(w['giris_kaybi_ort'])}  "
              f"çıkış kaybı {pct(w['cikis_kaybi_ort'])}  kaynak {pct(w['kaynak_getiri_ort'])}  bizim {pct(w['bizim_getiri_ort'])}")
    print("\nOkuma: giriş kaybı +%5 = kaynaktan %5 pahalıya aldık; çıkış kaybı +%5 = kaynaktan %5 ucuza sattık.")
    return res

if __name__ == "__main__":
    main()

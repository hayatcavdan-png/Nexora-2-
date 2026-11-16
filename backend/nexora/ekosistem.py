"""Ekosistem çekirdeği (N23): sistemin tanıdığı ekosistemler, adres biçiminden ekosistem tespiti ve ekosistem bazında özet.

Her ekosistemin cüzdanları AYRI dosyada tutulur (geriye uyumlu: Solana için mevcut wallets.txt). Paper veritabanlarındaki
her işlem ve pozisyon bir ekosistem etiketi taşır (eski kayıtlar 'solana'). Platform 2'nin borsa portföyleri 'borsa'dır.
Yeni bir ekosistem eklemek = bu listeye bir satır + o ekosistemin bağdaştırıcısı (takip, swap çözücü, teklif, güvenlik)."""
import os, re, sqlite3

EKOSISTEMLER = [
    dict(id="solana", ad="Solana", tur="solana", zincir_id=None, cuzdan_dosyasi="wallets.txt", aktif=True, asama="N0–N22"),
    dict(id="bnb", ad="BNB Chain", tur="evm", zincir_id=56, cuzdan_dosyasi="wallets_bnb.txt", aktif=True, asama="N24 (paper)"),
    dict(id="base", ad="Base", tur="evm", zincir_id=8453, cuzdan_dosyasi="wallets_base.txt", aktif=False, asama="N25"),
    dict(id="ton", ad="TON", tur="ton", zincir_id=None, cuzdan_dosyasi="wallets_ton.txt", aktif=False, asama="N27"),
    dict(id="borsa", ad="Borsalar (Binance, OKX, KuCoin, MEXC)", tur="borsa", zincir_id=None, cuzdan_dosyasi=None, aktif=True, asama="N22"),
]
KIMLIKLER = {e["id"] for e in EKOSISTEMLER}
VARSAYILAN = "solana"

_SOLANA = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_EVM = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TON = re.compile(r"^(?:[EUk0][Qf][A-Za-z0-9_-]{46}|-?\d:[0-9a-fA-F]{64})$")


def bul(eid):
    return next((e for e in EKOSISTEMLER if e["id"] == eid), None)


def tespit(adres):
    """Adres biçiminden teknoloji: 'solana' | 'evm' | 'ton' | None. EVM adresi hangi zincir olduğunu söylemez (BNB/Base aynı biçim)."""
    if not isinstance(adres, str): return None
    a = adres.strip()
    if _EVM.match(a): return "evm"
    if _TON.match(a): return "ton"
    if _SOLANA.match(a): return "solana"
    return None


def cuzdanlar(eid, kok="."):
    """Ekosistemin cüzdan dosyasındaki, biçimi o ekosisteme uyan adresler (yorum ve hatalı satırlar atlanır)."""
    e = bul(eid)
    if not e or not e["cuzdan_dosyasi"]: return []
    yol = os.path.join(kok, e["cuzdan_dosyasi"])
    if not os.path.exists(yol): return []
    with open(yol) as f:
        satir = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    return [a for a in satir if tespit(a) == e["tur"]]


def ozet(db_yollari, kok="."):
    """Ekosistem başına: cüzdan sayısı, kopyalanan alım, kapanan işlem, gerçekleşen K/Z, açık pozisyon. Salt okunur."""
    say = {e["id"]: dict(kopya=0, kapanan=0, kz=0.0, acik=0) for e in EKOSISTEMLER}
    for yol in db_yollari:
        if not yol or not os.path.exists(yol): continue
        c = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=5)
        try:
            cols = {r[1] for r in c.execute("PRAGMA table_info(trades)")}
            ek = "COALESCE(ekosistem,'solana')" if "ekosistem" in cols else "'solana'"
            for eid, kopya, kapanan, kz in c.execute(f"""SELECT {ek}, SUM(side='buy'), SUM(side='sell'), SUM(CASE WHEN side='sell' THEN pnl ELSE 0 END)
                                                         FROM trades WHERE decision='KOPYALANDI' GROUP BY 1"""):
                s = say.setdefault(eid, dict(kopya=0, kapanan=0, kz=0.0, acik=0))
                s["kopya"] += kopya or 0; s["kapanan"] += kapanan or 0; s["kz"] += kz or 0.0
            pcols = {r[1] for r in c.execute("PRAGMA table_info(positions)")}
            pek = "COALESCE(ekosistem,'solana')" if "ekosistem" in pcols else "'solana'"
            for eid, n in c.execute(f"SELECT {pek}, COUNT(*) FROM positions GROUP BY 1"):
                say.setdefault(eid, dict(kopya=0, kapanan=0, kz=0.0, acik=0))["acik"] += n
        except sqlite3.OperationalError:
            pass
        finally:
            c.close()
    return [dict(e, cuzdan=len(cuzdanlar(e["id"], kok)), **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in say[e["id"]].items()})
            for e in EKOSISTEMLER]

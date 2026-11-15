"""Takipçi kaybı (N4: kaynak getirisi ile takipçinin uygulanabilir getirisini ayırma).

Her kopyalanan paper işlemin event_id'si "cüzdan:imza" biçimindedir. İmzadan kaynak cüzdanın
gerçek işlemini okuyup kaynağın birim fiyatını, bizim gerçek teklifle aldığımız/sattığımız
birim fiyatla karşılaştırırız (ikisi de USD/token):

  giriş kaybı  = bizim alış fiyatı / kaynak alış fiyatı − 1     (+ ise kaynaktan pahalıya aldık)
  çıkış kaybı  = 1 − bizim satış fiyatı / kaynak satış fiyatı   (+ ise kaynaktan ucuza sattık)
  kaynak getirisi = kaynak satış / kaynak alış − 1               (token hareketi)

SOL ile yapılan kaynak işlemleri tek bir güncel SOL/USD fiyatıyla çevrilir (yaklaşık)."""
from nexora.constants import USDC_MINT, WSOL_MINT
from nexora.swap_decoder import decode_swap


def source_price_usd(rec, sol_usd):
    """Çözülmüş swap kaydından token başına USD fiyatı; hesaplanamazsa None."""
    try:
        qty = abs(int(rec["token_delta_raw"])) / 10 ** int(rec["token_decimals"])
    except (KeyError, TypeError, ValueError):
        return None
    if qty <= 0: return None
    q = rec.get("quote_mint")
    if q == USDC_MINT and rec.get("quote_delta_raw") is not None:
        usd = abs(int(rec["quote_delta_raw"])) / 1e6
    elif q == WSOL_MINT and rec.get("quote_delta_raw") is not None:
        usd = abs(int(rec["quote_delta_raw"])) / 1e9 * sol_usd
    elif rec.get("sol_delta_lamports") is not None:
        usd = abs(int(rec["sol_delta_lamports"])) / 1e9 * sol_usd
    else:
        return None
    return usd / qty if usd > 0 else None


def round_trips(trades):
    """Kopyalanan alım ve satımları cüzdan+token bazında eşler. Açık pozisyonlar sat=None."""
    out, open_buy = [], {}
    for t in sorted(trades, key=lambda r: (r["ts"] or 0, r.get("id") or 0)):
        if t["decision"] != "KOPYALANDI": continue
        key = (t["wallet"], t["token"])
        if t["side"] == "buy":
            open_buy[key] = t
        elif t["side"] == "sell" and key in open_buy:
            out.append(dict(alis=open_buy.pop(key), satis=t))
    out += [dict(alis=b, satis=None) for b in open_buy.values()]
    return out


def analyze(trades, fetch_tx, sol_usd):
    """trades: paper 'trades' satırları. fetch_tx(imza) -> işlem sözlüğü ya da None."""
    cache = {}

    def src(trade):
        ev = trade.get("event_id") or ""
        if ":" not in ev: return None
        wallet, sig = ev.split(":", 1)
        if sig not in cache:
            try:
                tx = fetch_tx(sig)
                rec = decode_swap(tx, wallet) if isinstance(tx, dict) else None
            except Exception:
                rec = None
            cache[sig] = rec if rec and rec.get("event_type") in ("BUY", "SELL") else None
        rec = cache[sig]
        return source_price_usd(rec, sol_usd) if rec else None

    rows = []
    for rt in round_trips(trades):
        b, s = rt["alis"], rt["satis"]
        src_b = src(b)
        our_b = b.get("price") or None
        row = dict(cuzdan=b["wallet"], token=b["token"], alis_ts=b["ts"], durum="acik" if s is None else "kapandi",
                   kaynak_alis=src_b, bizim_alis=our_b,
                   giris_kaybi=(our_b / src_b - 1) if src_b and our_b else None,
                   kaynak_satis=None, bizim_satis=None, cikis_kaybi=None, kaynak_getiri=None,
                   bizim_kz=None, bizim_getiri=None, tutma_sn=None)
        if s is not None:
            src_s = src(s)
            our_s = s.get("price") or None
            cost = (b.get("qty") or 0) * (b.get("price") or 0)
            row.update(kaynak_satis=src_s, bizim_satis=our_s,
                       cikis_kaybi=(1 - our_s / src_s) if src_s and our_s else None,
                       kaynak_getiri=(src_s / src_b - 1) if src_s and src_b else None,
                       bizim_kz=s.get("pnl"), bizim_getiri=(s["pnl"] / cost) if cost and s.get("pnl") is not None else None,
                       tutma_sn=(s["ts"] - b["ts"]) if s.get("ts") and b.get("ts") else None)
        rows.append(row)

    def avg(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    wallets = {}
    for r in rows:
        w = wallets.setdefault(r["cuzdan"], dict(cuzdan=r["cuzdan"], islem=0, kapanan=0, _g=[], _c=[], _k=[], _b=[]))
        w["islem"] += 1
        w["_g"].append(r["giris_kaybi"])
        if r["durum"] == "kapandi":
            w["kapanan"] += 1; w["_c"].append(r["cikis_kaybi"]); w["_k"].append(r["kaynak_getiri"]); w["_b"].append(r["bizim_getiri"])
    ozet = []
    for w in wallets.values():
        g, c, k, b = avg(w.pop("_g")), avg(w.pop("_c")), avg(w.pop("_k")), avg(w.pop("_b"))
        w.update(giris_kaybi_ort=g, cikis_kaybi_ort=c, kaynak_getiri_ort=k, bizim_getiri_ort=b)
        ozet.append(w)
    return dict(sol_usd=sol_usd, islemler=rows, cuzdanlar=ozet)


def teshis(r):
    """Tek bir kapanan tur için kısa Türkçe açıklama: kayıp nereden geldi?"""
    if r["durum"] != "kapandi": return "açık pozisyon"
    parts = []
    if r["kaynak_getiri"] is not None: parts.append(f"token hareketi (kaynak) %{100 * r['kaynak_getiri']:+.1f}")
    if r["giris_kaybi"] is not None: parts.append(f"giriş kaybı %{100 * r['giris_kaybi']:+.1f}")
    if r["cikis_kaybi"] is not None: parts.append(f"çıkış kaybı %{100 * r['cikis_kaybi']:+.1f}")
    return ", ".join(parts) or "kaynak işlemi okunamadı"

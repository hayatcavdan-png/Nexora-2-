"""Cüzdan kârlılık analizi (N4, ilk sürüm). Saf hesaplama: ağ, veritabanı, emir yok.

İşlemler -> swap çözücü -> FIFO eşleştirme -> satış başına gerçekleşmiş K/Z.
SOL ve WSOL ile yapılan işlemler aynı kuyrukta eşleşir (ikisi de SOL).
USD karşılığı tek bir SOL fiyatıyla hesaplanır; bu bir yaklaşıklıktır.

Sınırlar (rapora yansır):
- Yalnızca incelenen pencere (son N işlem) görülür; pencereden önce alınıp
  pencerede satılan token'lar 'eşleşmeyen satış' olur ve K/Z'ye katılmaz.
- Açık pozisyonlar değerlenmez (gerçekleşmemiş K/Z yok).
- Kaynak cüzdanın getirisi, takipçinin elde edeceği getiri değildir: takipçi
  gecikmeli girer ve al-sat kaybı öder. Eşikler bu yüzden sıkı tutulur."""
from collections import Counter, defaultdict
from decimal import Decimal
from statistics import median

from nexora.constants import WSOL_MINT
from nexora.native_sol_fifo_adapter import NATIVE_SOL
from nexora.wallet_fifo_adapter import behavior_to_fifo_events
from nexora.fifo_matcher import match_fifo
from nexora.wallet_pnl import _decode_with_meta
from nexora.swap_decoder import decode_swap

THRESHOLDS = dict(
    min_closed=5,          # en az 5 kapanmış satış
    min_hold_s=60,         # medyan elde tutma < 60 sn: bizim gecikmemizle takip edilemez
    max_unmatched=0.5,     # satışların yarısından fazlası eşleşmiyorsa geçmiş eksik
    min_win_rate=0.40,
    min_profit_factor=1.3,
    min_mean_return=0.05,  # işlem başına ortalama %5: takipçinin al-sat kaybını karşılamalı
    max_top_token_share=0.8,  # kazancın %80'i tek token'dan geliyorsa şans olabilir
)

def _normalize(event):
    """WSOL ile yerel SOL'u aynı kuyrukta eşleştirmek için tek kimliğe indirger."""
    e = dict(event)
    if e.get("quote_mint") == WSOL_MINT:
        e["quote_mint"] = NATIVE_SOL
    if e.get("quote_mint") == NATIVE_SOL and e.get("fee_mint") == WSOL_MINT:
        e["fee_mint"] = NATIVE_SOL
    return e

def analyze(transactions, wallet, sol_usd):
    if not isinstance(sol_usd, (int, float)) or sol_usd <= 0:
        raise ValueError("SOL fiyatı geçersiz")
    records, skipped = [], Counter()
    for tx in transactions:
        if not isinstance(tx, dict): continue
        try:
            raw = decode_swap(tx, wallet)
        except (TypeError, ValueError):
            skipped["çözülemedi"] += 1; continue
        if raw.get("event_type") not in ("BUY", "SELL"):
            skipped[(raw.get("evidence") or ["?"])[0]] += 1; continue
        r = _decode_with_meta(tx, wallet)
        if r: records.append(r)
    conv = behavior_to_fifo_events({"wallet": wallet, "classifications": records})
    events = [_normalize(e) for e in conv["events"]]
    res = match_fifo(events, verified_only=False)

    ts = {e["signature"]: e["timestamp_ms"] for e in events}
    to_usd = lambda amount, quote: float(Decimal(amount)) * (sol_usd if quote == NATIVE_SOL else 1.0)

    sells = defaultdict(lambda: dict(pnl=0.0, cost=0.0, holds=[], token=None))
    for m in res["matches"]:
        s = sells[m["sell_signature"]]
        q = m["quote_mint"]
        s["pnl"] += to_usd(m["realized_pnl_quote"], q)
        s["cost"] += to_usd(Decimal(m["buy_cost_quote"]) + Decimal(m["buy_fee_quote"]), q)
        s["token"] = m["token_mint"]
        if m["buy_signature"] in ts and m["sell_signature"] in ts:
            s["holds"].append((ts[m["sell_signature"]] - ts[m["buy_signature"]]) / 1000)
    closed = list(sells.values())

    buys = [e for e in events if e["side"] == "BUY"]
    n_sells = sum(1 for e in events if e["side"] == "SELL")
    gains = sum(c["pnl"] for c in closed if c["pnl"] > 0)
    losses = -sum(c["pnl"] for c in closed if c["pnl"] < 0)
    realized = sum(c["pnl"] for c in closed)
    returns = [c["pnl"] / c["cost"] for c in closed if c["cost"] > 0]
    holds = [median(c["holds"]) for c in closed if c["holds"]]
    per_token = defaultdict(float)
    for c in closed: per_token[c["token"]] += c["pnl"]
    top_share = (max(per_token.values()) / gains) if gains > 0 and per_token else 0.0
    times = [r["timestamp_ms"] for r in records]
    buy_usd = [to_usd(Decimal(e["quote_amount_raw"]) / 10 ** e["quote_decimals"], e["quote_mint"]) for e in buys]

    return dict(
        wallet=wallet,
        islem=len(transactions), swap=len(records), alis=len(buys), satis=n_sells,
        token_sayisi=len({r["token_mint"] for r in records}),
        kapanan=len(closed), eslesmeyen_satis=len(res["unmatched_sells"]), acik_pozisyon=len(res["open_positions"]),
        gerceklesen_usd=round(realized, 2),
        kazanma_orani=round(sum(1 for c in closed if c["pnl"] > 0) / len(closed), 3) if closed else 0.0,
        kar_faktoru=round(gains / losses, 2) if losses > 0 else (99.0 if gains > 0 else 0.0),
        ort_getiri=round(sum(returns) / len(returns), 4) if returns else 0.0,
        medyan_tutma_sn=round(median(holds)) if holds else None,
        en_buyuk_token_payi=round(top_share, 3),
        ort_alis_usd=round(sum(buy_usd) / len(buy_usd), 2) if buy_usd else 0.0,
        pencere_gun=round((max(times) - min(times)) / 86_400_000, 2) if len(times) > 1 else 0.0,
        hesap_ac_kapa=skipped.get("token_account_created_or_closed", 0),   # çözücünün güvenlik gereği atladığı
    )

def verdict(m, t=THRESHOLDS):
    """(karar, gerekçeler). Karar: kopyalanabilir / zayıf / zararda / çok hızlı / eksik veri / yetersiz veri / swap yok."""
    if m["swap"] == 0: return "swap yok", ["incelenen işlemlerde swap bulunamadı"]
    if m["kapanan"] < t["min_closed"]:
        return "yetersiz veri", [f"yalnızca {m['kapanan']} kapanmış satış (en az {t['min_closed']})"]
    if m["satis"] and m["eslesmeyen_satis"] / m["satis"] > t["max_unmatched"]:
        return "eksik veri", [f"satışların %{100 * m['eslesmeyen_satis'] / m['satis']:.0f}'inin alışı pencerede yok"]
    if m["medyan_tutma_sn"] is not None and m["medyan_tutma_sn"] < t["min_hold_s"]:
        return "çok hızlı", [f"medyan elde tutma {m['medyan_tutma_sn']} sn: gecikmeyle takip edilemez"]
    if m["gerceklesen_usd"] <= 0: return "zararda", [f"gerçekleşen K/Z {m['gerceklesen_usd']} USD"]
    reasons = []
    if m["kazanma_orani"] < t["min_win_rate"]: reasons.append(f"kazanma oranı %{100 * m['kazanma_orani']:.0f}")
    if m["kar_faktoru"] < t["min_profit_factor"]: reasons.append(f"kâr faktörü {m['kar_faktoru']}")
    if m["ort_getiri"] < t["min_mean_return"]: reasons.append(f"işlem başı ortalama getiri %{100 * m['ort_getiri']:.1f}")
    if m["en_buyuk_token_payi"] > t["max_top_token_share"]:
        reasons.append(f"kazancın %{100 * m['en_buyuk_token_payi']:.0f}'i tek token'dan")
    return ("zayıf", reasons) if reasons else ("kopyalanabilir", ["tüm eşikler geçti"])

def score(m):
    """Kopyalanabilirler arasında sıralama: ortalama getiri x örnek büyüklüğü (aşırı küçük örnekleri cezalandırır)."""
    return m["ort_getiri"] * min(1.0, m["kapanan"] / 20) * min(m["kar_faktoru"], 5)

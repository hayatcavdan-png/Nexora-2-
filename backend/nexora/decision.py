"""Kopyalama karar motoru (N7, ilk sürüm). Paper trading için gerçek Jupiter teklifleriyle doldurma.
Sıra: kurallar (ağsız) -> token güvenliği -> alış teklifi -> geri satış teklifi -> kayıt.
Geçmiş/ideal fiyat kullanılmaz; doldurma, sinyal anındaki gerçek teklife göre yapılır."""
from nexora.constants import USDC_MINT
from nexora.core import CFG
from nexora.market import QuoteError

USDC_DECIMALS = 6

class Decider:
    def __init__(self, paper, quoter, safety):
        self.paper, self.quoter, self.safety = paper, quoter, safety

    def decide(self, event_id, wallet, token, side, signal_age_s):
        p = self.paper
        if p.seen(event_id): return dict(decision="ATLANDI", reason="tekrarlanan olay")
        reason, size = p.precheck(side, token, signal_age_s)
        if reason: return p.reject(event_id, wallet, token, side, reason)
        return self._buy(event_id, wallet, token, size) if side == "buy" else self._sell(event_id, wallet, token)

    def _buy(self, event_id, wallet, token, size):
        p = self.paper
        s = self.safety.check(token)
        if s["verdict"] != "UYGUN":
            return p.reject(event_id, wallet, token, "buy", f"token {s['verdict']}: {'; '.join(s['reasons'])}")
        amount = int(round(size * 10 ** USDC_DECIMALS))
        try:
            q = self.quoter.quote(USDC_MINT, token, amount)
        except QuoteError as e:
            return p.reject(event_id, wallet, token, "buy", f"alış teklifi yok: {e}")
        if q["price_impact_pct"] > CFG["max_price_impact_pct"]:
            return p.reject(event_id, wallet, token, "buy", f"fiyat etkisi yüksek (%{q['price_impact_pct']:.2f})")
        try:
            back = self.quoter.quote(token, USDC_MINT, q["out_amount"])
        except QuoteError as e:
            return p.reject(event_id, wallet, token, "buy", f"geri satış teklifi yok, satılamayabilir: {e}")
        rt = (1 - back["out_amount"] / amount) * 100
        if rt > CFG["max_roundtrip_loss_pct"]:
            return p.reject(event_id, wallet, token, "buy", f"al-sat kaybı yüksek (%{rt:.1f})")
        return p.record_buy(event_id, wallet, token, size, q["out_amount"], s["decimals"],
                            note=f"etki %{q['price_impact_pct']:.2f}, al-sat kaybı %{rt:.1f}")

    def _sell(self, event_id, wallet, token):
        p = self.paper
        pos = p.position(token)
        try:
            q = self.quoter.quote(token, USDC_MINT, int(pos["qty_raw"]))
        except QuoteError as e:
            return p.reject(event_id, wallet, token, "sell", f"satış teklifi yok, pozisyon açık kaldı: {e}")
        proceeds = q["out_amount"] / 10 ** USDC_DECIMALS
        return p.record_sell(event_id, wallet, token, proceeds, note=f"etki %{q['price_impact_pct']:.2f}")

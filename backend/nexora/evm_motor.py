"""EVM ekosistemi (BNB Chain / Base) PAPER motoru: takip edilen cüzdanların swap'larını bloklardan yakalar ve platform 1 ile
AYNI kurallarla (pozisyon başına %5, günlük %3 zarar, en fazla 8 pozisyon, bayat sinyal reddi) ayrı bir sanal portföyde kopyalar.

Alım öncesi sıra: güvenlik (GoPlus: honeypot, vergi, satılamama) -> alış teklifi (KyberSwap, USD stablecoin ile)
-> hemen geri satış teklifi (al-sat kaybı > %6 ise alınmaz) -> paper alım. Satım: kaynak cüzdan satınca güncel teklifle.
Fiyat teklifi zaten kaymayı içerdiği için paper motoruna ek kayma verilmez. Gerçek emir YOK."""
import json, time

from nexora.evm import EvmHatasi, ZINCIRLER, coz_tam


class EvmKarar:
    def __init__(self, paper, rpc, teklif, guvenlik, zincir):
        self.p, self.rpc, self.t, self.g, self.z = paper, rpc, teklif, guvenlik, ZINCIRLER[zincir]

    def _red(self, ev, w, token, yon, neden):
        return self.p.reject(ev, w, token, yon, neden)

    def karar(self, ev, w, token, yon, yas):
        p = self.p
        if p.seen(ev): return dict(decision="ATLANDI", reason="tekrarlanan olay")
        if yas > p.limit("max_signal_age_s"): return self._red(ev, w, token, yon, "sinyal bayat")
        if yon == "sell":
            poz = p.position(token)
            if not poz: return self._red(ev, w, token, yon, "sahip olunmayan pozisyon satılamaz")
            try:
                dec = self.rpc.ondalik(token)
                q = self.t.teklif(token, self.z["usd"], int(poz["qty"] * 10 ** dec))
            except EvmHatasi as e:
                return self._red(ev, w, token, yon, f"satış teklifi yok, pozisyon açık kaldı: {e}")
            usd = q["cikis_raw"] / 10 ** self.z["usd_ondalik"]
            return p.handle_signal(ev, w, token, "sell", usd / poz["qty"], 10 ** 9, yas)
        g = self.g.kontrol(token)
        if not g["uygun"]: return self._red(ev, w, token, yon, "token güvenliği: " + "; ".join(g["gerekceler"]))
        boyut = round(p.equity() * p.poz_orani(), 6)
        try:
            dec = self.rpc.ondalik(token)
            al = self.t.teklif(self.z["usd"], token, int(boyut * 10 ** self.z["usd_ondalik"]))
            geri = self.t.teklif(token, self.z["usd"], al["cikis_raw"])
        except EvmHatasi as e:
            return self._red(ev, w, token, yon, f"teklif yok: {e}")
        rt = (1 - geri["cikis_raw"] / 10 ** self.z["usd_ondalik"] / boyut) * 100
        if rt > p.limit("max_roundtrip_loss_pct"): return self._red(ev, w, token, yon, f"al-sat kaybı yüksek (%{rt:.1f})")
        if rt < -2.0: return self._red(ev, w, token, yon, f"teklif tutarsız (al-sat %{rt:.1f})")
        adet = al["cikis_raw"] / 10 ** dec
        return p.handle_signal(ev, w, token, "buy", boyut / adet, max(g["likidite_usd"], 0.0), yas)

    def degerle(self):
        ok = 0
        for poz in self.p.portfolio()["positions"]:
            try:
                dec = self.rpc.ondalik(poz["token"])
                q = self.t.teklif(poz["token"], self.z["usd"], int(poz["qty"] * 10 ** dec))
                self.p.mark_price(poz["token"], q["cikis_raw"] / 10 ** self.z["usd_ondalik"] / poz["qty"]); ok += 1
            except (EvmHatasi, ZeroDivisionError):
                pass
        return ok


class EvmTakip:
    """Blok aralığını tarar, cüzdan işlemlerini çözer, kararı verir. Kaldığı bloğu paper veritabanında saklar."""
    MAKS_ARALIK = 500

    def __init__(self, rpc, karar, cuzdanlar, zincir, clock=time.time):
        self.rpc, self.k, self.w, self.zincir, self.clock = rpc, karar, [c.lower() for c in cuzdanlar], zincir, clock
        self.gorulen = set()

    def tur(self):
        if not self.w: return []
        son = self.rpc.blok()
        kayit = self.k.p._get("evm_son_blok")
        bas = max(int(kayit) + 1 if kayit else son, son - self.MAKS_ARALIK)      # ilk çalıştırmada geçmişe dönülmez
        olay = []
        if bas > son: return olay
        for karma, (blok, w) in sorted(self.rpc.cuzdan_islemleri(self.w, bas, son).items(), key=lambda x: x[1][0]):
            if (karma, w) in self.gorulen: continue
            self.gorulen.add((karma, w))
            try:
                tx = self.rpc.call("eth_getTransactionByHash", [karma]) or {}
                mk = self.rpc.call("eth_getTransactionReceipt", [karma]) or {}
            except EvmHatasi:
                continue
            s = coz_tam(self.rpc, tx, mk, w, self.zincir, blok)
            if not s: continue
            yas = max(0.0, self.clock() - self.rpc.blok_zamani(blok))
            r = self.k.karar(f"{self.zincir}:{w}:{karma}", w, s["token"], s["yon"], yas)
            olay.append(dict(s, cuzdan=w, karma=karma, yas=round(yas, 1), karar=r.get("decision"), neden=r.get("reason")))
        self.k.p._set("evm_son_blok", son); self.k.p.db.commit()
        if len(self.gorulen) > 5000: self.gorulen = set(list(self.gorulen)[-2000:])
        return olay

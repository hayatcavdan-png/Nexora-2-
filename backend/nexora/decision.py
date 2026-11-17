"""Kopyalama karar motoru (N7, ilk sürüm). Paper trading için gerçek Jupiter teklifleriyle doldurma.
Sıra: kurallar (ağsız) -> token güvenliği -> alış teklifi -> geri satış teklifi -> kayıt.
Geçmiş/ideal fiyat kullanılmaz; doldurma, sinyal anındaki gerçek teklife göre yapılır."""
from nexora.constants import USDC_MINT
from nexora.core import CFG
from nexora.market import QuoteError
from nexora import durum as D

USDC_DECIMALS = 6

def kaynak_bakiyesi(client, wallet, mint):
    """Kaynak cüzdanın bu token'daki toplam ham bakiyesi (tüm token hesapları; salt okunur RPC). Bilinmiyorsa None."""
    try:
        r = client.call("getTokenAccountsByOwner", [wallet, {"mint": mint}, {"encoding": "jsonParsed", "commitment": "confirmed"}])
        return sum(int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) for a in (r or {}).get("value") or [])
    except Exception:
        return None


def _q(q):
    """Denetim izi için teklifin özeti."""
    return dict(giris=q.get("in_amount"), cikis=q.get("out_amount"), etki=q.get("price_impact_pct"),
                router=q.get("router"), giris_usd=q.get("in_usd"), cikis_usd=q.get("out_usd"))


def puan_agirligi(puanlar, wallet):
    """Puan ağırlıklı yöntem: en iyi skora göre 0.2-1.0 arası çarpan (üst sınır gerçek %5 kuralı). Skoru bilinmeyen: 0.5."""
    skor = puanlar.get(wallet)
    en_iyi = max([v for v in puanlar.values() if v and v > 0], default=0)
    if skor is None or skor <= 0 or en_iyi <= 0: return skor, 0.5
    return skor, round(max(0.2, min(1.0, skor / en_iyi)), 4)


class Decider:
    def __init__(self, paper, quoter, safety, bilgi=None, yurutme=None, puanlar=None, izle=None, kapi=None):
        self.paper, self.quoter, self.safety = paper, quoter, safety
        self.kapi = kapi              # N20: model filtresi (yalnızca açıkça açıldıysa ve model varsa etkili)
        self._yas = None
        self.izle = set(izle or ())   # yalnızca izlenen cüzdanlar: sinyalleri etiketlenir, alımları kopyalanmaz (satış açık pozisyonu kapatır)
        self.puanlar = puanlar or {}  # N7: cüzdan -> analiz skoru (yalnızca büyüklük karşılaştırma ölçümü için)
        self.bilgi = bilgi            # isteğe bağlı token bilgisi toplayıcı (yalnızca ölçüm; kararı etkilemez)
        self.yurutme = yurutme        # isteğe bağlı yürütme gecikmesi ölçer (yalnızca ölçüm)

    # Yer/sınır kuralı yüzünden reddedilen alımlar gölgede ölçülür: "sınır olmasaydı ne kazanırdık?" (N8/N10 kararı için).
    KURAL_GOLGE = ("maks. eşzamanlı pozisyon", "bu cüzdan için pozisyon sınırı dolu", "bu token'a bugünkü giriş sınırı dolu",
                   "toplam risk sınırı (%40) dolu")
    KURAL_GOLGE_SAAT = 8              # saatte en fazla bu kadar ölçüm: Jupiter/Helius kotası gerçek sinyallere kalsın

    def _kural_golgesi(self, event_id, wallet, token, reason, now=None):
        """Reddedilen alımı, kopyalansaydı geçeceği AYNI süzgeçlerden geçirip gölge pozisyon açar. Paper defterine dokunmaz."""
        import time as _t
        now = now if now is not None else _t.time()
        gecmis = self.__dict__.setdefault("_kg", [])
        gecmis[:] = [t for t in gecmis if now - t < 3600]
        if len(gecmis) >= self.KURAL_GOLGE_SAAT: return False
        gecmis.append(now)
        p = self.paper
        try:
            s = self.safety.check(token)
            if s["verdict"] != "UYGUN": return False
            size = round(p.equity() * p.poz_orani(wallet), 6)
            amount = int(round(size * 10 ** USDC_DECIMALS))
            q = self.quoter.quote(USDC_MINT, token, amount)
            if q["price_impact_pct"] is not None and q["price_impact_pct"] > p.limit("max_price_impact_pct"): return False
            back = self.quoter.quote(token, USDC_MINT, q["out_amount"])
            rt = (1 - back["out_amount"] / amount) * 100
            if rt < CFG["min_roundtrip_loss_pct"] or rt > p.limit("max_roundtrip_loss_pct"): return False
            if p.shadow_open(event_id, wallet, token, size, q["out_amount"], s["decimals"], rt, q["price_impact_pct"], "kural: " + reason):
                self._olc(event_id, token); return True
        except Exception:
            pass                          # ölçüm hatası kararı etkilemez
        return False

    def _olc(self, event_id, token):
        if self.bilgi is not None: self.bilgi.enqueue(event_id, token)

    KAYNAK_YAS_SN = 600           # pozisyon en az bu kadar açıksa denetlenir (kaynağın alışı zincirde yerleşsin)

    def kaynak_denetimi(self, bakiye, now=None):
        """Kaynak cüzdan token'ı satış sinyali vermeden elden çıkardıysa (başka adrese aktarım ya da çözülemeyen bir satış),
        pozisyon kendi kendine hiç kapanmaz. Böyle pozisyonları gerçek satış teklifiyle kapatır.
        bakiye(wallet, token) -> ham miktar; None (bilinmiyor) ya da sıfırdan büyükse pozisyona dokunulmaz."""
        import time as _t
        now = now if now is not None else _t.time()
        out = []
        for pos in self.paper.portfolio()["positions"]:
            w, t = pos.get("wallet"), pos["token"]
            if not w or w == "MANUEL" or not pos.get("qty_raw"): continue
            if pos.get("opened_ts") and now - pos["opened_ts"] < self.KAYNAK_YAS_SN: continue
            b = bakiye(w, t)
            if b is None or b > 0: continue
            r = self.decide(f"aktarim:{t}:{int(now)}", w, t, "sell", 0.0, neden="kaynakta token kalmadı (satış sinyali gelmedi)")
            out.append((t, r.get("decision"), r.get("reason")))
        return out

    def decide(self, event_id, wallet, token, side, signal_age_s, boyut_usd=None, neden=None):
        p = self.paper
        if p.seen(event_id): return dict(decision="ATLANDI", reason="tekrarlanan olay")
        iz = []                       # N1: her adımın girdisi ve sonucu (değiştirilemez kayıt)
        self._yas = signal_age_s
        r = None
        try:
            if side == "sell": self._close_shadows(event_id, wallet, token)
            limitler = {k: p.limit(k) for k in ("max_pos_pct", "daily_loss_pct", "max_positions", "max_positions_per_wallet", "max_token_entries_per_day",
                                                "max_signal_age_s", "max_price_impact_pct", "max_roundtrip_loss_pct")}
            reason, size = p.precheck(side, token, signal_age_s, wallet)
            if not reason and side == "buy" and wallet in self.izle: reason = "cüzdan yalnızca izleniyor"
            if boyut_usd is not None and size: size = round(min(size, max(0.0, float(boyut_usd))), 6)   # elle işlem: sınırı aşamaz
            if boyut_usd is not None and side == "buy" and not reason and size < 0.5: reason = "tutar çok küçük (en az 0.5 USDC)"
            iz.append(dict(adim="kurallar", sonuc=reason or "geçti", boyut_usd=size, limitler=limitler,
                           nakit=round(p.cash(), 6)))
            if reason:
                r = p.reject(event_id, wallet, token, side, reason)
                if side == "buy" and reason in self.KURAL_GOLGE and boyut_usd is None:
                    iz.append(dict(adim="kural_golgesi", sonuc="açıldı" if self._kural_golgesi(event_id, wallet, token, reason) else "açılmadı"))
            else:
                r = self._buy(event_id, wallet, token, size, iz) if side == "buy" else self._sell(event_id, wallet, token, iz, neden)
            return r
        except Exception as e:
            iz.append(dict(adim="hata", sonuc=f"{type(e).__name__}: {str(e)[:120]}"))
            raise
        finally:
            if r is not None and r.get("decision") != "ATLANDI":
                try:
                    p.karar_izi_yaz(event_id, wallet, token, side, signal_age_s, r.get("decision"), r.get("reason"), iz)
                except Exception:
                    pass                  # denetim izi yazılamazsa karar geri alınmaz

    def _buy(self, event_id, wallet, token, size, iz=None):
        iz = iz if iz is not None else []
        p = self.paper
        s = self.safety.check(token)
        iz.append(dict(adim="token_guvenligi", sonuc=s["verdict"], gerekceler=s.get("reasons", [])))
        if s["verdict"] != "UYGUN":
            return p.reject(event_id, wallet, token, "buy", f"token {s['verdict']}: {'; '.join(s['reasons'])}")
        amount = int(round(size * 10 ** USDC_DECIMALS))
        try:
            q = self.quoter.quote(USDC_MINT, token, amount)
        except QuoteError as e:
            iz.append(dict(adim="alis_teklifi", sonuc=f"yok: {e}"))
            return p.reject(event_id, wallet, token, "buy", f"alış teklifi yok: {e}")
        iz.append(dict(adim="alis_teklifi", sonuc="alındı", **_q(q)))
        if q["price_impact_pct"] is not None and q["price_impact_pct"] > p.limit("max_price_impact_pct"):
            why = f"fiyat etkisi yüksek (%{q['price_impact_pct']:.2f})"
            if p.shadow_open(event_id, wallet, token, size, q["out_amount"], s["decimals"], None, q["price_impact_pct"], why):
                self._olc(event_id, token)
            return p.reject(event_id, wallet, token, "buy", why)
        try:
            back = self.quoter.quote(token, USDC_MINT, q["out_amount"])
        except QuoteError as e:
            iz.append(dict(adim="geri_satis_teklifi", sonuc=f"yok: {e}"))
            return p.reject(event_id, wallet, token, "buy", f"geri satış teklifi yok, satılamayabilir: {e}")
        rt = (1 - back["out_amount"] / amount) * 100
        iz.append(dict(adim="geri_satis_teklifi", sonuc="alındı", al_sat_kaybi_pct=round(rt, 4), **_q(back)))
        if rt < CFG["min_roundtrip_loss_pct"]:
            # Hemen geri satınca daha fazla USDC: alış ve satış teklifleri birbiriyle çelişiyor (bayat/tek taraflı havuz).
            # Gerçekte bu fark yakalanamaz; paper defteri şişirmemek için alım yapılmaz, gölgede ölçülür.
            why = f"teklif tutarsız (al-sat %{rt:.1f})"
            if p.shadow_open(event_id, wallet, token, size, q["out_amount"], s["decimals"], rt, q["price_impact_pct"], why):
                self._olc(event_id, token)
            return p.reject(event_id, wallet, token, "buy", why)
        if rt > p.limit("max_roundtrip_loss_pct"):
            why = f"al-sat kaybı yüksek (%{rt:.1f})"
            if p.shadow_open(event_id, wallet, token, size, q["out_amount"], s["decimals"], rt, q["price_impact_pct"], why):
                self._olc(event_id, token)
            return p.reject(event_id, wallet, token, "buy", why)
        if self.kapi is not None:
            try:
                k = self.kapi.izin(wallet, token, self._yas, q["price_impact_pct"], round(rt, 4))
            except Exception as e:                       # filtre arızası alımı engellemez; izde görünür
                k = None; iz.append(dict(adim="model", sonuc=f"hata: {type(e).__name__}"))
            if k is not None:
                iz.append(dict(adim="model", sonuc="geçti" if k["secerdi"] else "eledi", olasilik=k["olasilik"],
                               esik=k["esik"], surum=k["surum"]))
                if not k["secerdi"]:
                    why = f"model olasılığı düşük (%{100 * k['olasilik']:.0f} < %{100 * k['esik']:.0f})"
                    if p.shadow_open(event_id, wallet, token, size, q["out_amount"], s["decimals"], rt, q["price_impact_pct"], why):
                        self._olc(event_id, token)
                    return p.reject(event_id, wallet, token, "buy", why)
        etki = "etki bilinmiyor" if q["price_impact_pct"] is None else f"etki %{q['price_impact_pct']:.2f}"
        r = p.record_buy(event_id, wallet, token, size, q["out_amount"], s["decimals"],
                         note=f"{etki}, al-sat kaybı %{rt:.1f}")
        if r.get("decision") == "KOPYALANDI":
            self._olc(event_id, token)
            skor, w = puan_agirligi(self.puanlar, wallet)
            p.boyut_kaydet(event_id, wallet, size, w, skor)
            if self.yurutme is not None: self.yurutme.enqueue(event_id, "buy", token, USDC_MINT, token, amount, q["out_amount"])
        return r

    def _close_shadows(self, event_id, wallet, token):
        """Kaynak cüzdan sattığında, o cüzdan+token için açık gölge pozisyonları gerçek satış teklifiyle kapatır."""
        for sh in self.paper.open_shadows(wallet, token):
            try:
                q = self.quoter.quote(token, USDC_MINT, int(sh["qty_raw"]))
            except QuoteError as e:
                self.paper.shadow_close(sh["id"], 0.0, event_id, status="satilamadi", note=str(e)[:80])
                continue
            self.paper.shadow_close(sh["id"], q["out_amount"] / 10 ** USDC_DECIMALS, event_id)

    def _sell(self, event_id, wallet, token, iz=None, neden=None):
        iz = iz if iz is not None else []
        p = self.paper
        pos = p.position(token)
        p.durum_degistir(token, D.KAPANIYOR, neden or "kaynak sattı")
        if neden: iz.append(dict(adim="neden", sonuc=neden))
        iz.append(dict(adim="durum", sonuc=D.KAPANIYOR))
        try:
            q = self.quoter.quote(token, USDC_MINT, int(pos["qty_raw"]))
        except QuoteError as e:
            iz.append(dict(adim="satis_teklifi", sonuc=f"yok: {e}"))
            p.durum_degistir(token, D.TAKILDI, f"satış teklifi yok: {str(e)[:60]}")
            iz.append(dict(adim="durum", sonuc=D.TAKILDI))
            return p.reject(event_id, wallet, token, "sell", f"satış teklifi yok, pozisyon açık kaldı: {e}")
        iz.append(dict(adim="satis_teklifi", sonuc="alındı", maliyet_usd=pos["cost"], **_q(q)))
        proceeds = q["out_amount"] / 10 ** USDC_DECIMALS
        etki = "etki bilinmiyor" if q["price_impact_pct"] is None else f"etki %{q['price_impact_pct']:.2f}"
        r = p.record_sell(event_id, wallet, token, proceeds, note=etki + (f"; {neden}" if neden else ""))
        if r.get("decision") == "KOPYALANDI" and self.yurutme is not None:
            self.yurutme.enqueue(event_id, "sell", token, token, USDC_MINT, int(pos["qty_raw"]), q["out_amount"])
        return r

    def mark_to_market(self):
        """Açık pozisyonları gerçek satış teklifiyle değerler. Teklif alınamazsa eski fiyat kalır."""
        done, failed = 0, 0
        for pos in self.paper.portfolio()["positions"]:
            if not pos.get("qty_raw") or not pos.get("qty"): continue
            try:
                q = self.quoter.quote(pos["token"], USDC_MINT, int(pos["qty_raw"]))
            except QuoteError:
                failed += 1; self.paper.teklif_sonucu(pos["token"], False); continue
            self.paper.teklif_sonucu(pos["token"], True)
            self.paper.mark_price(pos["token"], q["out_amount"] / 10 ** USDC_DECIMALS / pos["qty"])
            done += 1
        return done, failed

"""Kopyalama karar motoru (N7, ilk sürüm). Paper trading için gerçek Jupiter teklifleriyle doldurma.
Sıra: kurallar (ağsız) -> token güvenliği -> alış teklifi -> geri satış teklifi -> kayıt.
Geçmiş/ideal fiyat kullanılmaz; doldurma, sinyal anındaki gerçek teklife göre yapılır."""
import os
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


def satis_orani(tx, wallet, mint):
    """Kaynağın bu satışta elindeki token'ın ne kadarını sattığı (0-1), işlemin kendi öncesi/sonrası bakiyelerinden.
    Ek RPC yok. Bilinmiyorsa None."""
    try:
        meta = tx.get("meta") or {}
        def top(alan):
            return sum(int(b["uiTokenAmount"]["amount"]) for b in meta.get(alan) or []
                       if b.get("owner") == wallet and b.get("mint") == mint)
        once, sonra = top("preTokenBalances"), top("postTokenBalances")
        if once <= 0 or sonra > once: return None
        return round((once - sonra) / once, 6)
    except (KeyError, TypeError, ValueError, AttributeError):
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

    KISMI_ESIK = 0.95             # kaynak bundan azını sattıysa "kısmi satış" sayılır
    KISMI_SURE_SN = 86400         # ölçüm en geç 24 saatte kalan gerçek teklifle kapanır

    def _kismi_isle(self, event_id, wallet, token, oran):
        """Açık kısmi ölçümlerde, kaynağın yeni satışıyla orantılı payı gerçek teklifle 'satar'. Paper defterine dokunmaz."""
        for k in self.paper.kismi_acik(wallet, token):
            kalan = int(k["kalan_raw"])
            pay = kalan if (oran is None or oran >= self.KISMI_ESIK) else int(kalan * oran)
            try:
                usd = self.quoter.quote(token, USDC_MINT, pay)["out_amount"] / 10 ** USDC_DECIMALS if pay > 0 else 0.0
            except QuoteError as e:
                self.paper.kismi_guncelle(k["id"], 0, 0.0, status="satilamadi", note=str(e)[:80]); continue
            kalan -= pay
            self.paper.kismi_guncelle(k["id"], kalan, usd, status="open" if kalan > 0 else "closed")

    def kismi_zaman_asimi(self, now=None):
        """24 saati dolan kısmi ölçümleri kalanın gerçek teklifiyle kapatır."""
        import time as _t
        now = now if now is not None else _t.time()
        for k in self.paper.kismi_acik():
            if now - (k["acilis_ts"] or now) < self.KISMI_SURE_SN: continue
            kalan = int(k["kalan_raw"])
            try:
                usd = self.quoter.quote(k["token"], USDC_MINT, kalan)["out_amount"] / 10 ** USDC_DECIMALS if kalan > 0 else 0.0
                self.paper.kismi_guncelle(k["id"], 0, usd, status="zaman")
            except QuoteError as e:
                self.paper.kismi_guncelle(k["id"], 0, 0.0, status="satilamadi", note=str(e)[:80])

    # Güçlendirme (17.11.2026, kullanıcı onayı; deney masası [10b]: 2x en iyi, kâr +%17, düşüş azaldı): GUC_SN içinde
    # 2+ farklı cüzdanın aldığı token "teyitli". Tutuluyorsa bir kez ek parça; tutulmuyorsa GUC_KAT büyüklükle giriş.
    # Toplam açık maliyet her durumda %40'ı aşamaz. GUCLENDIRME_KAT=1 ile kapatılır.
    GUC_SN = 900
    GUC_KAT = float(os.getenv("GUCLENDIRME_KAT", "2"))
    GOLGE_TEYIT = os.getenv("GOLGE_TEYIT", "0") == "1"     # 1: gölge havuzun alımı da teyit sayılır (kullanıcı onayıyla açılır)

    def _teyit(self, wallet, token, now=None, golge=False):
        """Bu alımı da sayarak son GUC_SN içinde token'ı alan farklı cüzdan sayısı (bellekte; servis yeniden başlarsa sıfırlanır).
        Dönüş: (kopyalanan cüzdan sayısı, gölge/izlenen dahil toplam). Canlı güçlendirme yalnızca ilkini kullanır;
        ikincisi karar izine yazılır (gölge teyidi önce ölçülür, deney masası [10b])."""
        import time as _t
        now = now if now is not None else _t.time()
        kayit = self.__dict__.setdefault("_alimlar", {})
        d = kayit.setdefault(token, {}); d[wallet] = (now, golge)
        for w in [w for w, (t, _) in d.items() if now - t > self.GUC_SN]: del d[w]
        if len(kayit) > 2000:                                         # bellek sınırı: eski token'ları at
            for t in [t for t, x in kayit.items() if not x or max(v[0] for v in x.values()) < now - self.GUC_SN]: del kayit[t]
        return sum(1 for _, g in d.values() if not g), len(d)

    def decide(self, event_id, wallet, token, side, signal_age_s, boyut_usd=None, neden=None, kaynak_oran=None):
        p = self.paper
        if p.seen(event_id): return dict(decision="ATLANDI", reason="tekrarlanan olay")
        iz = []                       # N1: her adımın girdisi ve sonucu (değiştirilemez kayıt)
        self._yas = signal_age_s
        r = None
        try:
            if side == "sell":
                self._close_shadows(event_id, wallet, token)
                try: self._kismi_isle(event_id, wallet, token, kaynak_oran)
                except Exception: pass    # ölçüm hatası kararı etkilemez
            limitler = {k: p.limit(k) for k in ("max_pos_pct", "daily_loss_pct", "max_positions", "max_positions_per_wallet", "max_token_entries_per_day",
                                                "max_signal_age_s", "max_price_impact_pct", "max_roundtrip_loss_pct")}
            reason, size = p.precheck(side, token, signal_age_s, wallet)
            ek = False
            if side == "buy" and wallet in self.izle:                  # gölge/izlenen alım: yalnızca teyit sayacına yazılır
                self._teyit(wallet, token, golge=True)
            if side == "buy" and boyut_usd is None and wallet != "MANUEL" and wallet not in self.izle and self.GUC_KAT > 1:
                teyit, teyit_tum = self._teyit(wallet, token)
                if teyit_tum > teyit: iz.append(dict(adim="golge_teyit", teyit=teyit, gölge_dahil=teyit_tum, etkin=self.GOLGE_TEYIT))
                if self.GOLGE_TEYIT: teyit = teyit_tum
                if teyit >= 2 and reason == "bu token'da zaten pozisyon var":
                    reason, size = p.precheck(side, token, signal_age_s, wallet, ek=True); ek = not reason
                    iz.append(dict(adim="guclendirme", sonuc="ek parça" if ek else f"yok: {reason}", teyit=teyit))
                elif teyit >= 2 and not reason:
                    buyuk = round(size * self.GUC_KAT, 6)
                    if p.risk_uygun(buyuk) and buyuk + 0.01 + 1.0 <= p.cash(): size = buyuk
                    iz.append(dict(adim="guclendirme", sonuc=f"{self.GUC_KAT:g}x" if size == buyuk else "risk/nakit: 1x", teyit=teyit))
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
                r = self._buy(event_id, wallet, token, size, iz, ek=ek) if side == "buy" else self._sell(event_id, wallet, token, iz, neden, kaynak_oran)
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

    def _buy(self, event_id, wallet, token, size, iz=None, ek=False):
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
                         note=f"{etki}, al-sat kaybı %{rt:.1f}" + ("; güçlendirme (2+ cüzdan teyidi)" if ek else ""), ek=ek)
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

    def _sell(self, event_id, wallet, token, iz=None, neden=None, oran=None):
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
        r = p.record_sell(event_id, wallet, token, proceeds, note=etki + (f"; {neden}" if neden else "")
                          + (f"; kaynak %{100 * oran:.0f} sattı" if oran is not None else ""))
        if r.get("decision") == "KOPYALANDI" and oran is not None and oran < self.KISMI_ESIK and not neden:
            try:                                          # ölçüm: kaynak kadar satsaydık kalan pay
                p.kismi_ac(wallet, token, oran, int(int(pos["qty_raw"]) * (1 - oran)), round(proceeds * (1 - oran), 6))
            except Exception:
                pass
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

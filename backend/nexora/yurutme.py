"""Yürütme gecikmesi ölçümü (N9, yalnızca ölçüm). Gerçek işlemde emir, karardan birkaç saniye sonra zincire ulaşır.
Kopyalanan her alım/satımda aynı teklif GECIKME_SN sonra yeniden alınır; çıktı farkı 'gecikme kaybı' olarak kaydedilir.
Pozitif kayıp: geç kalınca daha az token/USDC alınırdı. Paper defteri değişmez. Kuyruk dolarsa ölçüm atlanır."""
import queue, threading, time

from nexora.market import QuoteError

GECIKME_SN = 3.0
DERINLIK_USD = (25, 100)   # N5: kopyalanan alımda bu tutarlarla da teklif alınır (likidite derinliği)
USDC_ONDALIK = 10 ** 6


class YurutmeOlcer:
    def __init__(self, quoter, paper, gecikme=GECIKME_SN, maxsize=50, clock=time.time, sleep=time.sleep):
        self.quoter, self.paper, self.gecikme = quoter, paper, gecikme
        self.clock, self.sleep = clock, sleep
        self.q = queue.Queue(maxsize=maxsize)

    def derinlik(self, event_id, token, girdi, cikti, miktar, ilk):
        """Alımda USDC tutarı büyüdükçe birim fiyat ne kadar kötüleşiyor? kayıp_N = 1 - (çıktı_N/N) / (çıktı/tutar)."""
        if not ilk or miktar < USDC_ONDALIK // 2 or not hasattr(self.paper, "derinlik_kaydet"): return None   # 0.5 USDC altı: ölçülmez
        birim = ilk / miktar; kayip = {}
        try:
            for usd in DERINLIK_USD:
                raw = usd * USDC_ONDALIK
                if raw <= miktar: continue
                q = self.quoter.quote(girdi, cikti, raw)
                kayip[usd] = round((1 - (q["out_amount"] / raw) / birim) * 100, 3)
            self.paper.derinlik_kaydet(event_id, token, round(miktar / USDC_ONDALIK, 4), kayip)
        except QuoteError as e:
            self.paper.derinlik_kaydet(event_id, token, round(miktar / USDC_ONDALIK, 4), kayip, hata=str(e)[:80])
        return kayip

    def enqueue(self, event_id, side, token, girdi, cikti, miktar, ilk_cikti):
        try:
            self.q.put_nowait((event_id, side, token, girdi, cikti, int(miktar), int(ilk_cikti), self.clock()))
        except queue.Full:
            pass

    def isle(self, item):
        event_id, side, token, girdi, cikti, miktar, ilk, t0 = item
        bekle = t0 + self.gecikme - self.clock()
        if bekle > 0: self.sleep(bekle)
        try:
            try:
                q = self.quoter.quote(girdi, cikti, miktar)
            except QuoteError as e:
                if "429" not in str(e) and "bağlantı" not in str(e): raise
                self.sleep(1.1)                                      # hız sınırı/bağlantı: bir kez daha dene
                q = self.quoter.quote(girdi, cikti, miktar)
            gecen = self.clock() - t0
            sonuc = self.paper.yurutme_kaydet(event_id, side, token, round(gecen, 2), ilk, q["out_amount"])
            if side == "buy": self.derinlik(event_id, token, girdi, cikti, miktar, ilk)
            return sonuc
        except QuoteError as e:
            self.paper.yurutme_kaydet(event_id, side, token, round(self.clock() - t0, 2), ilk, None, hata=str(e)[:80])
            return None

    def baslat(self):
        def run():
            while True:
                try:
                    self.isle(self.q.get())
                except Exception:
                    pass
        threading.Thread(target=run, daemon=True).start()
        return self

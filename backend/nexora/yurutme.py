"""Yürütme gecikmesi ölçümü (N9, yalnızca ölçüm). Gerçek işlemde emir, karardan birkaç saniye sonra zincire ulaşır.
Kopyalanan her alım/satımda aynı teklif GECIKME_SN sonra yeniden alınır; çıktı farkı 'gecikme kaybı' olarak kaydedilir.
Pozitif kayıp: geç kalınca daha az token/USDC alınırdı. Paper defteri değişmez. Kuyruk dolarsa ölçüm atlanır."""
import queue, threading, time

from nexora.market import QuoteError

GECIKME_SN = 3.0


class YurutmeOlcer:
    def __init__(self, quoter, paper, gecikme=GECIKME_SN, maxsize=50, clock=time.time, sleep=time.sleep):
        self.quoter, self.paper, self.gecikme = quoter, paper, gecikme
        self.clock, self.sleep = clock, sleep
        self.q = queue.Queue(maxsize=maxsize)

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
            q = self.quoter.quote(girdi, cikti, miktar)
            gecen = self.clock() - t0
            return self.paper.yurutme_kaydet(event_id, side, token, round(gecen, 2), ilk, q["out_amount"])
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

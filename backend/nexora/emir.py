"""N11 · Gerçek emir altyapısı, İMZASIZ kısım: işlem oluşturma, yapı denetimi ve zincirde simülasyon.

Bu modül emir GÖNDERMEZ: Jupiter /execute çağrısı ve RPC sendTransaction burada yoktur (N12, ayrıca açık onayla).
Akış:
  1) hazirla(): GET /swap/v2/order + taker -> imzalanmamış işlem (base64) ve requestId.
     JupiterZ (RFQ) dışlanır: piyasa yapıcı imzası gerektirir, simüle edilemez. İşlem sürümü 0 istenir.
  2) cozumle(): işlemin yapısı denetlenir: tek imzacı, ücret ödeyen = bizim cüzdan, imza alanı boş.
  3) simule(): Helius simulateTransaction (sigVerify=false, replaceRecentBlockhash=true). Zincire bir şey yazılmaz.
Cüzdanda bakiye yoksa Jupiter işlemi oluşturmaz (errorCode 1/2): bu da beklenen, raporlanan bir sonuçtur."""
import base64

import requests

from nexora.ed25519 import b58

ORDER_URL = "https://api.jup.ag/swap/v2/order"
ORDER_HATALARI = {1: "giriş token bakiyesi yetersiz", 2: "ağ ücreti için SOL yetersiz", 3: "tutar ücretsiz işlem alt sınırının altında"}


class EmirHatasi(RuntimeError):
    pass


def _cu16(b, i):
    """Solana compact-u16 okuma -> (değer, yeni konum)."""
    v = s = 0
    while True:
        if i >= len(b): raise EmirHatasi("işlem baytları eksik")
        x = b[i]; i += 1
        v |= (x & 0x7F) << s
        if not x & 0x80: return v, i
        s += 7
        if s > 14: raise EmirHatasi("compact-u16 geçersiz")


def cozumle(tx_b64):
    """İşlemin imza ve mesaj başlığını çözer. Dönüş: imza_sayisi, imzalar_bos, surum, imzaci_sayisi, hesaplar, mesaj."""
    try:
        b = base64.b64decode(tx_b64, validate=True)
    except (ValueError, TypeError):
        raise EmirHatasi("işlem base64 değil") from None
    n, i = _cu16(b, 0)
    imzalar = [b[i + 64 * k: i + 64 * (k + 1)] for k in range(n)]
    i += 64 * n
    mesaj = b[i:]
    if len(mesaj) < 4: raise EmirHatasi("mesaj eksik")
    j, surum = 0, "legacy"
    if mesaj[0] & 0x80:
        surum = mesaj[0] & 0x7F; j = 1
        if surum != 0: raise EmirHatasi(f"desteklenmeyen işlem sürümü {surum}")
    imzaci, salt_imzaci, salt_imzasiz = mesaj[j], mesaj[j + 1], mesaj[j + 2]
    k, j = _cu16(mesaj, j + 3)
    if j + 32 * k + 32 > len(mesaj): raise EmirHatasi("hesap listesi eksik")
    hesaplar = [b58(mesaj[j + 32 * x: j + 32 * (x + 1)]) for x in range(k)]
    return dict(imza_sayisi=n, imzalar_bos=all(s == bytes(64) for s in imzalar), surum=surum, imzaci_sayisi=imzaci,
                hesaplar=hesaplar, mesaj=mesaj, ham=b)


def denetle(tx_b64, taker):
    """Gerçek emirde imzalamadan önce zorunlu güvenlik denetimi. Sorun listesi döner (boş = geçti)."""
    c = cozumle(tx_b64)
    sorun = []
    if c["imzaci_sayisi"] != 1: sorun.append(f"{c['imzaci_sayisi']} imzacı gerekiyor (yalnızca bizim cüzdan beklenir)")
    if c["imza_sayisi"] != c["imzaci_sayisi"]: sorun.append("imza alanı sayısı başlıkla uyuşmuyor")
    if not c["hesaplar"] or c["hesaplar"][0] != taker: sorun.append("ücreti ödeyen hesap bizim cüzdan değil")
    if not c["imzalar_bos"]: sorun.append("işlem önceden imzalanmış")
    return sorun, c


class EmirHazirlayici:
    def __init__(self, helius, api_key="", session=None, timeout=10):
        self.helius, self.api_key = helius, api_key
        self.session, self.timeout = session or requests.Session(), timeout

    def hazirla(self, giris, cikis, miktar_raw, taker, kayma_bps=None):
        if isinstance(miktar_raw, bool) or not isinstance(miktar_raw, int) or miktar_raw <= 0: raise EmirHatasi("miktar geçersiz")
        params = {"inputMint": giris, "outputMint": cikis, "amount": str(miktar_raw), "taker": taker,
                  "excludeRouters": "jupiterz", "maxSupportedTransactionVersion": "0"}
        if kayma_bps is not None: params["slippageBps"] = str(int(kayma_bps))
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        try:
            r = self.session.get(ORDER_URL, params=params, headers=headers, timeout=self.timeout)
        except requests.RequestException:
            raise EmirHatasi("Jupiter bağlantı hatası") from None
        if r.status_code == 429: raise EmirHatasi("Jupiter hız sınırı (429)")
        if r.status_code != 200: raise EmirHatasi(f"Jupiter HTTP {r.status_code}")
        try:
            d = r.json()
        except ValueError:
            raise EmirHatasi("Jupiter yanıtı okunamadı") from None
        tx = d.get("transaction") if isinstance(d, dict) else None
        sonuc = dict(router=d.get("router"), out_amount=d.get("outAmount"), request_id=d.get("requestId"),
                     mod=d.get("mode"), ucret_bps=d.get("feeBps"), surum=d.get("transactionVersion"), transaction=None)
        if not tx:
            kod = d.get("errorCode")
            sonuc["hata"] = ORDER_HATALARI.get(kod, d.get("errorMessage") or "işlem oluşturulmadı")
            sonuc["hata_kodu"] = kod
            return sonuc
        sonuc["transaction"] = tx
        return sonuc

    def simule(self, tx_b64):
        """Zincirde simülasyon: hiçbir şey gönderilmez. Dönüş: basarili, hata, birim (compute unit), son günlükler."""
        res = self.helius.call("simulateTransaction", [tx_b64, {"encoding": "base64", "sigVerify": False,
                                                               "replaceRecentBlockhash": True, "commitment": "confirmed"}])
        v = res.get("value") if isinstance(res, dict) else None
        if not isinstance(v, dict): raise EmirHatasi("simülasyon yanıtı geçersiz")
        return dict(basarili=v.get("err") is None, hata=v.get("err"), birim=v.get("unitsConsumed"),
                    gunluk=(v.get("logs") or [])[-6:])

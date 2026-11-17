"""Giden e-posta (şifre sıfırlama kodu). SMTP ayarları ortam değişkenlerinden okunur; kodda sır YOK.

Öncelik: NEXORA_BREVO_API_KEY tanımlıysa Brevo HTTPS API'si kullanılır (önerilen). Yoksa aşağıdaki SMTP ayarları.
Ortam değişkenleri (sunucuda /etc/nexora.env içinde):
  NEXORA_SMTP_HOST=smtp.gmail.com   NEXORA_SMTP_PORT=587
  NEXORA_SMTP_KULLANICI=<gönderen e-posta>   NEXORA_SMTP_PAROLA=<uygulama şifresi>
  NEXORA_SMTP_GONDEREN=<gönderen e-posta>
Ayar eksikse gönderim hata verir; çağıran taraf bunu yakalar, kullanıcıya bilgi sızdırmaz."""
import os, smtplib, ssl
from email.message import EmailMessage

import requests

BREVO_URL = "https://api.brevo.com/v3/smtp/email"   # HTTPS (443): SMTP portlarının engellendiği sunucularda da çalışır


class EpostaHatasi(RuntimeError):
    pass


def ayar():
    return dict(host=os.getenv("NEXORA_SMTP_HOST", ""), port=int(os.getenv("NEXORA_SMTP_PORT", "587") or 587),
                kullanici=os.getenv("NEXORA_SMTP_KULLANICI", ""), parola=os.getenv("NEXORA_SMTP_PAROLA", ""),
                gonderen=os.getenv("NEXORA_SMTP_GONDEREN", ""))


def gonder(alici, konu, metin, cfg=None, smtp=smtplib.SMTP, http=requests):
    cfg = cfg or ayar()
    anahtar = os.getenv("NEXORA_BREVO_API_KEY", "").strip()
    if anahtar:
        if not cfg["gonderen"]: raise EpostaHatasi("gönderen adresi ayarlanmamış")
        try:
            r = http.post(BREVO_URL, timeout=15, headers={"api-key": anahtar, "accept": "application/json"},
                          json={"sender": {"name": "NEXORA", "email": cfg["gonderen"]}, "to": [{"email": alici}],
                                "subject": konu, "textContent": metin})
        except requests.RequestException as e:
            raise EpostaHatasi(f"Brevo'ya ulaşılamadı: {type(e).__name__}") from None
        if r.status_code not in (200, 201, 202):
            raise EpostaHatasi(f"Brevo HTTP {r.status_code}")          # yanıt gövdesi (olası ayrıntı) loglanmaz
        return
    if not cfg["host"] or not cfg["gonderen"]: raise EpostaHatasi("e-posta ayarları yapılmamış")
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = konu, cfg["gonderen"], alici
    m.set_content(metin)
    with smtp(cfg["host"], cfg["port"], timeout=15) as s:
        s.starttls(context=ssl.create_default_context())
        if cfg["kullanici"]: s.login(cfg["kullanici"], cfg["parola"])
        s.send_message(m)

"""Giden e-posta (şifre sıfırlama kodu). SMTP ayarları ortam değişkenlerinden okunur; kodda sır YOK.

Ortam değişkenleri (sunucuda /etc/nexora.env içinde):
  NEXORA_SMTP_HOST=smtp.gmail.com   NEXORA_SMTP_PORT=587
  NEXORA_SMTP_KULLANICI=<gönderen e-posta>   NEXORA_SMTP_PAROLA=<uygulama şifresi>
  NEXORA_SMTP_GONDEREN=<gönderen e-posta>
Ayar eksikse gönderim hata verir; çağıran taraf bunu yakalar, kullanıcıya bilgi sızdırmaz."""
import os, smtplib, ssl
from email.message import EmailMessage


class EpostaHatasi(RuntimeError):
    pass


def ayar():
    return dict(host=os.getenv("NEXORA_SMTP_HOST", ""), port=int(os.getenv("NEXORA_SMTP_PORT", "587") or 587),
                kullanici=os.getenv("NEXORA_SMTP_KULLANICI", ""), parola=os.getenv("NEXORA_SMTP_PAROLA", ""),
                gonderen=os.getenv("NEXORA_SMTP_GONDEREN", ""))


def gonder(alici, konu, metin, cfg=None, smtp=smtplib.SMTP):
    cfg = cfg or ayar()
    if not cfg["host"] or not cfg["gonderen"]: raise EpostaHatasi("e-posta ayarları yapılmamış")
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = konu, cfg["gonderen"], alici
    m.set_content(metin)
    with smtp(cfg["host"], cfg["port"], timeout=15) as s:
        s.starttls(context=ssl.create_default_context())
        if cfg["kullanici"]: s.login(cfg["kullanici"], cfg["parola"])
        s.send_message(m)

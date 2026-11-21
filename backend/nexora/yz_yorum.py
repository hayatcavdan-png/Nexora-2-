"""Yapay zekâ destekli analiz (20.11.2026, kullanıcı isteği): ölçüm raporlarını bir dil modeline (Claude) yorumlatır.

SALT OKUNUR YORUM: hiçbir ayarı değiştirmez, işlem açmaz. Modele yalnızca raporun metni gider (toplu rakamlar ve herkese
açık zincir adresleri); API anahtarı, cüzdan anahtarı, üye bilgisi GİTMEZ.
Etkinleştirme: /etc/nexora.env içine ANTHROPIC_API_KEY=... (isteğe bağlı YZ_YORUM_MODEL). Anahtar yoksa kural tabanlı
kısa yorum döner. Maliyet koruması: sonuç 1 saat önbellekte tutulur, yeniden üretme en erken 5 dakikada bir,
konu başına günde en fazla YZ_YORUM_GUNLUK (varsayılan 30) çağrı."""
import json, os, time

import requests

API = "https://api.anthropic.com/v1/messages"
MODEL = os.getenv("YZ_YORUM_MODEL", "claude-haiku-5-5")      # 21.11: en ucuz model (analiz başına ~0,1 sent); istenirse claude-sonnet-5-5
ONBELLEK_SN = 3600
YENILE_SN = 300
GUNLUK = int(os.getenv("YZ_YORUM_GUNLUK", "30"))
KONULAR = ("hl", "teshis")

SISTEM = """Sen NEXORA'nın ölçüm analistisin. NEXORA PAPER modda çalışan bir kopya-işlem sistemidir: gerçek para ve gerçek emir yoktur.
Sana bir ölçüm raporu verilecek. Türkçe, sade ve kısa yaz (en fazla 220 kelime). Kurallar:
- Yalnızca rapordaki rakamlara dayan; rakam uydurma, raporda olmayanı varsayma.
- Örneklem küçükse (ör. 30'dan az kapanan ölçüm) bunu açıkça söyle ve kesin hüküm verme.
- Yatırım tavsiyesi verme, gerçek paraya geçmeyi önerme.
- Risk kuralı veya işlem kuralı değişikliği önerirsen 'kullanıcı onayına sunulabilir' diye belirt; kendiliğinden uygulanmaz.
Biçim (başlıklar aynen):
Özet: 2-3 cümle.
Güçlü yanlar: en fazla 3 madde.
Zayıf yanlar / riskler: en fazla 3 madde.
Sonraki adım: 1-2 madde, ölçülebilir."""


def _yol(konu, dizin="."): return os.path.join(dizin, f"yz_yorum_{konu}.json")


def _oku(yol):
    try: return json.load(open(yol))
    except (OSError, ValueError): return {}


def _yaz(yol, d):
    with open(yol + ".tmp", "w") as f: json.dump(d, f, ensure_ascii=False)
    os.replace(yol + ".tmp", yol)


def kural_yorumu_hl(r):
    """Anahtar yokken ya da model çağrısı başarısızken: Hyperliquid raporundan kural tabanlı kısa yorum."""
    if not r or not r.get("kapanan"):
        return "Henüz kapanan ölçüm yok. Takip edilen trader'lar sıfırdan pozisyon açıp kapattıkça sonuçlar birikecek."
    b, k = r["biz"], r["kaynak"]; L = []
    L.append(f"{r['kapanan']} kapanan ölçüm: biz ortalama %{b['ort']:+.2f} (medyan %{b['medyan']:+.2f}, kazanan %{b['pozitif']}).")
    if k["ort"] is not None:
        L.append(f"Trader'ların kendisi ortalama %{k['ort']:+.2f}; aradaki fark gecikme ve ücretten geliyor"
                 + (f" (gecikme medyanı %{r['gecikme_pct']:+.3f})." if r.get("gecikme_pct") is not None else "."))
    if r.get("dk30", {}).get("ort") is not None:
        L.append(f"30 dakikada çıksaydık ortalama %{r['dk30']['ort']:+.2f}.")
    if r["kapanan"] < 30: L.append("Örneklem küçük (30'dan az): sonuçlar henüz karar için yeterli değil.")
    return " ".join(L)


def _cagir(anahtar, metin, s=None):
    s = s or requests
    r = s.post(API, timeout=60, headers={"x-api-key": anahtar, "anthropic-version": "2023-06-01", "content-type": "application/json"},
               json=dict(model=MODEL, max_tokens=900, system=SISTEM, messages=[{"role": "user", "content": metin}]))
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
    return "".join(b.get("text", "") for b in r.json().get("content") or [] if b.get("type") == "text").strip()


def analiz(konu, rapor_metni, kural_metni="", yenile=False, dizin=".", now=None, anahtar=None, s=None):
    """Dönüş: dict(etkin, metin, kaynak='yz'|'kural'|'onbellek', ts, model, uyari)."""
    if konu not in KONULAR: raise ValueError("konu: " + ", ".join(KONULAR))
    now = now if now is not None else time.time()
    anahtar = (anahtar if anahtar is not None else os.getenv("ANTHROPIC_API_KEY", "")).strip()
    yol = _yol(konu, dizin); d = _oku(yol)
    gun = time.strftime("%Y-%m-%d", time.gmtime(now))
    sayac = d.get("sayac", {}) if d.get("gun") == gun else {}
    if not anahtar:
        return dict(etkin=False, metin=kural_metni, kaynak="kural", ts=now, model=None,
                    uyari="Yapay zekâ yorumu kapalı: sunucuda ANTHROPIC_API_KEY tanımlı değil. Kural tabanlı özet gösteriliyor.")
    taze = d.get("metin") and now - d.get("ts", 0) < (YENILE_SN if yenile else ONBELLEK_SN)
    if taze:
        return dict(etkin=True, metin=d["metin"], kaynak="onbellek", ts=d["ts"], model=d.get("model"),
                    uyari="Son 5 dakikada üretildi; yeniden üretme biraz sonra." if yenile else None)
    if sum(sayac.values()) >= GUNLUK:
        return dict(etkin=True, metin=d.get("metin") or kural_metni, kaynak="onbellek" if d.get("metin") else "kural",
                    ts=d.get("ts", now), model=d.get("model"), uyari=f"Günlük yapay zekâ çağrı sınırı ({GUNLUK}) doldu.")
    try:
        metin = _cagir(anahtar, f"Rapor türü: {konu}\n\n{rapor_metni[:24000]}", s)
    except Exception as e:
        return dict(etkin=True, metin=d.get("metin") or kural_metni, kaynak="onbellek" if d.get("metin") else "kural",
                    ts=d.get("ts", now), model=d.get("model"), uyari=f"Yapay zekâ çağrısı başarısız: {str(e)[:120]}")
    sayac[konu] = sayac.get(konu, 0) + 1
    _yaz(yol, dict(metin=metin, ts=now, model=MODEL, gun=gun, sayac=sayac))
    return dict(etkin=True, metin=metin, kaynak="yz", ts=now, model=MODEL, uyari=None)

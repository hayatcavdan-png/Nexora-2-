"""BTC haber ve sosyal medya duyarlılığı: Gemini + Google Arama ile son 24 saatin özeti (SALT OKUNUR).

Varsayılan KAPALI (BTC_HABER=1 ile açılır; GEMINI_API_KEY gerekir). Sonuç 3 saat önbellekte tutulur (kota için).
Çıktı: {"duygu": -2..+2, "ozet": "...", "olaylar": [...], "kaynaklar": [{"baslik","url"}]}.
Bu sinyalin geçmişi yoktur, geriye dönük sınanamaz; her tur kaydedilir ve 4 saat sonra canlı olarak puanlanır.
X/Twitter ve Reddit'e doğrudan erişim yoktur (ücretli/kimlik doğrulamalı API); arama sonuçlarında görünen
sosyal medya ve haber içeriği üzerinden özetlenir. Model metni veri değil yorumdur: kararı tek başına belirlemez."""
import json, os, re, time, urllib.request

from nexora import yz_xai

URL = os.getenv("YZ_ARAMA_URL", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent")
ONBELLEK_SN = 3 * 3600


def acik():
    return os.getenv("BTC_HABER") == "1"


def istem():
    return ("Google aramasını kullanarak SON 24 SAATTE Bitcoin (BTC) ile ilgili haberleri, makro gelişmeleri "
            "(Fed, ETF akışları, düzenleme, büyük borsa olayları) ve sosyal medyadaki (X/Twitter, Reddit, kripto "
            "toplulukları, tanınmış trader ve analistlerin) genel duyarlılığı incele. Eski haberleri dikkate alma. "
            "Önümüzdeki saatler için BTC fiyatına etkisi açısından genel duygu puanı ver: -2 çok olumsuz, -1 olumsuz, "
            "0 nötr/karışık, +1 olumlu, +2 çok olumlu. Emin değilsen 0 ver. "
            "YALNIZCA şu JSON'u döndür: "
            '{"duygu": -2..2 tam sayı, "ozet": "en fazla 30 kelime Türkçe", "olaylar": ["en fazla 3 kısa madde"]}')


def cozumle(yanit):
    """generateContent yanıtı -> dict ya da None."""
    try:
        aday = (yanit.get("candidates") or [])[0]
        metin = "".join(p.get("text", "") for p in (aday.get("content") or {}).get("parts") or [])
    except (IndexError, AttributeError, TypeError):
        return None
    m = re.search(r"\{.*\}", metin or "", re.S)
    if not m: return None
    try: d = json.loads(m.group(0))
    except ValueError: return None
    try: duygu = int(round(float(str(d.get("duygu")).replace("+", ""))))
    except (TypeError, ValueError): return None
    if not -2 <= duygu <= 2: return None
    kaynak = []
    for c in ((aday.get("groundingMetadata") or {}).get("groundingChunks") or [])[:6]:
        w = c.get("web") or {}
        if w.get("uri"): kaynak.append(dict(baslik=str(w.get("title", ""))[:80], url=w["uri"]))
    return dict(duygu=duygu, ozet=str(d.get("ozet", ""))[:300],
                olaylar=[str(x)[:120] for x in (d.get("olaylar") or [])][:3], kaynaklar=kaynak)


def cagir(api_key, post=None, model=None):
    govde = json.dumps({"contents": [{"role": "user", "parts": [{"text": istem()}]}],
                        "tools": [{"google_search": {}}]}).encode("utf-8")
    if post is not None: return post(govde)
    req = urllib.request.Request(URL.format(model=model or yz_xai.MODEL), data=govde, method="POST",
                                 headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def getir(paper, now=None, post=None):
    """(haber|None, hata|None). Önbellek: paper state 'haber_ts'/'haber_json'."""
    if not acik(): return None, None
    now = now or time.time()
    try:
        ts = float(paper._get("haber_ts") or 0)
        if now - ts < ONBELLEK_SN:
            return json.loads(paper._get("haber_json")), None
    except (TypeError, ValueError):
        pass
    anahtar = os.getenv("GEMINI_API_KEY", "")
    if not anahtar and post is None: return None, "GEMINI_API_KEY yok"
    try:
        h = cozumle(cagir(anahtar, post=post))
    except Exception as e:
        return None, f"haber: {type(e).__name__}: {str(e)[:100]}"
    if not h: return None, "haber: yanıt okunamadı"
    h["ts"] = now
    paper._set("haber_ts", now); paper._set("haber_json", json.dumps(h, ensure_ascii=False)); paper.db.commit()
    return h, None

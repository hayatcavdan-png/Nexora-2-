"""Token sembolleri (5.26.1): uygulama 'FLOAT' gibi okunur adlar göstersin diye. Jupiter'den toplu alınır ve
sembol_onbellek.json'da kalıcı tutulur (sembol değişmez). Bulunamayanlar 1 saatte bir yeniden denenir."""
import json, os, threading, time

DOSYA = "sembol_onbellek.json"
_KILIT = threading.Lock()
_BELLEK = None
_DENENDI = {}


def _yukle():
    global _BELLEK
    if _BELLEK is None:
        try: _BELLEK = json.load(open(DOSYA))
        except (OSError, ValueError): _BELLEK = {}
    return _BELLEK


def bul(mints, toplu=None, now=None):
    """{mint: sembol}. toplu(mints) -> {mint: ham bilgi} (token_bilgi.toplu). Hata olursa eldekini döner."""
    now = now or time.time()
    with _KILIT:
        b = _yukle()
        eksik = [m for m in dict.fromkeys(mints) if m and m not in b and now - _DENENDI.get(m, float("-inf")) > 3600][:100]
    if eksik and toplu is not None:
        try: gelen = toplu(eksik) or {}
        except Exception: gelen = {}
        with _KILIT:
            for m in eksik:
                _DENENDI[m] = now
                s = ((gelen.get(m) or {}).get("symbol") or "").strip()
                if s: b[m] = s[:12]
            try:
                with open(DOSYA + ".tmp", "w") as f: json.dump(b, f)
                os.replace(DOSYA + ".tmp", DOSYA)
            except OSError:
                pass
    return {m: b[m] for m in mints if m in b}


def ekle(satirlar, toplu=None):
    """Her satıra (token alanı olan) 'sembol' ekler."""
    s = bul([r.get("token") for r in satirlar], toplu)
    for r in satirlar: r["sembol"] = s.get(r.get("token"), "")
    return satirlar

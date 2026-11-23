"""Gemini günlük rapor pilotu. SALT OKUNUR: yalnızca toplulaştırılmış sayılardan kısa bir yorum üretir.

Hiçbir karar, eşik ya da işlem bu modülden etkilenmez. Varsayılan KAPALI (YZ_XAI=1 ile açılır).
Model çıktısındaki her sayı girdi verisinde yoksa rapor 'doğrulanamadı' olarak işaretlenir.
API: POST https://generativelanguage.googleapis.com/v1beta/interactions, başlık x-goog-api-key: GEMINI_API_KEY.
Model: gemini-3.1-flash-lite (kararlı; 2.5 Flash-Lite yeni hesaplara sınırlı)."""
import json, os, re, sys, urllib.request

URL = os.getenv("YZ_URL", "https://generativelanguage.googleapis.com/v1beta/interactions")
MODEL = os.getenv("YZ_MODEL", "gemini-3.1-flash-lite")
IZINLI = {0.0, 1.0, 2.0, 3.0, 5.0, 10.0, 100.0}          # cümle yapısında geçebilecek küçük sabitler
SAYI = re.compile(r"-?\d+(?:[.,]\d+)?")


def acik():
    return os.getenv("YZ_XAI") == "1"


def istem(veri):
    """Modele giden metin. Yalnızca verilen toplulaştırılmış veri; ham cüzdan/anahtar yok."""
    return ("Aşağıdaki kopyalama sisteminin günlük özet verisini Türkçe, en fazla 6 kısa madde ile yorumla. "
            "Yalnızca verideki sayıları kullan, yeni sayı uydurma. Alım/satım önerisi verme; "
            "yalnızca gözlem ve belirsizlik yaz.\n\nVERİ:\n" + json.dumps(veri, ensure_ascii=False, sort_keys=True))


def metin_cek(yanit):
    """Interactions yanıtındaki son metin bloğu (steps[].content[].text). Düşünme adımları metin taşımaz."""
    metinler = [c["text"] for adim in yanit.get("steps", []) if isinstance(adim, dict)
                for c in adim.get("content", []) if isinstance(c, dict) and c.get("text")]
    return metinler[-1] if metinler else None


def sayilar(metin):
    out = set()
    for ham in SAYI.findall(metin):
        try: out.add(round(float(ham.replace(",", ".")), 2))
        except ValueError: pass
    return out


def dogrula(metin, veri):
    """(ok, bilinmeyen_sayilar). Metindeki her sayı veride ya da küçük sabitlerde olmalı."""
    veri_say = {round(x, 2) for x in sayilar(json.dumps(veri))}
    veri_say |= {round(-x, 2) for x in veri_say}
    bilinmeyen = sorted(s for s in sayilar(metin) if s not in veri_say and s not in IZINLI and -s not in IZINLI)
    return (not bilinmeyen), bilinmeyen


def cagir(veri, api_key, post=None):
    govde = json.dumps({"model": MODEL, "input": istem(veri)}).encode("utf-8")
    if post is not None:
        return post(govde)
    req = urllib.request.Request(URL, data=govde, method="POST", headers={
        "x-goog-api-key": api_key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def rapor(veri, post=None):
    """Kapalıysa ya da GEMINI_API_KEY yoksa None. Açıksa {'metin','dogru','bilinmeyen','model','kullanim'}."""
    if not acik(): return None
    anahtar = os.getenv("GEMINI_API_KEY", "")
    if not anahtar and post is None: return None
    yanit = cagir(veri, anahtar, post=post)
    metin = metin_cek(yanit)
    if not metin: return {"metin": None, "dogru": False, "bilinmeyen": [], "model": MODEL, "hata": "boş yanıt"}
    ok, bil = dogrula(metin, veri)
    return {"metin": metin, "dogru": ok, "bilinmeyen": bil, "model": yanit.get("model", MODEL),
            "kullanim": yanit.get("usage")}


if __name__ == "__main__":                       # elle: YZ_XAI=1 GEMINI_API_KEY=... python3 -m nexora.yz_xai ozet.json
    with open(sys.argv[1], encoding="utf-8") as f: veri = json.load(f)
    sonuc = rapor(veri)
    if sonuc is None:
        print("Kapalı (YZ_XAI=1 ve GEMINI_API_KEY gerekli)."); sys.exit(0)
    print(sonuc["metin"] or "(boş)")
    print(f"\n[model={sonuc['model']} doğrulama={'geçti' if sonuc['dogru'] else 'BAŞARISIZ: ' + str(sonuc['bilinmeyen'])}]")

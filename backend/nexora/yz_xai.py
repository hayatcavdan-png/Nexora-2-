"""xAI (Grok) günlük rapor pilotu. SALT OKUNUR: yalnızca toplulaştırılmış sayılardan kısa bir yorum üretir.

Hiçbir karar, eşik ya da işlem bu modülden etkilenmez. Varsayılan KAPALI (YZ_XAI=1 ile açılır).
Model çıktısındaki her sayı girdi verisinde yoksa rapor 'doğrulanamadı' olarak işaretlenir.
API: POST https://api.x.ai/v1/responses, Authorization: Bearer <XAI_API_KEY> (docs.x.ai)."""
import json, os, re, sys, urllib.request

URL = os.getenv("XAI_URL", "https://api.x.ai/v1/responses")
MODEL = os.getenv("XAI_MODEL", "grok-4.3")
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
    """Responses API yanıtından son asistan metnini al (type=message, content type=output_text)."""
    for oge in yanit.get("output", []):
        if oge.get("type") != "message": continue
        for part in oge.get("content", []):
            if part.get("type") == "output_text" and part.get("text"):
                return part["text"]
    return None


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
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def rapor(veri, post=None):
    """Kapalıysa ya da anahtar yoksa None. Açıksa {'metin','dogru','bilinmeyen','model','kullanim'}."""
    if not acik(): return None
    anahtar = os.getenv("XAI_API_KEY", "")
    if not anahtar and post is None: return None
    yanit = cagir(veri, anahtar, post=post)
    metin = metin_cek(yanit)
    if not metin: return {"metin": None, "dogru": False, "bilinmeyen": [], "model": MODEL, "hata": "boş yanıt"}
    ok, bil = dogrula(metin, veri)
    return {"metin": metin, "dogru": ok, "bilinmeyen": bil, "model": yanit.get("model", MODEL),
            "kullanim": yanit.get("usage")}


if __name__ == "__main__":                       # elle: YZ_XAI=1 XAI_API_KEY=... python3 -m nexora.yz_xai ozet.json
    with open(sys.argv[1], encoding="utf-8") as f: veri = json.load(f)
    sonuc = rapor(veri)
    if sonuc is None:
        print("Kapalı (YZ_XAI=1 ve XAI_API_KEY gerekli)."); sys.exit(0)
    print(sonuc["metin"] or "(boş)")
    print(f"\n[model={sonuc['model']} doğrulama={'geçti' if sonuc['dogru'] else 'BAŞARISIZ: ' + str(sonuc['bilinmeyen'])}]")

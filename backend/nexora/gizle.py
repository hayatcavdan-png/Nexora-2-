"""Gizli bilgi maskeleme (N0: eski sistemin core/logger.py SensitiveDataFilter fikrinden uyarlandı).
Günlüğe ya da veritabanına yazılan her metinde API anahtarı, URL içindeki api-key ve bilinen ortam
anahtarlarının değerleri [GİZLİ] ile değiştirilir. Savunma katmanıdır: istemciler zaten anahtarsız hata üretir."""
import io, os, re

ANAHTAR_ORTAM = ("HELIUS_API_KEY", "JUPITER_API_KEY", "NEXORA_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY")
DESENLER = (
    re.compile(r"(?i)(api[-_]?key=)([^&\s\"']+)"),
    re.compile(r"(?i)\b(api[ _-]?key|secret|password|private[ _-]?key|x-api-key)(\s*[:=]\s*)(?!\[GİZLİ\])([^\s,;&\"']+)"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)"),
)


def gizle(metin):
    if not isinstance(metin, str) or not metin: return metin
    for ad in ANAHTAR_ORTAM:
        v = (os.getenv(ad) or "").strip()
        if len(v) >= 6: metin = metin.replace(v, "[GİZLİ]")
    metin = DESENLER[0].sub(lambda m: m.group(1) + "[GİZLİ]", metin)
    metin = DESENLER[1].sub(lambda m: m.group(1) + m.group(2) + "[GİZLİ]", metin)
    metin = DESENLER[2].sub(lambda m: m.group(1) + "[GİZLİ]", metin)
    return metin


class GizleyenAkis(io.TextIOBase):
    """sys.stdout/sys.stderr sarmalayıcısı: yazılan her şeyi maskeler (izleme çıktıları ve hata dökümleri dahil)."""
    def __init__(self, alt): self.alt = alt
    def write(self, s): return self.alt.write(gizle(s))
    def flush(self): return self.alt.flush()
    def isatty(self): return False
    @property
    def encoding(self): return getattr(self.alt, "encoding", "utf-8")


def kur():
    import sys
    if not isinstance(sys.stdout, GizleyenAkis): sys.stdout = GizleyenAkis(sys.stdout)
    if not isinstance(sys.stderr, GizleyenAkis): sys.stderr = GizleyenAkis(sys.stderr)

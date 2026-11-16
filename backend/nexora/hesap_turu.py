"""Hesap türü ayrımı (N3): kopyalanacak adres gerçek bir KULLANICI cüzdanı mı?

Kullanıcı cüzdanı = ed25519 eğrisi üzerinde bir açık anahtar + Sistem Programı'na ait + çalıştırılabilir değil + verisi yok.
Ayıklananlar:
  program          çalıştırılabilir hesap (ör. DEX programı)
  pda              eğri dışı adres (programın türettiği hesap: havuz kasası, protokol hesabı, çoklu imza kasası)
  program hesabı   Sistem Programı dışında bir programa ait veri hesabı (havuz durumu, token hesabı, piyasa)
  boş              zincirde hesap yok (bakiyesi sıfırlanıp kapanmış)
  bilinen          bilinen_hesaplar.txt'te etiketli adres (borsa, köprü, protokol; kullanıcı kendisi ekler)
Maliyet: 100 adres başına tek getMultipleAccounts isteği (veri gövdesi istenmez)."""
import os

SISTEM = "11111111111111111111111111111111"
KULLANICI = "kullanıcı"
_ALFABE = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_P = 2 ** 255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def b58(adres):
    n = 0
    for ch in adres:
        i = _ALFABE.find(ch)
        if i < 0: raise ValueError("base58 değil")
        n = n * 58 + i
    govde = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(adres) - len(adres.lstrip("1"))) + govde


def egri_ustunde(adres):
    """32 baytlık adres geçerli bir ed25519 noktası mı? PDA'lar bilinçli olarak eğri dışıdır."""
    try:
        b = b58(adres)
    except ValueError:
        return False
    if len(b) != 32: return False
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= _P: return False
    y2 = y * y % _P
    x2 = (y2 - 1) * pow(_D * y2 + 1, _P - 2, _P) % _P
    if x2 == 0: return not (b[31] >> 7)                       # x = 0 ise işaret biti 0 olmalı
    return pow(x2, (_P - 1) // 2, _P) == 1                     # x² bir kare kalan mı (Euler ölçütü)


def bilinenler(path="bilinen_hesaplar.txt"):
    """'adres  # etiket' satırları."""
    out = {}
    if not os.path.exists(path): return out
    for l in open(path):
        l = l.strip()
        if not l or l.startswith("#"): continue
        adres, _, etiket = l.partition("#")
        out[adres.strip()] = etiket.strip() or "bilinen hesap"
    return out


def tur(adres, bilgi, bilinen=None):
    """(tür, açıklama). bilgi: getMultipleAccounts'tan tek hesap (None = hesap yok)."""
    if bilinen and adres in bilinen: return "bilinen", bilinen[adres]
    if not egri_ustunde(adres): return "pda", "eğri dışı adres: bir programın türettiği hesap"
    if bilgi is None: return "boş", "zincirde hesap yok"
    if bilgi.get("executable"): return "program", "çalıştırılabilir program hesabı"
    sahip = bilgi.get("owner")
    if sahip != SISTEM: return "program hesabı", f"sahibi {str(sahip)[:4]}…{str(sahip)[-4:]} programı"
    return KULLANICI, "sistem programına ait imzalayıcı cüzdan"


def siniflandir(client, adresler, bilinen=None, parca=100):
    """{adres: (tür, açıklama)}. Eğri dışı ve bilinen adresler için istek yapılmaz."""
    bilinen = bilinen or {}
    sonuc, sorgu = {}, []
    for a in dict.fromkeys(adresler):
        if a in bilinen or not egri_ustunde(a): sonuc[a] = tur(a, None, bilinen)
        else: sorgu.append(a)
    for i in range(0, len(sorgu), parca):
        grup = sorgu[i:i + parca]
        res = client.call("getMultipleAccounts", [grup, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}])
        degerler = res.get("value") if isinstance(res, dict) else None
        if not isinstance(degerler, list) or len(degerler) != len(grup): raise ValueError("geçersiz hesap yanıtı")
        for a, b in zip(grup, degerler): sonuc[a] = tur(a, b if isinstance(b, dict) else None, bilinen)
    return sonuc

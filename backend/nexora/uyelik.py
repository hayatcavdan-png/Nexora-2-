"""Üyelik: kayıt/giriş, davet kodu, bağlantı kayıtları ve komisyon sonrası bakiye GÖSTERİMİ.

Kapsam (bilinçli olarak dar):
- Yalnızca PAPER modu. Para saklanmaz, komisyon tahsil edilmez, emir gönderilmez; komisyon yalnızca sanal hesaplanır.
- Hiçbir gizli anahtar (borsa API anahtarı, cüzdan özel anahtarı, seed) SAKLANMAZ ve istenmez. Bağlantılar için yalnızca
  herkese açık Solana adresi kaydedilir. Borsa API anahtarı alanı, gerçek emir onayına (N12) kadar kilitlidir.
- Parola: scrypt + kişiye özel tuz. Oturum anahtarı rastgele; veritabanında yalnızca SHA-256 özeti tutulur.
"""
import hashlib, hmac, os, re, secrets, sqlite3, time

from nexora.ed25519 import _ALFABE

OTURUM_SN = 30 * 86400
GIRIS_DENEME, GIRIS_PENCERE_SN = 5, 600
DAVET_ALFABE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"          # karışan harf/rakamlar yok
EPOSTA_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,24}$")

# Bağlantı türleri: (ad, durum). "adres" = yalnızca herkese açık adres kaydedilir; "kilitli" = henüz kullanılamaz.
BAGLANTILAR = {
    "solana_rpc": dict(ad="Solana RPC (Helius)", tur="sistem", aciklama="Zincir verisi: sistem sunucusu kullanır, sizden anahtar istenmez."),
    "jupiter": dict(ad="Jupiter fiyat/rota", tur="sistem", aciklama="Fiyat ve rota teklifleri: sistem sunucusu kullanır."),
    "phantom": dict(ad="Phantom / Solana cüzdanı", tur="adres", aciklama="Yalnızca herkese açık adresiniz kaydedilir. Özel anahtar ve seed phrase asla istenmez."),
    "binance": dict(ad="Binance API", tur="kilitli",
                    aciklama="Gerçek emir açılana kadar kilitli. Açıldığında yalnızca 'işlem yetkili', 'para çekme KAPALI', IP kısıtlı anahtar kabul edilecek."),
}


class UyelikHatasi(ValueError):
    pass


def adres_gecerli(a):
    """Solana adresi: base58, 32 bayt."""
    if not isinstance(a, str) or not 32 <= len(a) <= 44 or any(c not in _ALFABE for c in a): return False
    n = 0
    for c in a: n = n * 58 + _ALFABE.index(c)
    ham = b"\0" * (len(a) - len(a.lstrip("1"))) + n.to_bytes((n.bit_length() + 7) // 8, "big")
    return len(ham) == 32


def _ozet(parola, tuz):
    return hashlib.scrypt(parola.encode(), salt=tuz, n=2 ** 14, r=8, p=1, dklen=32)


def maskele(eposta):
    y, d = eposta.split("@", 1)
    return (y[:2] + "***" if len(y) > 2 else y[:1] + "***") + "@" + d


def komisyon_hesapla(baslangic, brut_kar, pct):
    """Kâr payı modeli: yalnızca pozitif net kârdan yüzde. Zararda komisyon 0. Dönüş: komisyon, net bakiye."""
    pct = max(0.0, min(float(pct), 50.0))
    kom = round(max(0.0, brut_kar) * pct / 100.0, 2)
    return dict(komisyon_pct=pct, komisyon=kom, net_kar=round(brut_kar - kom, 2), net_bakiye=round(baslangic + brut_kar - kom, 2))


class Uyelik:
    def __init__(self, yol=":memory:"):
        self.db = sqlite3.connect(yol, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS uye(id INTEGER PRIMARY KEY, eposta TEXT UNIQUE NOT NULL, tuz BLOB NOT NULL, ozet BLOB NOT NULL,
            davet_kodu TEXT UNIQUE NOT NULL, davet_eden INTEGER, ts REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS oturum(ozet TEXT PRIMARY KEY, uye INTEGER NOT NULL, bitis REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS baglanti(uye INTEGER NOT NULL, tur TEXT NOT NULL, adres TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY(uye, tur));
        CREATE TABLE IF NOT EXISTS giris_deneme(anahtar TEXT NOT NULL, ts REAL NOT NULL);
        """)

    # ---- kayıt / giriş
    def _kod(self):
        while True:
            k = "".join(secrets.choice(DAVET_ALFABE) for _ in range(8))
            if not self.db.execute("SELECT 1 FROM uye WHERE davet_kodu=?", (k,)).fetchone(): return k

    def kayit(self, eposta, parola, davet=""):
        eposta = (eposta or "").strip().lower()
        if not EPOSTA_RE.match(eposta): raise UyelikHatasi("e-posta geçersiz")
        if not isinstance(parola, str) or not 8 <= len(parola) <= 128: raise UyelikHatasi("parola 8-128 karakter olmalı")
        eden = None
        davet = (davet or "").strip().upper()
        if davet:
            r = self.db.execute("SELECT id FROM uye WHERE davet_kodu=?", (davet,)).fetchone()
            if not r: raise UyelikHatasi("davet kodu geçersiz")
            eden = r["id"]
        tuz = secrets.token_bytes(16)
        try:
            c = self.db.execute("INSERT INTO uye(eposta,tuz,ozet,davet_kodu,davet_eden,ts) VALUES(?,?,?,?,?,?)",
                                (eposta, tuz, _ozet(parola, tuz), self._kod(), eden, time.time()))
            self.db.commit()
        except sqlite3.IntegrityError:
            raise UyelikHatasi("bu e-posta zaten kayıtlı") from None
        return self._oturum(c.lastrowid)

    def giris(self, eposta, parola, now=None):
        now = now or time.time(); eposta = (eposta or "").strip().lower()
        self.db.execute("DELETE FROM giris_deneme WHERE ts<?", (now - GIRIS_PENCERE_SN,))
        if self.db.execute("SELECT COUNT(*) FROM giris_deneme WHERE anahtar=?", (eposta,)).fetchone()[0] >= GIRIS_DENEME:
            raise PermissionError("çok fazla deneme: 10 dakika sonra tekrar deneyin")
        r = self.db.execute("SELECT * FROM uye WHERE eposta=?", (eposta,)).fetchone()
        tuz = r["tuz"] if r else bytes(16)
        ok = hmac.compare_digest(_ozet(parola if isinstance(parola, str) else "", tuz), r["ozet"] if r else bytes(32)) and r is not None
        if not ok:
            self.db.execute("INSERT INTO giris_deneme VALUES(?,?)", (eposta, now)); self.db.commit()
            raise UyelikHatasi("e-posta veya parola hatalı")
        return self._oturum(r["id"], now)

    def _oturum(self, uye, now=None):
        now = now or time.time(); tok = secrets.token_urlsafe(32)
        self.db.execute("INSERT INTO oturum VALUES(?,?,?)", (hashlib.sha256(tok.encode()).hexdigest(), uye, now + OTURUM_SN))
        self.db.commit()
        return tok

    def uye(self, oturum, now=None):
        now = now or time.time()
        if not oturum: return None
        r = self.db.execute("SELECT u.* FROM oturum o JOIN uye u ON u.id=o.uye WHERE o.ozet=? AND o.bitis>?",
                            (hashlib.sha256(oturum.encode()).hexdigest(), now)).fetchone()
        return dict(r) if r else None

    def cikis(self, oturum):
        self.db.execute("DELETE FROM oturum WHERE ozet=?", (hashlib.sha256((oturum or "").encode()).hexdigest(),)); self.db.commit()

    # ---- bağlantılar
    def baglanti_kaydet(self, uye_id, tur, adres):
        b = BAGLANTILAR.get(tur)
        if not b: raise UyelikHatasi("bilinmeyen bağlantı")
        if b["tur"] != "adres": raise UyelikHatasi("bu bağlantı kullanıcıdan veri almaz" if b["tur"] == "sistem" else "bu bağlantı henüz kilitli")
        if not adres_gecerli(adres): raise UyelikHatasi("geçerli bir Solana adresi değil (özel anahtar/seed GİRMEYİN)")
        self.db.execute("INSERT OR REPLACE INTO baglanti VALUES(?,?,?,?)", (uye_id, tur, adres, time.time())); self.db.commit()

    def baglanti_sil(self, uye_id, tur):
        self.db.execute("DELETE FROM baglanti WHERE uye=? AND tur=?", (uye_id, tur)); self.db.commit()

    def baglantilar(self, uye_id):
        kayit = {r["tur"]: r["adres"] for r in self.db.execute("SELECT tur, adres FROM baglanti WHERE uye=?", (uye_id,))}
        cikti = []
        for tur, b in BAGLANTILAR.items():
            durum = {"sistem": "sistem kullanıyor", "kilitli": "kilitli"}.get(b["tur"], "bağlı" if tur in kayit else "bağlı değil")
            cikti.append(dict(tur=tur, ad=b["ad"], aciklama=b["aciklama"], durum=durum, adres=kayit.get(tur)))
        return cikti

    # ---- profil, davet, bakiye
    def profil(self, u):
        davetliler = [dict(eposta=maskele(r["eposta"]), ts=r["ts"]) for r in
                      self.db.execute("SELECT eposta, ts FROM uye WHERE davet_eden=? ORDER BY id DESC", (u["id"],))]
        return dict(eposta=u["eposta"], davet_kodu=u["davet_kodu"], davet_sayisi=len(davetliler), davetliler=davetliler[:20],
                    baglantilar=self.baglantilar(u["id"]))

    @staticmethod
    def bakiye(baslangic, brut_kar, pct):
        d = komisyon_hesapla(baslangic, brut_kar, pct)
        d.update(baslangic=round(baslangic, 2), brut_kar=round(brut_kar, 2), brut_bakiye=round(baslangic + brut_kar, 2),
                 sanal=True, not_="Komisyon yalnızca sanal gösterimdir; para saklanmaz, tahsilat yapılmaz.")
        return d

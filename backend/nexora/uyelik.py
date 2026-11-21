"""Üyelik: kayıt/giriş, davet kodu, bağlantı kayıtları ve komisyon sonrası bakiye GÖSTERİMİ.

Kapsam (bilinçli olarak dar):
- Yalnızca PAPER modu. Para saklanmaz, komisyon tahsil edilmez, emir gönderilmez; komisyon yalnızca sanal hesaplanır.
- Cüzdan özel anahtarı ve seed phrase ASLA istenmez ve saklanmaz. Solana için yalnızca herkese açık adres kaydedilir.
- Borsa API anahtarı (N29): yalnızca PARA ÇEKME İZNİ KAPALI olduğu borsadan doğrulanan anahtar kabul edilir; sunucuda
  yalnızca şifreli (kasa.py) saklanır ve şimdilik yalnızca bakiye OKUMAK için kullanılır. Emir gönderme yok (N31).
- Parola: scrypt + kişiye özel tuz. Oturum anahtarı rastgele; veritabanında yalnızca SHA-256 özeti tutulur.
"""
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, struct, time

from nexora.ed25519 import _ALFABE

OTURUM_SN = 30 * 86400
PORTFOY_MIN, PORTFOY_MAX, PORTFOY_VARSAYILAN = 10.0, 100_000.0, 100.0
GIRIS_DENEME, GIRIS_PENCERE_SN = 5, 600
DAVET_ALFABE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"          # karışan harf/rakamlar yok
EPOSTA_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,24}$")

# Bağlantı türleri: (ad, durum). "adres" = yalnızca herkese açık adres kaydedilir; "kilitli" = henüz kullanılamaz.
BAGLANTILAR = {
    "solana_rpc": dict(ad="Solana RPC (Helius)", tur="sistem", aciklama="Zincir verisi: sistem sunucusu kullanır, sizden anahtar istenmez."),
    "jupiter": dict(ad="Jupiter fiyat/rota", tur="sistem", aciklama="Fiyat ve rota teklifleri: sistem sunucusu kullanır."),
    "phantom": dict(ad="Phantom / Solana cüzdanı", tur="adres", aciklama="Yalnızca herkese açık adresiniz kaydedilir. Özel anahtar ve seed phrase asla istenmez."),
    "borsa": dict(ad="Borsa hesapları (Binance · OKX · KuCoin · MEXC)", tur="borsa",
                  aciklama="Kendi hesabınızın API anahtarı. Para çekme izni KAPALI olmalı; şifreli saklanır, şimdilik yalnızca bakiye okunur."),
}
BORSA_DENEME, BORSA_PENCERE_SN = 10, 3600
SIFIRLA_SN, SIFIRLA_TALEP, SIFIRLA_DENEME = 30 * 60, 3, 5     # kod 30 dk geçerli; 10 dk içinde en çok 3 istek, 5 yanlış deneme


class UyelikHatasi(ValueError):
    pass


# ---- İki adımlı doğrulama (N35, 21.11.2026): RFC 6238 TOTP (30 sn, 6 hane, SHA-1) — Google Authenticator, Microsoft
# Authenticator, Authy, 2FAS vb. ile uyumlu. Gizli anahtar sunucuda tutulur; kullanılan kod tekrar kullanılamaz.
IKI_ADIM_GEREKLI = "iki adımlı doğrulama kodu gerekli"
TOTP_ADIM, TOTP_HANE, TOTP_PENCERE = 30, 6, 1


def totp(gizli, sayac):
    k = base64.b32decode(gizli.upper() + "=" * (-len(gizli) % 8))
    h = hmac.new(k, struct.pack(">Q", sayac), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** TOTP_HANE).zfill(TOTP_HANE)


def totp_dogrula(gizli, kod, now, son=0):
    """Doğruysa kullanılan sayaç (tekrar kullanımı engellemek için saklanır), değilse None. ±1 adım saat kayması kabul."""
    kod = re.sub(r"\s", "", str(kod or ""))
    if not gizli or not re.fullmatch(r"\d{6}", kod): return None
    c = int(now // TOTP_ADIM)
    for s in range(c - TOTP_PENCERE, c + TOTP_PENCERE + 1):
        if s > (son or 0) and hmac.compare_digest(totp(gizli, s), kod): return s
    return None


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
        CREATE TABLE IF NOT EXISTS uye_portfoy(uye INTEGER PRIMARY KEY, baslangic REAL NOT NULL, giris_deger REAL NOT NULL,
            zirve REAL NOT NULL, ts REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sifirla(uye INTEGER PRIMARY KEY, ozet TEXT NOT NULL, bitis REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS borsa_anahtar(uye INTEGER NOT NULL, borsa TEXT NOT NULL, sifreli TEXT NOT NULL, maske TEXT NOT NULL,
            izin TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY(uye, borsa));
        """)
        var = {r["name"] for r in self.db.execute("PRAGMA table_info(uye)")}
        if "rol" not in var:                                                              # rol ayrımı (eski veritabanı)
            self.db.execute("ALTER TABLE uye ADD COLUMN rol TEXT NOT NULL DEFAULT 'uye'"); self.db.commit()
        for k, t in (("totp", "TEXT"), ("totp_acik", "INTEGER NOT NULL DEFAULT 0"), ("totp_son", "INTEGER NOT NULL DEFAULT 0")):
            if k not in var: self.db.execute(f"ALTER TABLE uye ADD COLUMN {k} {t}")
        self.db.commit()

    ROLLER = ("uye", "kurucu")

    def rol_ata(self, eposta, rol):
        """Rol yalnızca sunucuda komutla atanır (python3 -m nexora.uyelik kurucu <eposta>); uygulamadan değiştirilemez.
        Rol değişince o üyenin tüm oturumları kapanır: yeni yetki yeni girişle başlar."""
        if rol not in self.ROLLER: raise UyelikHatasi(f"rol {self.ROLLER} içinden olmalı")
        r = self.db.execute("SELECT id FROM uye WHERE eposta=?", ((eposta or "").strip().lower(),)).fetchone()
        if not r: raise UyelikHatasi("bu e-postayla kayıtlı üye yok")
        self.db.execute("UPDATE uye SET rol=? WHERE id=?", (rol, r["id"]))
        self.db.execute("DELETE FROM oturum WHERE uye=?", (r["id"],)); self.db.commit()
        return True

    def kurucular(self):
        return [r["eposta"] for r in self.db.execute("SELECT eposta FROM uye WHERE rol='kurucu' ORDER BY id")]

    # ---- kayıt / giriş
    def _kod(self):
        while True:
            k = "".join(secrets.choice(DAVET_ALFABE) for _ in range(8))
            if not self.db.execute("SELECT 1 FROM uye WHERE davet_kodu=?", (k,)).fetchone(): return k

    KAYIT_SINIRI = 20             # 10 dakikada en fazla bu kadar kayıt denemesi (tüm sunucu; toplu hesap açmaya karşı)

    def kayit(self, eposta, parola, davet="", now=None):
        now = now or time.time()
        if self._say("kayit", now) >= self.KAYIT_SINIRI: raise PermissionError("çok fazla kayıt denemesi: biraz sonra tekrar deneyin")
        self.db.execute("INSERT INTO giris_deneme VALUES('kayit', ?)", (now,)); self.db.commit()
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

    # ---- iki adımlı doğrulama
    def iki_adim_kur(self, uye_id):
        """Yeni gizli anahtar üretir (henüz AÇIK değil; ilk doğru kodla açılır). Dönüş: gizli anahtar ve otpauth bağlantısı."""
        r = self.db.execute("SELECT eposta, totp_acik FROM uye WHERE id=?", (uye_id,)).fetchone()
        if not r: raise UyelikHatasi("üye yok")
        if r["totp_acik"]: raise UyelikHatasi("iki adımlı doğrulama zaten açık")
        gizli = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
        self.db.execute("UPDATE uye SET totp=?, totp_son=0 WHERE id=?", (gizli, uye_id)); self.db.commit()
        from urllib.parse import quote
        uri = f"otpauth://totp/NEXORA:{quote(r['eposta'])}?secret={gizli}&issuer=NEXORA&digits={TOTP_HANE}&period={TOTP_ADIM}"
        return dict(gizli=gizli, uri=uri)

    def _kod_denetle(self, r, kod, now, sayac_adi):
        self.db.execute("DELETE FROM giris_deneme WHERE ts<?", (now - GIRIS_PENCERE_SN,))
        if self.db.execute("SELECT COUNT(*) FROM giris_deneme WHERE anahtar=?", (sayac_adi,)).fetchone()[0] >= GIRIS_DENEME:
            raise PermissionError("çok fazla deneme: 10 dakika sonra tekrar deneyin")
        s = totp_dogrula(r["totp"], kod, now, r["totp_son"])
        if s is None:
            self.db.execute("INSERT INTO giris_deneme VALUES(?,?)", (sayac_adi, now)); self.db.commit()
            raise UyelikHatasi("doğrulama kodu hatalı")
        self.db.execute("UPDATE uye SET totp_son=? WHERE id=?", (s, r["id"])); self.db.commit()

    def iki_adim_onayla(self, uye_id, kod, now=None):
        now = now or time.time()
        r = self.db.execute("SELECT * FROM uye WHERE id=?", (uye_id,)).fetchone()
        if not r or not r["totp"]: raise UyelikHatasi("önce kurulumu başlatın")
        self._kod_denetle(r, kod, now, f"totp:{uye_id}")
        self.db.execute("UPDATE uye SET totp_acik=1 WHERE id=?", (uye_id,)); self.db.commit()
        return True

    def iki_adim_kapat(self, uye_id, parola, kod, now=None):
        """Kapatmak için parola VE geçerli kod gerekir (çalınmış oturumla kapatılamasın)."""
        now = now or time.time()
        r = self.db.execute("SELECT * FROM uye WHERE id=?", (uye_id,)).fetchone()
        if not r or not r["totp_acik"]: raise UyelikHatasi("iki adımlı doğrulama zaten kapalı")
        if not hmac.compare_digest(_ozet(parola if isinstance(parola, str) else "", r["tuz"]), r["ozet"]):
            raise UyelikHatasi("parola hatalı")
        self._kod_denetle(r, kod, now, f"totp:{uye_id}")
        self.db.execute("UPDATE uye SET totp=NULL, totp_acik=0, totp_son=0 WHERE id=?", (uye_id,)); self.db.commit()
        return True

    def iki_adim_sifirla(self, eposta):
        """Telefon kaybında yalnızca SUNUCUDA: python3 -m nexora.uyelik 2fa-kapat <eposta>. Oturumlar da kapanır."""
        r = self.db.execute("SELECT id FROM uye WHERE eposta=?", ((eposta or "").strip().lower(),)).fetchone()
        if not r: raise UyelikHatasi("bu e-postayla kayıtlı üye yok")
        self.db.execute("UPDATE uye SET totp=NULL, totp_acik=0, totp_son=0 WHERE id=?", (r["id"],))
        self.db.execute("DELETE FROM oturum WHERE uye=?", (r["id"],)); self.db.commit()

    def giris(self, eposta, parola, now=None, kod=None):
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
        if r["totp_acik"]:
            if not str(kod or "").strip(): raise UyelikHatasi(IKI_ADIM_GEREKLI)
            self._kod_denetle(r, kod, now, f"totp:{r['id']}")
        return self._oturum(r["id"], now)

    # ---- şifre sıfırlama (e-posta kodu)
    def _say(self, anahtar, now):
        self.db.execute("DELETE FROM giris_deneme WHERE ts<?", (now - GIRIS_PENCERE_SN,))
        return self.db.execute("SELECT COUNT(*) FROM giris_deneme WHERE anahtar=?", (anahtar,)).fetchone()[0]

    def sifre_sifirla_iste(self, eposta, gonder, now=None):
        """Kod üretir, `gonder(eposta, kod)` ile yollar. Hesap yoksa da AYNI sonuç döner (e-posta varlığı sızmaz)."""
        now = now or time.time(); eposta = (eposta or "").strip().lower()
        if self._say(f"sifirla:{eposta}", now) >= SIFIRLA_TALEP:
            raise PermissionError("çok fazla istek: 10 dakika sonra tekrar deneyin")
        self.db.execute("INSERT INTO giris_deneme VALUES(?,?)", (f"sifirla:{eposta}", now)); self.db.commit()
        r = self.db.execute("SELECT id FROM uye WHERE eposta=?", (eposta,)).fetchone()
        if r is None: return
        kod = "".join(secrets.choice(DAVET_ALFABE) for _ in range(8))
        self.db.execute("INSERT OR REPLACE INTO sifirla VALUES(?,?,?)", (r["id"], hashlib.sha256(kod.encode()).hexdigest(), now + SIFIRLA_SN))
        self.db.commit()
        gonder(eposta, kod)

    def sifre_sifirla(self, eposta, kod, yeni, now=None):
        """Kodu doğrular, parolayı değiştirir, tüm oturumları kapatır ve bu cihaza yeni oturum verir. Kod tek kullanımlık."""
        now = now or time.time(); eposta = (eposta or "").strip().lower()
        if not isinstance(yeni, str) or not 8 <= len(yeni) <= 128: raise UyelikHatasi("yeni parola 8-128 karakter olmalı")
        r = self.db.execute("SELECT id FROM uye WHERE eposta=?", (eposta,)).fetchone()
        hata = UyelikHatasi("kod geçersiz veya süresi dolmuş")
        if r is None: raise hata
        uid = r["id"]
        if self._say(f"kod:{uid}", now) >= SIFIRLA_DENEME: raise PermissionError("çok fazla yanlış kod: 10 dakika sonra deneyin")
        s = self.db.execute("SELECT ozet, bitis FROM sifirla WHERE uye=?", (uid,)).fetchone()
        ok = s is not None and s["bitis"] >= now and hmac.compare_digest(
            s["ozet"], hashlib.sha256(str(kod or "").strip().upper().encode()).hexdigest())
        if not ok:
            self.db.execute("INSERT INTO giris_deneme VALUES(?,?)", (f"kod:{uid}", now)); self.db.commit()
            raise hata
        tuz = secrets.token_bytes(16)
        self.db.execute("DELETE FROM sifirla WHERE uye=?", (uid,))
        self.db.execute("UPDATE uye SET tuz=?, ozet=? WHERE id=?", (tuz, _ozet(yeni, tuz), uid))
        self.db.execute("DELETE FROM oturum WHERE uye=?", (uid,))
        self.db.commit()
        return self._oturum(uid, now)

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

    def parola_degistir(self, uye_id, eski, yeni, now=None):
        """Parolayı değiştirir (eski parola doğrulanır), TÜM oturumları kapatır ve bu kullanıcı için yeni bir oturum döner."""
        now = now or time.time()
        if not isinstance(yeni, str) or not 8 <= len(yeni) <= 128: raise UyelikHatasi("yeni parola 8-128 karakter olmalı")
        if yeni == (eski or ""): raise UyelikHatasi("yeni parola eskisiyle aynı olamaz")
        sayac = f"parola:{uye_id}"                                   # ele geçirilmiş oturumla sınırsız deneme olmasın
        self.db.execute("DELETE FROM giris_deneme WHERE ts<?", (now - GIRIS_PENCERE_SN,))
        if self.db.execute("SELECT COUNT(*) FROM giris_deneme WHERE anahtar=?", (sayac,)).fetchone()[0] >= GIRIS_DENEME:
            raise PermissionError("çok fazla deneme: 10 dakika sonra tekrar deneyin")
        r = self.db.execute("SELECT * FROM uye WHERE id=?", (uye_id,)).fetchone()
        if r is None or not hmac.compare_digest(_ozet(eski if isinstance(eski, str) else "", r["tuz"]), r["ozet"]):
            self.db.execute("INSERT INTO giris_deneme VALUES(?,?)", (sayac, now)); self.db.commit()
            raise UyelikHatasi("mevcut parola hatalı")
        tuz = secrets.token_bytes(16)
        self.db.execute("UPDATE uye SET tuz=?, ozet=? WHERE id=?", (tuz, _ozet(yeni, tuz), uye_id))
        self.db.execute("DELETE FROM oturum WHERE uye=?", (uye_id,))
        self.db.commit()
        return self._oturum(uye_id, now)

    def tum_oturumlari_kapat(self, uye_id, now=None):
        """Bu hesabın tüm oturumlarını kapatır; bu cihaz dahil yeniden giriş gerekir. Borsa anahtarlarına dokunmaz."""
        self.db.execute("DELETE FROM oturum WHERE uye=?", (uye_id,)); self.db.commit()

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
            if b["tur"] == "borsa":
                n = self.db.execute("SELECT COUNT(*) FROM borsa_anahtar WHERE uye=?", (uye_id,)).fetchone()[0]
                cikti.append(dict(tur=tur, ad=b["ad"], aciklama=b["aciklama"], durum=f"{n} borsa bağlı" if n else "bağlı değil", adres=None))
                continue
            durum = {"sistem": "sistem kullanıyor", "kilitli": "kilitli"}.get(b["tur"], "bağlı" if tur in kayit else "bağlı değil")
            cikti.append(dict(tur=tur, ad=b["ad"], aciklama=b["aciklama"], durum=durum, adres=kayit.get(tur)))
        return cikti

    # ---- borsa API anahtarları (N29/N30): yalnızca okuma
    def borsa_bagla(self, uye_id, borsa, anahtar, gizli, parola, kasa, istemci, now=None):
        """Anahtarı borsadan doğrular (izinler), çekim izni kapalıysa şifreli kaydeder. `istemci(borsa, k, g, p)` -> Istemci."""
        from nexora import borsa_hesap as BH
        from nexora.kasa import maskele as _mask
        now = now or time.time(); borsa = (borsa or "").strip().lower()
        if borsa not in BH.BORSALAR: raise UyelikHatasi("desteklenmeyen borsa")
        k, g = BH._temiz(anahtar), BH._temiz(gizli)
        p = BH._temiz(parola, en_az=1, en_cok=64) if BH.BORSALAR[borsa]["parola"] else ""
        if not k or not g: raise UyelikHatasi("API anahtarı ve gizli anahtar gerekli (boşluksuz)")
        if BH.BORSALAR[borsa]["parola"] and not p: raise UyelikHatasi(f"{BH.BORSALAR[borsa]['ad']} için API parolası (passphrase) gerekli")
        sayac = f"borsa:{uye_id}"
        self.db.execute("DELETE FROM giris_deneme WHERE ts<?", (now - BORSA_PENCERE_SN,))
        if self.db.execute("SELECT COUNT(*) FROM giris_deneme WHERE anahtar=?", (sayac,)).fetchone()[0] >= BORSA_DENEME:
            raise PermissionError("çok fazla bağlantı denemesi: 1 saat sonra tekrar deneyin")
        self.db.execute("INSERT INTO giris_deneme VALUES(?,?)", (sayac, now)); self.db.commit()
        try:
            izin = BH.izinler(istemci(borsa, k, g, p))
            BH.kabul_et(izin)
        except BH.BorsaHesapHatasi as e:
            raise UyelikHatasi(str(e)) from None
        sifreli = kasa.sifrele(json.dumps(dict(k=k, g=g, p=p)), baglam=f"uye:{uye_id}:borsa:{borsa}")
        self.db.execute("INSERT OR REPLACE INTO borsa_anahtar VALUES(?,?,?,?,?,?)",
                        (uye_id, borsa, sifreli, _mask(k), json.dumps(izin), now)); self.db.commit()
        return self.borsalar(uye_id)

    def borsa_sil(self, uye_id, borsa):
        self.db.execute("DELETE FROM borsa_anahtar WHERE uye=? AND borsa=?", (uye_id, (borsa or "").strip().lower())); self.db.commit()
        return self.borsalar(uye_id)

    def borsalar(self, uye_id):
        from nexora.borsa_hesap import BORSALAR
        kayit = {r["borsa"]: r for r in self.db.execute("SELECT borsa, maske, izin, ts FROM borsa_anahtar WHERE uye=?", (uye_id,))}
        out = []
        for b, m in BORSALAR.items():
            r = kayit.get(b)
            out.append(dict(borsa=b, ad=m["ad"], parola_gerekli=m["parola"], bagli=r is not None,
                            maske=r["maske"] if r else None, izin=json.loads(r["izin"]) if r else None, ts=r["ts"] if r else None))
        return out

    def borsa_bakiye(self, uye_id, kasa, istemci, fiyat=None):
        """Bağlı her borsanın GERÇEK bakiyesi (yalnızca okuma). `fiyat(borsa)` -> {taban: dict(son)} ya da None."""
        from nexora import borsa_hesap as BH
        out, toplam = [], 0.0
        for r in self.db.execute("SELECT borsa, sifreli FROM borsa_anahtar WHERE uye=?", (uye_id,)).fetchall():
            b = r["borsa"]
            try:
                a = json.loads(kasa.coz(r["sifreli"], baglam=f"uye:{uye_id}:borsa:{b}"))
                oz = BH.ozet_bakiye(BH.bakiyeler(istemci(b, a["k"], a["g"], a["p"]), fiyat(b) if fiyat else None))
                toplam += oz["toplam_usd"]; out.append(dict(borsa=b, ad=BH.BORSALAR[b]["ad"], **oz))
            except BH.BorsaHesapHatasi as e:
                out.append(dict(borsa=b, ad=BH.BORSALAR[b]["ad"], hata=str(e)))
            except Exception:
                out.append(dict(borsa=b, ad=BH.BORSALAR[b]["ad"], hata="anahtar okunamadı: yeniden bağlayın"))
        return dict(borsalar=out, toplam_usd=round(toplam, 2), ts=time.time(),
                    not_="Gerçek bakiyeniz kendi borsa hesabınızdadır; uygulama yalnızca okur, emir göndermez.")

    # ---- profil, davet, bakiye
    def profil(self, u):
        davetliler = [dict(eposta=maskele(r["eposta"]), ts=r["ts"]) for r in
                      self.db.execute("SELECT eposta, ts FROM uye WHERE davet_eden=? ORDER BY id DESC", (u["id"],))]
        return dict(eposta=u["eposta"], davet_kodu=u["davet_kodu"], davet_sayisi=len(davetliler), davetliler=davetliler[:20],
                    baglantilar=self.baglantilar(u["id"]), rol=u.get("rol") or "uye", iki_adim=bool(u.get("totp_acik")))

    # ---- üye başına sanal hesap (N15: hesap izolasyonu)
    def portfoy_baslat(self, uye_id, baslangic, sistem_deger, now=None):
        """Üyenin sanal hesabını (yeniden) başlatır: katılım anındaki sistem değeri kaydedilir. Pozisyonlar portföyün
        yüzdesiyle açıldığı için üyenin getirisi = sistemin bu andan sonraki yüzde getirisi."""
        try: baslangic = float(baslangic)
        except (TypeError, ValueError): raise UyelikHatasi("başlangıç tutarı sayı olmalı") from None
        if not PORTFOY_MIN <= baslangic <= PORTFOY_MAX: raise UyelikHatasi(f"başlangıç {PORTFOY_MIN:.0f}-{PORTFOY_MAX:.0f} USDC arası olmalı")
        if not sistem_deger or sistem_deger <= 0: raise UyelikHatasi("sistem değeri okunamadı")
        self.db.execute("INSERT OR REPLACE INTO uye_portfoy VALUES(?,?,?,?,?)", (uye_id, baslangic, sistem_deger, baslangic, now or time.time()))
        self.db.commit()

    def uye_bakiye(self, uye_id, sistem_deger, pct, now=None):
        """Üyenin kendi sanal bakiyesi; kayıt yoksa 100 USDC ile şimdi başlatılır. Zirve (yüksek su işareti) tutulur."""
        r = self.db.execute("SELECT * FROM uye_portfoy WHERE uye=?", (uye_id,)).fetchone()
        if r is None:
            self.portfoy_baslat(uye_id, PORTFOY_VARSAYILAN, sistem_deger, now)
            r = self.db.execute("SELECT * FROM uye_portfoy WHERE uye=?", (uye_id,)).fetchone()
        deger = r["baslangic"] * sistem_deger / r["giris_deger"]
        zirve = max(r["zirve"], deger)
        if zirve > r["zirve"]:
            self.db.execute("UPDATE uye_portfoy SET zirve=? WHERE uye=?", (zirve, uye_id)); self.db.commit()
        d = self.bakiye(r["baslangic"], deger - r["baslangic"], pct)
        d.update(katilim_ts=r["ts"], getiri_pct=round((deger / r["baslangic"] - 1) * 100, 2), zirve=round(zirve, 2),
                 zirveden_dusus_pct=round((zirve - deger) / zirve * 100, 2) if zirve > 0 else 0.0, kisisel=True)
        return d

    @staticmethod
    def bakiye(baslangic, brut_kar, pct):
        d = komisyon_hesapla(baslangic, brut_kar, pct)
        d.update(baslangic=round(baslangic, 2), brut_kar=round(brut_kar, 2), brut_bakiye=round(baslangic + brut_kar, 2),
                 sanal=True, not_="Komisyon yalnızca sanal gösterimdir; para saklanmaz, tahsilat yapılmaz.")
        return d


if __name__ == "__main__":                       # sunucuda:  python3 -m nexora.uyelik kurucu <eposta>   |   uye <eposta>   |   liste
    import sys
    u = Uyelik(os.getenv("UYELIK_DB", "nexora_uyelik.db"))
    if len(sys.argv) == 3 and sys.argv[1] == "2fa-kapat":
        try:
            u.iki_adim_sifirla(sys.argv[2]); print(f"{sys.argv[2]}: iki adımlı doğrulama kapatıldı, oturumlar kapandı. Uygulamadan yeniden kurun.")
        except UyelikHatasi as e:
            sys.exit(f"Hata: {e}")
    elif len(sys.argv) == 2 and sys.argv[1] == "liste":
        print("Kurucular:", ", ".join(u.kurucular()) or "yok")
    elif len(sys.argv) == 3 and sys.argv[1] in Uyelik.ROLLER:
        try:
            u.rol_ata(sys.argv[2], sys.argv[1]); print(f"{sys.argv[2]}: rol '{sys.argv[1]}' (oturumları kapandı, yeniden giriş yapın)")
        except UyelikHatasi as e:
            sys.exit(f"Hata: {e}")
    else:
        sys.exit("Kullanım: python3 -m nexora.uyelik kurucu <eposta> | uye <eposta> | liste | 2fa-kapat <eposta>")

"""Üye bazlı ayrı paper hesapları (5.27).

- Her üyenin kendi paper defteri vardır (ayrı SQLite dosyası); ana/ortak motorun
  bakiyesi, pozisyonu ve işlemleri üyeye gösterilmez.
- Üye kendi başlangıç değerini seçer (10–10000 USDC), bu değer yalnızca hesap ilk
  açılırken belirlenir.
- Bot yalnızca üye "başlat" dediğinde o üye için sinyal işler.
- Bot kapatılınca açık pozisyonlar son fiyattan kapatılır (onay zorunlu).
"""
import os, sqlite3, threading, time
from nexora.core import Paper

BASLANGIC_MIN = 10.0
BASLANGIC_MAX = 10000.0
DIZIN = os.getenv("NEXORA_HESAP_DIR", "nexora_hesap")

_kilit = threading.Lock()
_acik = {}          # uye_id -> Paper


class HesapHatasi(ValueError):
    pass


def _kayit_db():
    os.makedirs(DIZIN, exist_ok=True)
    db = sqlite3.connect(os.path.join(DIZIN, "hesaplar.db"), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS hesap(uye INTEGER PRIMARY KEY, baslangic REAL NOT NULL,
        bot INTEGER NOT NULL DEFAULT 0, acilis REAL, guncelleme REAL)""")
    db.commit()
    return db


def _kayit(uye):
    db = _kayit_db()
    try:
        r = db.execute("SELECT * FROM hesap WHERE uye=?", (uye,)).fetchone()
        return dict(r) if r else None
    finally:
        db.close()


def _hesap(uye):
    """Üyenin paper defteri (önbellekli). Kayıt yoksa HesapHatasi."""
    with _kilit:
        if uye in _acik:
            return _acik[uye]
        k = _kayit(uye)
        if not k:
            raise HesapHatasi("hesap yok")
        p = Paper(os.path.join(DIZIN, f"uye_{int(uye)}.db"), start_cash=k["baslangic"], dagit=False)
        _acik[uye] = p
        return p


def durum(uye):
    k = _kayit(uye)
    if not k:
        return {"var": False, "bot": False}
    return {"var": True, "bot": bool(k["bot"]), "baslangic": k["baslangic"], "acilis": k["acilis"]}


def bot_ac(uye, baslangic=None, now=None):
    """Botu başlatır. Yeni hesapta başlangıç değeri zorunlu; mevcut hesapta değer değişmez."""
    now = now or time.time()
    with _kilit:
        db = _kayit_db()
        try:
            r = db.execute("SELECT * FROM hesap WHERE uye=?", (uye,)).fetchone()
            if r is None:
                try:
                    b = float(baslangic)
                except (TypeError, ValueError):
                    raise HesapHatasi("başlangıç değeri gerekli")
                if not (BASLANGIC_MIN <= b <= BASLANGIC_MAX):
                    raise HesapHatasi(f"başlangıç {BASLANGIC_MIN:g}–{BASLANGIC_MAX:g} USDC arasında olmalı")
                db.execute("INSERT INTO hesap(uye, baslangic, bot, acilis, guncelleme) VALUES(?,?,1,?,?)",
                           (uye, b, now, now))
            else:
                db.execute("UPDATE hesap SET bot=1, guncelleme=? WHERE uye=?", (now, uye))
            db.commit()
        finally:
            db.close()
    return durum(uye)


def bot_kapat(uye, onay, fiyat=None, now=None):
    """Botu kapatır ve açık pozisyonları kapatır. `onay` True değilse hiçbir şey yapmaz.
    fiyat(token) -> USD/token veya None; None ise pozisyonun son fiyatı, o da yoksa maliyet kullanılır."""
    if onay is not True:
        raise HesapHatasi("kapatma onayı gerekli")
    now = now or time.time()
    k = _kayit(uye)
    if not k:
        raise HesapHatasi("hesap yok")
    kapatilan = 0
    if k["bot"]:
        p = _hesap(uye)
        for pos in [dict(r) for r in p.db.execute("SELECT * FROM positions")]:
            token = pos["token"]
            px = fiyat(token) if fiyat else None
            if not px:
                px = pos["last_price"] or (pos["cost"] / pos["qty"] if pos["qty"] else 0.0)
            p.record_sell(f"kapat:{uye}:{token}:{int(now * 1000)}", "bot-kapat", token,
                          pos["qty"] * px, note="bot kapatıldı")
            kapatilan += 1
    with _kilit:
        db = _kayit_db()
        try:
            db.execute("UPDATE hesap SET bot=0, guncelleme=? WHERE uye=?", (now, uye))
            db.commit()
        finally:
            db.close()
    return {"kapatilan": kapatilan, "durum": durum(uye)}


def dagit(event_id, wallet, token, side, price, liquidity_usd, signal_age_s):
    """Ortak motora gelen her sinyali, botu açık olan üyelerin kendi defterlerine iletir."""
    db = _kayit_db()
    try:
        uyeler = [r["uye"] for r in db.execute("SELECT uye FROM hesap WHERE bot=1")]
    finally:
        db.close()
    for uye in uyeler:
        try:
            _hesap(uye).handle_signal(f"{event_id}|u{uye}", wallet, token, side, price, liquidity_usd, signal_age_s)
        except Exception as e:      # bir üyenin hatası diğerlerini durdurmaz
            print(f"[nexora] hesap {uye} sinyal hata: {type(e).__name__}", flush=True)


def portfoy(uye):
    """Üyenin kendi paper özeti (cüzdan adresi içermez)."""
    p = _hesap(uye)
    d = p.portfolio()
    d["baslangic"] = p.start_cash
    d["bot"] = durum(uye)["bot"]
    return d


def islemler(uye, limit=50):
    return [{k: v for k, v in t.items() if k != "wallet"} for t in _hesap(uye).trades(limit)]

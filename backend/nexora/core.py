"""NEXORA 2.0 çekirdek: paper trading + risk motoru (yalnızca stdlib).
GERÇEK İŞLEM YOK. Execution bilinçli olarak kapalıdır (N11/N12 sonrası)."""
import sqlite3, time, threading

CFG = dict(
    start_cash=100.0,        # USDC (sanal)
    max_pos_pct=0.05,        # pozisyon başına %5
    daily_loss_pct=0.03,     # günlük %3 zarar eşiği
    max_positions=5,
    max_signal_age_s=10,
    min_liquidity_usd=50_000,
    base_slippage=0.005,     # %0.5
    net_fee_usd=0.01,        # ağ + priority fee tahmini
    max_price_impact_pct=3.0,     # Jupiter teklifinde izin verilen en yüksek fiyat etkisi
    max_roundtrip_loss_pct=6.0,   # al-hemen-sat teklif kaybı (spread+etki+ücret) üst sınırı
    fee_reserve_usd=1.0,          # SOL işlem ücretleri için her zaman ayrılan nakit (alımda kullanılmaz)
    max_positions_per_wallet=2,   # tek bir kaynak cüzdan en fazla bu kadar açık pozisyon doldurabilir
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS positions(token TEXT PRIMARY KEY, qty REAL, cost REAL, last_price REAL, wallet TEXT);
CREATE TABLE IF NOT EXISTS shadow(id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE, wallet TEXT, token TEXT,
  opened_ts REAL, size_usd REAL, qty_raw TEXT, decimals INTEGER, rt_loss_pct REAL, impact_pct REAL, reason TEXT,
  status TEXT, closed_ts REAL, proceeds_usd REAL, pnl_usd REAL, close_event TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, event_id TEXT UNIQUE,
  wallet TEXT, token TEXT, side TEXT, qty REAL, price REAL, fee REAL, pnl REAL, decision TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS pos_iz(id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT, wallet TEXT, opened_ts REAL, cost REAL,
  min_pct REAL, max_pct REAL, marks INTEGER DEFAULT 0, tam INTEGER, status TEXT, closed_ts REAL, pnl REAL);
CREATE TABLE IF NOT EXISTS token_bilgi(event_id TEXT PRIMARY KEY, token TEXT, ts REAL, yas_sn REAL, likidite REAL,
  mcap REAL, sahip REAL, organik REAL, organik_etiket TEXT, top_pct REAL, dev_pct REAL, sus INTEGER, launchpad TEXT, hata TEXT);
CREATE TABLE IF NOT EXISTS stop_tetik(iz_id INTEGER, esik REAL, ts REAL, pnl REAL, PRIMARY KEY(iz_id, esik));
"""

# Zarar kesme ölçümü (yalnızca ölçüm, işlem davranışını DEĞİŞTİRMEZ): açık pozisyonun değerlemesi
# maliyetin bu yüzdeleri kadar altına ilk düştüğünde, o anki gerçek satış teklifiyle "burada satsaydık" K/Z'si kaydedilir.
STOP_ESIKLERI = (10, 20, 30, 50)

class Paper:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(positions)")}
        if "qty_raw" not in cols:            # eski şemadan güvenli geçiş
            self.db.execute("ALTER TABLE positions ADD COLUMN qty_raw TEXT")
            self.db.execute("ALTER TABLE positions ADD COLUMN decimals INTEGER")
        if "event_id" not in {r[1] for r in self.db.execute("PRAGMA table_info(pos_iz)")}:
            self.db.execute("ALTER TABLE pos_iz ADD COLUMN event_id TEXT")
        if self._get("cash") is None:
            self._set("cash", CFG["start_cash"]); self._set("kill", "0")
            self._set("day", time.strftime("%Y-%m-%d")); self._set("day_start", CFG["start_cash"])
        self.db.commit()

    def _get(self, k):
        r = self.db.execute("SELECT v FROM state WHERE k=?", (k,)).fetchone()
        return r["v"] if r else None
    def _set(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (k, str(v)))

    def cash(self): return float(self._get("cash"))
    def killed(self): return self._get("kill") == "1"
    def set_kill(self, on):
        with self.lock: self._set("kill", "1" if on else "0"); self.db.commit()

    def equity(self):
        pos = self.db.execute("SELECT SUM(qty*last_price) s FROM positions").fetchone()["s"] or 0.0
        return self.cash() + pos

    def _roll_day(self):
        d = time.strftime("%Y-%m-%d")
        if self._get("day") != d:
            self._set("day", d); self._set("day_start", self.equity())

    def _log(self, ev, wallet, token, side, qty, price, fee, pnl, decision, reason):
        self.db.execute("INSERT INTO trades(ts,event_id,wallet,token,side,qty,price,fee,pnl,decision,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (time.time(), ev, wallet, token, side, qty, price, fee, pnl, decision, reason))
        self.db.commit()
        return dict(decision=decision, reason=reason, qty=qty, price=price, fee=fee, pnl=pnl)

    def handle_signal(self, event_id, wallet, token, side, price, liquidity_usd, signal_age_s):
        """Idempotent: aynı event_id ikinci kez işlenmez."""
        with self.lock:
            if self.db.execute("SELECT 1 FROM trades WHERE event_id=?", (event_id,)).fetchone():
                return dict(decision="ATLANDI", reason="tekrarlanan olay")
            self._roll_day()
            rej = lambda why: self._log(event_id, wallet, token, side, 0, price, 0, 0, "REDDEDİLDİ", why)
            if side not in ("buy", "sell") or price <= 0: return rej("geçersiz sinyal")
            if self.killed(): return rej("acil durdurma aktif")
            if signal_age_s > CFG["max_signal_age_s"]: return rej("sinyal bayat")
            if liquidity_usd < CFG["min_liquidity_usd"]: return rej("likidite yetersiz/bilinmiyor")

            if side == "buy":
                eq, ds = self.equity(), float(self._get("day_start"))
                if ds > 0 and (ds - eq) / ds >= CFG["daily_loss_pct"]: return rej("günlük zarar limiti")
                n = self.db.execute("SELECT COUNT(*) c FROM positions").fetchone()["c"]
                has = self.db.execute("SELECT 1 FROM positions WHERE token=?", (token,)).fetchone()
                if n >= CFG["max_positions"] and not has: return rej("maks. eşzamanlı pozisyon")
                size = eq * CFG["max_pos_pct"]
                if size + CFG["net_fee_usd"] > self.cash(): return rej("yetersiz nakit")
                slip = CFG["base_slippage"] + size / liquidity_usd
                fill = price * (1 + slip); qty = size / fill
                self._set("cash", self.cash() - size - CFG["net_fee_usd"])
                self.db.execute("""INSERT INTO positions(token,qty,cost,last_price,wallet) VALUES(?,?,?,?,?) ON CONFLICT(token) DO UPDATE SET
                  qty=qty+excluded.qty, cost=cost+excluded.cost, last_price=excluded.last_price""",
                  (token, qty, size, price, wallet))
                return self._log(event_id, wallet, token, side, qty, fill, CFG["net_fee_usd"], 0, "KOPYALANDI", "ok")

            pos = self.db.execute("SELECT * FROM positions WHERE token=?", (token,)).fetchone()
            if not pos: return rej("sahip olunmayan pozisyon satılamaz")
            slip = CFG["base_slippage"] + pos["qty"] * price / liquidity_usd
            fill = price * (1 - slip); proceeds = pos["qty"] * fill - CFG["net_fee_usd"]
            pnl = proceeds - pos["cost"]
            self._set("cash", self.cash() + proceeds)
            self.db.execute("DELETE FROM positions WHERE token=?", (token,))
            return self._log(event_id, wallet, token, side, pos["qty"], fill, CFG["net_fee_usd"], pnl, "KOPYALANDI", "ok")

    # --- Gerçek teklif (Jupiter) ile çalışan yol -------------------------------------------
    def seen(self, event_id):
        with self.lock:
            return self.db.execute("SELECT 1 FROM trades WHERE event_id=?", (event_id,)).fetchone() is not None

    def reject(self, event_id, wallet, token, side, reason):
        with self.lock:
            if self.db.execute("SELECT 1 FROM trades WHERE event_id=?", (event_id,)).fetchone():
                return dict(decision="ATLANDI", reason="tekrarlanan olay")
            return self._log(event_id, wallet, token, side, 0, 0, 0, 0, "REDDEDİLDİ", reason)

    def position(self, token):
        with self.lock:
            r = self.db.execute("SELECT * FROM positions WHERE token=?", (token,)).fetchone()
            return dict(r) if r else None

    def precheck(self, side, token, signal_age_s, wallet=None):
        """Ağ isteği yapmadan önce kurallar. (red_gerekçesi | None, pozisyon_büyüklüğü_usd)."""
        with self.lock:
            self._roll_day()
            if side not in ("buy", "sell"): return "geçersiz sinyal", 0
            if self.killed(): return "acil durdurma aktif", 0
            if signal_age_s > CFG["max_signal_age_s"]: return "sinyal bayat", 0
            has = self.db.execute("SELECT qty_raw FROM positions WHERE token=?", (token,)).fetchone()
            if side == "sell":
                if not has: return "sahip olunmayan pozisyon satılamaz", 0
                if not has["qty_raw"]: return "pozisyon miktarı bilinmiyor", 0
                return None, 0
            if has: return "bu token'da zaten pozisyon var", 0
            eq, ds = self.equity(), float(self._get("day_start"))
            if ds > 0 and (ds - eq) / ds >= CFG["daily_loss_pct"]: return "günlük zarar limiti", 0
            n = self.db.execute("SELECT COUNT(*) c FROM positions").fetchone()["c"]
            if n >= CFG["max_positions"]: return "maks. eşzamanlı pozisyon", 0
            if wallet is not None:
                nw = self.db.execute("SELECT COUNT(*) c FROM positions WHERE wallet=?", (wallet,)).fetchone()["c"]
                if nw >= CFG["max_positions_per_wallet"]: return "bu cüzdan için pozisyon sınırı dolu", 0
            size = round(eq * CFG["max_pos_pct"], 6)
            if size + CFG["net_fee_usd"] + CFG["fee_reserve_usd"] > self.cash():
                return "yetersiz nakit (ücret rezervi korunuyor)", 0
            return None, size

    def record_buy(self, event_id, wallet, token, size_usd, qty_raw, decimals, note="ok"):
        with self.lock:
            if self.db.execute("SELECT 1 FROM trades WHERE event_id=?", (event_id,)).fetchone():
                return dict(decision="ATLANDI", reason="tekrarlanan olay")
            if self.db.execute("SELECT 1 FROM positions WHERE token=?", (token,)).fetchone():
                return self._log(event_id, wallet, token, "buy", 0, 0, 0, 0, "REDDEDİLDİ", "bu token'da zaten pozisyon var")
            fee = CFG["net_fee_usd"]
            if size_usd + fee > self.cash():
                return self._log(event_id, wallet, token, "buy", 0, 0, 0, 0, "REDDEDİLDİ", "yetersiz nakit")
            qty = int(qty_raw) / 10 ** decimals
            price = size_usd / qty
            self._set("cash", self.cash() - size_usd - fee)
            self.db.execute("INSERT INTO positions(token,qty,cost,last_price,wallet,qty_raw,decimals) VALUES(?,?,?,?,?,?,?)",
                            (token, qty, size_usd, price, wallet, str(int(qty_raw)), decimals))
            self.db.execute("INSERT INTO pos_iz(token,wallet,opened_ts,cost,tam,status,event_id) VALUES(?,?,?,?,1,'open',?)",
                            (token, wallet, time.time(), size_usd, event_id))
            return self._log(event_id, wallet, token, "buy", qty, price, fee, 0, "KOPYALANDI", note)

    def record_sell(self, event_id, wallet, token, proceeds_usd, note="ok"):
        with self.lock:
            if self.db.execute("SELECT 1 FROM trades WHERE event_id=?", (event_id,)).fetchone():
                return dict(decision="ATLANDI", reason="tekrarlanan olay")
            pos = self.db.execute("SELECT * FROM positions WHERE token=?", (token,)).fetchone()
            if not pos:
                return self._log(event_id, wallet, token, "sell", 0, 0, 0, 0, "REDDEDİLDİ", "sahip olunmayan pozisyon satılamaz")
            fee = CFG["net_fee_usd"]
            net = proceeds_usd - fee
            pnl = net - pos["cost"]
            price = proceeds_usd / pos["qty"] if pos["qty"] else 0
            self._set("cash", self.cash() + net)
            self.db.execute("DELETE FROM positions WHERE token=?", (token,))
            iz = self._iz(token, pos)
            pct = pnl / pos["cost"] * 100 if pos["cost"] else 0.0
            self.db.execute("""UPDATE pos_iz SET status='closed', closed_ts=?, pnl=?, min_pct=MIN(COALESCE(min_pct, ?), ?),
                max_pct=MAX(COALESCE(max_pct, ?), ?) WHERE id=?""", (time.time(), pnl, pct, pct, pct, pct, iz))
            return self._log(event_id, wallet, token, "sell", pos["qty"], price, fee, pnl, "KOPYALANDI", note)

    def mark_price(self, token, price):
        """Açık pozisyonu güncel teklif fiyatıyla değerler (gerçekleşmemiş K/Z için) ve zarar kesme ölçümünü günceller."""
        with self.lock:
            self.db.execute("UPDATE positions SET last_price=? WHERE token=?", (price, token))
            self._set(f"mark_ts:{token}", time.time())
            pos = self.db.execute("SELECT * FROM positions WHERE token=?", (token,)).fetchone()
            if pos and pos["cost"]:
                iz = self._iz(token, pos)
                pnl = pos["qty"] * price - CFG["net_fee_usd"] - pos["cost"]      # şimdi satsaydık (satış ücreti dahil)
                pct = pnl / pos["cost"] * 100
                self.db.execute("""UPDATE pos_iz SET marks=marks+1, min_pct=MIN(COALESCE(min_pct, ?), ?),
                    max_pct=MAX(COALESCE(max_pct, ?), ?) WHERE id=?""", (pct, pct, pct, pct, iz))
                for e in STOP_ESIKLERI:
                    if pct <= -e:
                        self.db.execute("INSERT OR IGNORE INTO stop_tetik(iz_id,esik,ts,pnl) VALUES(?,?,?,?)",
                                        (iz, e, time.time(), pnl))
            self.db.commit()

    def token_bilgi_kaydet(self, event_id, token, ts, d, hata=None):
        d = d or {}
        with self.lock:
            self.db.execute("""INSERT OR REPLACE INTO token_bilgi(event_id,token,ts,yas_sn,likidite,mcap,sahip,organik,organik_etiket,
                top_pct,dev_pct,sus,launchpad,hata) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, token, ts, d.get("yas_sn"), d.get("likidite"), d.get("mcap"), d.get("sahip"), d.get("organik"),
                 d.get("organik_etiket"), d.get("top_pct"), d.get("dev_pct"), d.get("sus"), d.get("launchpad"), hata))
            self.db.commit()

    def _iz(self, token, pos):
        """Açık pozisyonun ölçüm kaydı; bu sürümden önce açılmış pozisyon için eksik (tam=0) kayıt oluşturur."""
        r = self.db.execute("SELECT id FROM pos_iz WHERE token=? AND status='open' ORDER BY id DESC LIMIT 1", (token,)).fetchone()
        if r: return r["id"]
        b = self.db.execute("SELECT ts FROM trades WHERE token=? AND side='buy' AND decision='KOPYALANDI' ORDER BY id DESC LIMIT 1",
                            (token,)).fetchone()
        cur = self.db.execute("INSERT INTO pos_iz(token,wallet,opened_ts,cost,tam,status) VALUES(?,?,?,?,0,'open')",
                              (token, pos["wallet"], b["ts"] if b else time.time(), pos["cost"]))
        return cur.lastrowid

    # --- Gölge işlemler: reddedilen alımlar için "girseydik ne olurdu" ölçümü -------------------
    # Nakde, pozisyonlara ve risk limitlerine dokunmaz. Eşik ayarı (N10) için veri toplar.
    MAX_OPEN_SHADOWS = 50

    def shadow_open(self, event_id, wallet, token, size_usd, qty_raw, decimals, rt_loss_pct, impact_pct, reason):
        with self.lock:
            n = self.db.execute("SELECT COUNT(*) c FROM shadow WHERE status='open'").fetchone()["c"]
            if n >= self.MAX_OPEN_SHADOWS: return False
            cur = self.db.execute("""INSERT OR IGNORE INTO shadow(event_id,wallet,token,opened_ts,size_usd,qty_raw,decimals,
                rt_loss_pct,impact_pct,reason,status) VALUES(?,?,?,?,?,?,?,?,?,?,'open')""",
                (event_id, wallet, token, time.time(), size_usd, str(int(qty_raw)), decimals, rt_loss_pct, impact_pct, reason))
            self.db.commit()
            return cur.rowcount == 1

    def open_shadows(self, wallet, token):
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT * FROM shadow WHERE status='open' AND wallet=? AND token=?", (wallet, token))]

    def shadow_close(self, shadow_id, proceeds_usd, close_event, status="closed", note=None):
        with self.lock:
            r = self.db.execute("SELECT size_usd FROM shadow WHERE id=? AND status='open'", (shadow_id,)).fetchone()
            if not r: return None
            pnl = proceeds_usd - r["size_usd"] - 2 * CFG["net_fee_usd"]          # iki bacak ağ ücreti
            self.db.execute("""UPDATE shadow SET status=?, closed_ts=?, proceeds_usd=?, pnl_usd=?, close_event=?, note=?
                WHERE id=?""", (status, time.time(), proceeds_usd, pnl, close_event, note, shadow_id))
            self.db.commit()
            return pnl

    def shadows(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM shadow ORDER BY id")]

    def portfolio(self):
        rows = [dict(r) for r in self.db.execute("SELECT * FROM positions")]
        eq = self.equity()
        return dict(cash=self.cash(), equity=eq, pnl=eq - CFG["start_cash"], positions=rows, killed=self.killed())

    def trades(self, limit=50):
        return [dict(r) for r in self.db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))]

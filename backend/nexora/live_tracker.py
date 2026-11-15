"""Canlı cüzdan takibi (polling, salt okunur).
- Her cüzdan bağımsız işlenir; bir cüzdanın hatası diğerlerini durdurmaz.
- Üst üste hata veren cüzdan karantinaya alınır.
- Son görülen imza SQLite'ta tutulur (yeniden başlatmada güvenli devam).
- İlk çalıştırmada geçmiş taranmaz: yalnızca bundan sonraki işlemler izlenir.
- Aynı imza iki kez işlenmez (paper motoru event_id ile de korur).
Token güvenliği, fiyat ve likidite henüz bilinmediği için sinyaller paper motorunda
REDDEDİLİR (BİLİNMİYOR = ENGELLE). Bu aşama yalnızca algılamayı ve gecikmeyi ölçer."""
import sqlite3, threading, time
from nexora.swap_decoder import decode_swap

QUARANTINE_AFTER = 5
SCHEMA = """
CREATE TABLE IF NOT EXISTS tracker_wallets(wallet TEXT PRIMARY KEY, last_sig TEXT,
  errors INTEGER DEFAULT 0, quarantined INTEGER DEFAULT 0, last_error TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS tracker_seen(sig TEXT, wallet TEXT, PRIMARY KEY(sig, wallet));
CREATE TABLE IF NOT EXISTS tracker_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
  wallet TEXT, sig TEXT, side TEXT, token TEXT, token_delta TEXT, quote TEXT,
  block_time INTEGER, latency_s REAL, decision TEXT, reason TEXT);
"""

class LiveTracker:
    def __init__(self, client, paper, db_path, wallets, clock=time.time, sleep=time.sleep):
        self.client, self.paper, self.clock, self.sleep = client, paper, clock, sleep
        self.lock = threading.RLock()
        self.db = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(tracker_signals)")}
        if "source" not in cols:                       # eski şemadan güvenli geçiş
            self.db.execute("ALTER TABLE tracker_signals ADD COLUMN source TEXT DEFAULT 'poll'")
        for w in wallets:
            self.db.execute("INSERT OR IGNORE INTO tracker_wallets(wallet) VALUES(?)", (w.strip(),))
        self.db.commit()

    def _signatures(self, wallet, until=None):
        opts = {"limit": 25, "commitment": "confirmed"}
        if until: opts["until"] = until
        res = self.client.call("getSignaturesForAddress", [wallet, opts])
        if not isinstance(res, list): raise ValueError("imza listesi geçersiz")
        return [r for r in res if isinstance(r, dict) and isinstance(r.get("signature"), str)]

    def poll_wallet(self, wallet):
        """Ağ istekleri kilit dışında yapılır; WebSocket sinyalleri yoklama yüzünden beklemez."""
        with self.lock:
            row = self.db.execute("SELECT last_sig FROM tracker_wallets WHERE wallet=?", (wallet,)).fetchone()
        last = row[0] if row else None
        sigs = self._signatures(wallet, until=last)
        if not sigs: return []
        newest = sigs[0]["signature"]
        out = []
        if last is not None:              # ilk çalıştırmada geçmiş işlenmez, yalnızca işaret konur
            for item in reversed(sigs):   # eskiden yeniye
                if item.get("err") is not None: continue
                r = self.handle_signature(wallet, item["signature"], source="poll", retries=2)
                if r: out.append(r)
        with self.lock:
            self.db.execute("UPDATE tracker_wallets SET last_sig=?, errors=0, last_error=NULL, updated=? WHERE wallet=?",
                            (newest, self.clock(), wallet))
            self.db.commit()
        return out

    def _seen(self, wallet, sig):
        return self.db.execute("SELECT 1 FROM tracker_seen WHERE sig=? AND wallet=?", (sig, wallet)).fetchone()

    def handle_signature(self, wallet, sig, source="ws", retries=4, delay=0.5):
        """Tek imzayı işler. WebSocket ve yoklama aynı yolu kullanır; aynı imza bir kez işlenir.
        İşlem henüz okunamazsa 'görüldü' işaretlenmez, yoklama sonra tamamlar."""
        with self.lock:
            if self._seen(wallet, sig): return None
        tx = None
        for i in range(retries):
            tx = self.client.call("getTransaction", [sig, {"encoding": "jsonParsed",
                    "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
            if isinstance(tx, dict): break
            if i + 1 < retries: self.sleep(delay)
        if not isinstance(tx, dict): return None
        with self.lock:
            if self._seen(wallet, sig): return None
            self.db.execute("INSERT OR IGNORE INTO tracker_seen VALUES(?,?)", (sig, wallet))
            rec = decode_swap(tx, wallet)
            if rec.get("event_type") not in ("BUY", "SELL"):
                self.db.commit(); return None
            bt = tx.get("blockTime") or 0
            age = max(0.0, self.clock() - bt) if bt else 1e9
            r = self.paper.handle_signal(f"{wallet}:{sig}", wallet, rec["token_mint"],
                    rec["event_type"].lower(), 1.0, 0.0, age)   # fiyat/likidite bilinmiyor -> engellenir
            self.db.execute("""INSERT INTO tracker_signals(ts,wallet,sig,side,token,token_delta,quote,
                block_time,latency_s,decision,reason,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.clock(), wallet, sig, rec["event_type"], rec["token_mint"], str(rec["token_delta_raw"]),
                 rec.get("quote_mint") or "SOL", bt, age, r["decision"], r["reason"], source))
            self.db.commit()
            return dict(wallet=wallet, sig=sig, side=rec["event_type"], token=rec["token_mint"],
                        latency_s=age, decision=r["decision"], reason=r["reason"], source=source)

    def poll_all(self):
        report = {}
        self.last_poll_rows = []
        for w in self.active_wallets():
            try:
                rows = self.poll_wallet(w)
                self.last_poll_rows.extend(rows)
                report[w] = len(rows)
            except Exception as e:                      # hata izolasyonu: diğer cüzdanlar etkilenmez
                with self.lock:
                    self.db.rollback()
                    self.db.execute("""UPDATE tracker_wallets SET errors=errors+1, last_error=?,
                        quarantined=CASE WHEN errors+1>=? THEN 1 ELSE 0 END, updated=? WHERE wallet=?""",
                        (type(e).__name__ + ": " + str(e)[:120], QUARANTINE_AFTER, self.clock(), w))
                    self.db.commit()
                report[w] = "hata"
        return report

    def status(self):
      with self.lock:
        return [dict(zip(("wallet", "errors", "quarantined", "last_error"), r)) for r in
                self.db.execute("SELECT wallet, errors, quarantined, last_error FROM tracker_wallets")]

    def signals(self, limit=50):
      with self.lock:
        cols = ("ts", "wallet", "sig", "side", "token", "latency_s", "decision", "reason")
        return [dict(zip(cols, r)) for r in self.db.execute(
            "SELECT ts,wallet,sig,side,token,latency_s,decision,reason FROM tracker_signals ORDER BY id DESC LIMIT ?", (limit,))]

    def active_wallets(self):
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT wallet FROM tracker_wallets WHERE quarantined=0")]

    def latency_stats(self):
        with self.lock:
            out = {}
            for src in ("ws", "poll"):
                lat = sorted(r[0] for r in self.db.execute(
                    "SELECT latency_s FROM tracker_signals WHERE source=? AND latency_s < 1e8", (src,)))
                if lat:
                    q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))]
                    out[src] = dict(n=len(lat), p50=q(.5), p95=q(.95), p99=q(.99))
            return out

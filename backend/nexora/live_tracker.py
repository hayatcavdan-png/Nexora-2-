"""Canlı cüzdan takibi (polling, salt okunur).
- Her cüzdan bağımsız işlenir; bir cüzdanın hatası diğerlerini durdurmaz.
- Üst üste hata veren cüzdan karantinaya alınır.
- Son görülen imza SQLite'ta tutulur (yeniden başlatmada güvenli devam).
- İlk çalıştırmada geçmiş taranmaz: yalnızca bundan sonraki işlemler izlenir.
- Aynı imza iki kez işlenmez (paper motoru event_id ile de korur).
Token güvenliği, fiyat ve likidite henüz bilinmediği için sinyaller paper motorunda
REDDEDİLİR (BİLİNMİYOR = ENGELLE). Bu aşama yalnızca algılamayı ve gecikmeyi ölçer."""
import sqlite3, time
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
    def __init__(self, client, paper, db_path, wallets, clock=time.time):
        self.client, self.paper, self.clock = client, paper, clock
        self.db = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self.db.executescript(SCHEMA)
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
        row = self.db.execute("SELECT last_sig FROM tracker_wallets WHERE wallet=?", (wallet,)).fetchone()
        last = row[0] if row else None
        sigs = self._signatures(wallet, until=last)
        if not sigs: return []
        newest = sigs[0]["signature"]
        if last is None:  # ilk çalıştırma: geçmişi işleme, yalnızca işaret koy
            self.db.execute("UPDATE tracker_wallets SET last_sig=?, updated=? WHERE wallet=?", (newest, self.clock(), wallet))
            self.db.commit(); return []
        out = []
        for s in reversed(sigs):                       # eskiden yeniye
            sig = s["signature"]
            if s.get("err") is not None: continue
            if self.db.execute("SELECT 1 FROM tracker_seen WHERE sig=? AND wallet=?", (sig, wallet)).fetchone(): continue
            tx = self.client.call("getTransaction", [sig, {"encoding": "jsonParsed",
                    "commitment": "confirmed", "maxSupportedTransactionVersion": 0}])
            self.db.execute("INSERT OR IGNORE INTO tracker_seen VALUES(?,?)", (sig, wallet))
            if not isinstance(tx, dict): continue
            rec = decode_swap(tx, wallet)
            if rec.get("event_type") not in ("BUY", "SELL"): continue
            bt = tx.get("blockTime") or 0
            age = max(0.0, self.clock() - bt) if bt else 1e9
            r = self.paper.handle_signal(f"{wallet}:{sig}", wallet, rec["token_mint"],
                    rec["event_type"].lower(), 1.0, 0.0, age)   # fiyat/likidite bilinmiyor -> engellenir
            self.db.execute("""INSERT INTO tracker_signals(ts,wallet,sig,side,token,token_delta,quote,
                block_time,latency_s,decision,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (self.clock(), wallet, sig, rec["event_type"], rec["token_mint"], str(rec["token_delta_raw"]),
                 rec.get("quote_mint") or "SOL", bt, age, r["decision"], r["reason"]))
            out.append(rec)
        self.db.execute("UPDATE tracker_wallets SET last_sig=?, errors=0, last_error=NULL, updated=? WHERE wallet=?",
                        (newest, self.clock(), wallet))
        self.db.commit()
        return out

    def poll_all(self):
        report = {}
        rows = self.db.execute("SELECT wallet FROM tracker_wallets WHERE quarantined=0").fetchall()
        for (w,) in rows:
            try:
                report[w] = len(self.poll_wallet(w))
            except Exception as e:                      # hata izolasyonu
                self.db.rollback()
                self.db.execute("""UPDATE tracker_wallets SET errors=errors+1, last_error=?,
                    quarantined=CASE WHEN errors+1>=? THEN 1 ELSE 0 END, updated=? WHERE wallet=?""",
                    (type(e).__name__ + ": " + str(e)[:120], QUARANTINE_AFTER, self.clock(), w))
                self.db.commit()
                report[w] = "hata"
        return report

    def status(self):
        return [dict(zip(("wallet", "errors", "quarantined", "last_error"), r)) for r in
                self.db.execute("SELECT wallet, errors, quarantined, last_error FROM tracker_wallets")]

    def signals(self, limit=50):
        cols = ("ts", "wallet", "sig", "side", "token", "latency_s", "decision", "reason")
        return [dict(zip(cols, r)) for r in self.db.execute(
            "SELECT ts,wallet,sig,side,token,latency_s,decision,reason FROM tracker_signals ORDER BY id DESC LIMIT ?", (limit,))]

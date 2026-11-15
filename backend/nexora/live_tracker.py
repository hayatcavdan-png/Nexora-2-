"""Canlı cüzdan takibi (polling, salt okunur).
- Her cüzdan bağımsız işlenir; bir cüzdanın hatası diğerlerini durdurmaz.
- Üst üste hata veren cüzdan karantinaya alınır.
- Son görülen imza SQLite'ta tutulur (yeniden başlatmada güvenli devam).
- İlk çalıştırmada geçmiş taranmaz: yalnızca bundan sonraki işlemler izlenir.
- Aynı imza iki kez işlenmez (paper motoru event_id ile de korur).
Token güvenliği, fiyat ve likidite henüz bilinmediği için sinyaller paper motorunda
REDDEDİLİR (BİLİNMİYOR = ENGELLE). Bu aşama yalnızca algılamayı ve gecikmeyi ölçer."""
import sqlite3, threading, time
from nexora.gizle import gizle
from collections import defaultdict, deque
from nexora.swap_decoder import decode_swap

QUARANTINE_AFTER = 5
RATE_WINDOW_S = 600       # 10 dakika
RATE_MAX = 30             # 10 dakikada bundan fazla işlem: yüksek frekans (bot) -> takip durur, API harcanmaz
QUARANTINE_ERRORS, QUARANTINE_BOT = 1, 2
TX_VERSION = 1      # Solana transaction v1 (Eylül 2026). 0 verilirse v1 işlemlerde RPC -32015 döner.
SCHEMA = """
CREATE TABLE IF NOT EXISTS tracker_wallets(wallet TEXT PRIMARY KEY, last_sig TEXT,
  errors INTEGER DEFAULT 0, quarantined INTEGER DEFAULT 0, last_error TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS tracker_seen(sig TEXT, wallet TEXT, PRIMARY KEY(sig, wallet));
CREATE TABLE IF NOT EXISTS tracker_failed(sig TEXT, wallet TEXT, error TEXT, ts REAL, PRIMARY KEY(sig, wallet));
CREATE TABLE IF NOT EXISTS tracker_signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
  wallet TEXT, sig TEXT, side TEXT, token TEXT, token_delta TEXT, quote TEXT,
  block_time INTEGER, latency_s REAL, decision TEXT, reason TEXT);
"""

def latency_from_db(db):
    """Kaynak (ws/poll) başına P50/P95/P99 algılama gecikmesi."""
    out = {}
    for src in ("ws", "poll"):
        lat = sorted(r[0] for r in db.execute(
            "SELECT latency_s FROM tracker_signals WHERE source=? AND latency_s < 1e8", (src,)))
        if lat:
            q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))]
            out[src] = dict(n=len(lat), p50=q(.5), p95=q(.95), p99=q(.99))
    return out

class LiveTracker:
    def __init__(self, client, paper, db_path, wallets, clock=time.time, sleep=time.sleep, decider=None):
        self.client, self.paper, self.clock, self.sleep = client, paper, clock, sleep
        self.decider = decider
        self.lock = threading.RLock()
        self.wallets = {w.strip() for w in wallets}
        self.recent = defaultdict(deque)
        self.flagged = []
        self.db = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(tracker_signals)")}
        if "source" not in cols:                       # eski şemadan güvenli geçiş
            self.db.execute("ALTER TABLE tracker_signals ADD COLUMN source TEXT DEFAULT 'poll'")
        if "kesinlik" not in cols:
            self.db.execute("ALTER TABLE tracker_signals ADD COLUMN kesinlik TEXT")
            self.db.execute("ALTER TABLE tracker_signals ADD COLUMN kesinlik_ts REAL")
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

    def _rate_ok(self, wallet):
        """Cüzdan başına kaynak limiti. Aşılırsa cüzdan 'bot' olarak durdurulur (kilit içinde çağrılır)."""
        row = self.db.execute("SELECT quarantined FROM tracker_wallets WHERE wallet=?", (wallet,)).fetchone()
        if row and row[0]: return False
        now, q = self.clock(), self.recent[wallet]
        while q and now - q[0] > RATE_WINDOW_S: q.popleft()
        if len(q) >= RATE_MAX:
            self.db.execute("UPDATE tracker_wallets SET quarantined=?, last_error=?, updated=? WHERE wallet=?",
                (QUARANTINE_BOT, f"yüksek frekans: {RATE_WINDOW_S // 60} dk içinde {RATE_MAX}+ işlem (bot olabilir)", now, wallet))
            self.db.commit(); q.clear()
            self.flagged.append(wallet)
            return False
        q.append(now)
        return True

    flagged = None

    def _seen(self, wallet, sig):
        return self.db.execute("SELECT 1 FROM tracker_seen WHERE sig=? AND wallet=?", (sig, wallet)).fetchone()

    def handle_signature(self, wallet, sig, source="ws", retries=4, delay=0.5):
        """Tek imzayı işler. WebSocket ve yoklama aynı yolu kullanır; aynı imza bir kez işlenir.
        İşlem henüz okunamazsa 'görüldü' işaretlenmez, yoklama sonra tamamlar."""
        with self.lock:
            if self._seen(wallet, sig): return None
            if not self._rate_ok(wallet): return None
        tx = None
        for i in range(retries):
            try:
                tx = self._get_tx(sig)
            except Exception as e:
                if getattr(e, "rpc_code", None) is None:
                    raise                               # bağlantı/HTTP: geçici, cüzdan düzeyinde sayılır
                with self.lock:                         # sunucu bu işlemi reddetti: kaydet, cüzdanı durdurma
                    self.db.execute("INSERT OR IGNORE INTO tracker_seen VALUES(?,?)", (sig, wallet))
                    self.db.execute("INSERT OR REPLACE INTO tracker_failed VALUES(?,?,?,?)",
                                    (sig, wallet, f"RPC {e.rpc_code}", self.clock()))
                    self.db.commit()
                return None
            if isinstance(tx, dict): break
            if i + 1 < retries: self.sleep(delay)
        if not isinstance(tx, dict): return None
        with self.lock:
            if self._seen(wallet, sig): return None
            self.db.execute("INSERT OR IGNORE INTO tracker_seen VALUES(?,?)", (sig, wallet))
            self.db.commit()
        rec = decode_swap(tx, wallet)
        if rec.get("event_type") not in ("BUY", "SELL"): return None
        bt = tx.get("blockTime") or 0
        age = max(0.0, self.clock() - bt) if bt else 1e9      # algılama gecikmesi (karar öncesi)
        event_id, side = f"{wallet}:{sig}", rec["event_type"].lower()
        if self.decider:                                       # gerçek teklifle paper karar (ağ: kilit dışında)
            r = self.decider.decide(event_id, wallet, rec["token_mint"], side, age)
        else:                                                  # fiyat/likidite bilinmiyor -> engellenir
            r = self.paper.handle_signal(event_id, wallet, rec["token_mint"], side, 1.0, 0.0, age)
        with self.lock:
            self.db.execute("""INSERT INTO tracker_signals(ts,wallet,sig,side,token,token_delta,quote,
                block_time,latency_s,decision,reason,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self.clock(), wallet, sig, rec["event_type"], rec["token_mint"], str(rec["token_delta_raw"]),
                 rec.get("quote_mint") or "SOL", bt, age, r["decision"], r["reason"], source))
            self.db.commit()
        return dict(wallet=wallet, sig=sig, side=rec["event_type"], token=rec["token_mint"],
                    latency_s=age, decision=r["decision"], reason=r["reason"], source=source)

    # --- N2: erken sinyal (confirmed) ile kesinleşmiş işlemi ayırma -----------------------------------
    # Sinyaller hız için 'confirmed' seviyesinde işlenir. Burada her sinyalin işlemi sonradan zincirde
    # yeniden sorulur: 'kesin' (finalized), 'hatali' (zincire girdi ama başarısız), 'dusuruldu' (DUSURME_SN
    # sonra hâlâ bulunamadı: çatallanmada düşmüş say). Paper defterini değiştirmez; yalnızca ölçer ve uyarır.
    KESINLIK_BEKLE_SN = 30
    DUSURME_SN = 150

    def verify_finality(self, now=None, limit=100):
        now = now if now is not None else self.clock()
        with self.lock:
            rows = self.db.execute("""SELECT id, sig, ts, wallet, token, side, decision FROM tracker_signals
                WHERE kesinlik IS NULL AND ts <= ? ORDER BY id LIMIT ?""", (now - self.KESINLIK_BEKLE_SN, limit)).fetchall()
        if not rows: return dict(kesin=0, hatali=0, dusuruldu=0, bekliyor=0, uyarilar=[])
        sigs = list(dict.fromkeys(r[1] for r in rows))
        res = self.client.call("getSignatureStatuses", [sigs, {"searchTransactionHistory": True}])
        vals = res.get("value") if isinstance(res, dict) else None
        if not isinstance(vals, list) or len(vals) != len(sigs): raise ValueError("imza durumu yanıtı geçersiz")
        durum = dict(zip(sigs, vals))
        say = dict(kesin=0, hatali=0, dusuruldu=0, bekliyor=0); uyarilar = []
        with self.lock:
            for rid, sig, ts, wallet, token, side, decision in rows:
                st = durum.get(sig)
                if isinstance(st, dict) and st.get("err") is not None: k = "hatali"
                elif isinstance(st, dict) and st.get("confirmationStatus") == "finalized": k = "kesin"
                elif st is None and now - ts >= self.DUSURME_SN: k = "dusuruldu"
                else: say["bekliyor"] += 1; continue
                say[k] += 1
                self.db.execute("UPDATE tracker_signals SET kesinlik=?, kesinlik_ts=? WHERE id=?", (k, now, rid))
                if k != "kesin" and decision == "KOPYALANDI":
                    uyarilar.append(dict(sig=sig, wallet=wallet, token=token, side=side, kesinlik=k))
            self.db.commit()
        say["uyarilar"] = uyarilar
        return say

    def kesinlik_ozeti(self):
        return kesinlik_from_db(self.db)

    def _get_tx(self, sig):
        return self.client.call("getTransaction", [sig, {"encoding": "jsonParsed",
                    "commitment": "confirmed", "maxSupportedTransactionVersion": TX_VERSION}])

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
                        (gizle(type(e).__name__ + ": " + str(e))[:140], QUARANTINE_AFTER, self.clock(), w))
                    self.db.commit()
                report[w] = "hata"
        return report

    def status(self):
      with self.lock:
        return [dict(zip(("wallet", "errors", "quarantined", "last_error"), r)) for r in
                self.db.execute("SELECT wallet, errors, quarantined, last_error FROM tracker_wallets")
                if r[0] in self.wallets]

    def bot_wallets(self):
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT wallet FROM tracker_wallets WHERE quarantined=?",
                                                    (QUARANTINE_BOT,)) if r[0] in self.wallets]

    def clear_bot_flag(self, wallet):
        with self.lock:
            self.db.execute("UPDATE tracker_wallets SET quarantined=0, errors=0, last_error=NULL WHERE wallet=?", (wallet,))
            self.db.commit()

    def signals(self, limit=50):
      with self.lock:
        cols = ("ts", "wallet", "sig", "side", "token", "latency_s", "decision", "reason")
        return [dict(zip(cols, r)) for r in self.db.execute(
            "SELECT ts,wallet,sig,side,token,latency_s,decision,reason FROM tracker_signals ORDER BY id DESC LIMIT ?", (limit,))]

    def active_wallets(self):
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT wallet FROM tracker_wallets WHERE quarantined=0")
                    if r[0] in self.wallets]          # wallets.txt'ten çıkarılan cüzdan izlenmez

    def latency_stats(self):
        with self.lock:
            return latency_from_db(self.db)

    def reset_quarantine(self):
        """Yeniden başlatmada karantinadaki cüzdanlara yeni şans verir; sayısını döndürür."""
        with self.lock:
            n = self.db.execute("UPDATE tracker_wallets SET quarantined=0, errors=0 WHERE quarantined=?",
                                (QUARANTINE_ERRORS,)).rowcount        # bot işaretlileri (2) kalıcıdır
            self.db.commit()
            return n

    def failed_count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM tracker_failed").fetchone()[0]


def kesinlik_from_db(db):
    """Sinyallerin zincir kesinliği dağılımı (eski veritabanında sütun yoksa boş)."""
    try:
        rows = db.execute("SELECT COALESCE(kesinlik,'bekliyor'), decision, COUNT(*) FROM tracker_signals GROUP BY 1, 2").fetchall()
    except sqlite3.OperationalError:
        return {}
    out = dict(kesin=0, hatali=0, dusuruldu=0, bekliyor=0, kopyalanan_sorunlu=0)
    for k, d, n in rows:
        out[k] = out.get(k, 0) + n
        if k in ("hatali", "dusuruldu") and d == "KOPYALANDI": out["kopyalanan_sorunlu"] += n
    return out

"""Birden çok iş parçacığının paylaştığı SQLite bağlantısı için kilitli sarmalayıcı."""


class _Sonuc:
    """Kilit altında tamamen okunmuş sorgu sonucu (imleç gibi kullanılır: fetchone, fetchall, döngü, lastrowid, rowcount)."""
    __slots__ = ("_satirlar", "_i", "lastrowid", "rowcount", "description")
    def __init__(self, cur):
        self._satirlar = cur.fetchall() if cur.description else []
        self._i = 0
        self.lastrowid, self.rowcount, self.description = cur.lastrowid, cur.rowcount, cur.description
    def fetchone(self):
        if self._i >= len(self._satirlar): return None
        self._i += 1; return self._satirlar[self._i - 1]
    def fetchall(self):
        kalan = self._satirlar[self._i:]; self._i = len(self._satirlar); return kalan
    def __iter__(self):
        while self._i < len(self._satirlar):
            self._i += 1; yield self._satirlar[self._i - 1]


class KilitliBaglanti:
    """24.11: sunucu çok iş parçacıklı (ThreadingHTTPServer) ve tek bağlantıyı paylaşıyordu. Kilitsiz okumalar
    (cash, killed, portfolio, trades...) eşzamanlı isteklerde aynı hazır ifadeyi çakıştırıp 'bad parameter or other
    API misuse' ve float(None) hatası veriyordu. Artık her ifade, satırları okunana kadar aynı yeniden girilebilir kilit altında."""
    def __init__(self, db, kilit):
        self._db, self._kilit = db, kilit
    def execute(self, sql, params=()):
        with self._kilit: return _Sonuc(self._db.execute(sql, params))
    def executescript(self, sql):
        with self._kilit: return self._db.executescript(sql)
    def commit(self):
        with self._kilit: self._db.commit()
    def rollback(self):
        with self._kilit: self._db.rollback()
    def close(self):
        with self._kilit: self._db.close()
    def __getattr__(self, ad):
        return getattr(self._db, ad)
    def __setattr__(self, ad, deger):
        if ad in ("_db", "_kilit"): object.__setattr__(self, ad, deger)
        else: setattr(self._db, ad, deger)

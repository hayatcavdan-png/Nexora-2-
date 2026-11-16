"""Bildirim sinyalleri (N32), 1. sürüm: borsada LİSTELENMEYEN token sinyalleri için kullanıcıya bildirim.

Kapsam (bilinçli olarak dar):
  - Yalnızca bildirim kaydı üretir. Emir, işlem, anahtar ve ağ çağrısı YOK; "elle değerlendir" bilgisi verir.
  - Kaynak: tracker_signals (öncü cüzdanların alımları) ve borsa_liste.json (dört borsada listeli Solana tokenleri).
  - Bir sinyal en fazla bir kez bildirilir (olay anahtarı tekil). Bildirimler kendi veritabanında tutulur (nexora_bildirim.db).
Kullanıcıya gösterilen metin, sinyalin ne olduğunu ve ne olmadığını söyler: "al" önerisi değildir."""
import sqlite3, time

ALIM = "BUY"


def bildirim_metni(sinyal, token_adi):
    return (f"{sinyal['wallet'][:4]}…{sinyal['wallet'][-4:]} cüzdanı {token_adi} tokenini aldı. "
            "Bu token dört borsada listeli değil; yalnızca bilgi amaçlıdır. Kendi kararınızla, kendi zincir üstü cüzdanınızdan "
            "değerlendirin. Uygulama bu token için işlem açmaz.")


def uret(sinyaller, listeli_mintler):
    """Yeni bildirimler: [dict(olay, tur, token, wallet, ts, metin)]. `listeli_mintler`: borsada listeli mint kümesi.
    Yalnızca ALIM sinyalleri ve listeli OLMAYAN tokenler bildirilir."""
    out = []
    for s in sinyaller:
        if (s.get("side") or "").upper() != ALIM: continue
        mint = s.get("token")
        if not mint or mint in listeli_mintler: continue
        olay = f"alim:{s.get('sig') or s.get('id')}"          # tekilleştirme: veritabanındaki UNIQUE kısıtı (yeniden başlatmaya dayanıklı)
        ad = (s.get("sembol") or mint[:6] + "…" + mint[-4:])
        out.append(dict(olay=olay, tur="borsada_yok", token=mint, wallet=s.get("wallet", ""), ts=s.get("ts") or time.time(),
                        metin=bildirim_metni(s, ad)))
    return out


class Bildirim:
    def __init__(self, yol="nexora_bildirim.db"):
        self.db = sqlite3.connect(yol, timeout=10)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS bildirim(id INTEGER PRIMARY KEY AUTOINCREMENT, olay TEXT UNIQUE NOT NULL, tur TEXT NOT NULL,
            token TEXT, wallet TEXT, ts REAL NOT NULL, metin TEXT NOT NULL, okundu INTEGER DEFAULT 0);
        """)

    def ekle(self, liste):
        n = 0
        for b in liste:
            cur = self.db.execute("INSERT OR IGNORE INTO bildirim(olay,tur,token,wallet,ts,metin) VALUES(?,?,?,?,?,?)",
                                  (b["olay"], b["tur"], b["token"], b["wallet"], b["ts"], b["metin"]))
            n += cur.rowcount
        self.db.commit()
        return n

    def son(self, limit=20):
        return [dict(id=r[0], tur=r[1], token=r[2], wallet=r[3], ts=r[4], metin=r[5], okundu=bool(r[6]))
                for r in self.db.execute("SELECT id, tur, token, wallet, ts, metin, okundu FROM bildirim ORDER BY id DESC LIMIT ?", (limit,))]


def islem_bildirimleri(satirlar, ekosistem="solana"):
    """Paper işlemlerden bildirim: satirlar = [(id, ts, side, token, pnl, decision, wallet)]. Yalnızca KOPYALANDI işlemler."""
    out = []
    for i, ts, side, token, pnl, decision, wallet in satirlar:
        if decision != "KOPYALANDI": continue
        kisa = (token or "")[:6] + "…" + (token or "")[-4:]
        if (side or "").lower() == "buy":
            metin = f"[{ekosistem}] Paper alım açıldı: {kisa}. Gerçek para kullanılmadı."
        else:
            metin = f"[{ekosistem}] Paper satım kapandı: {kisa}, K/Z {pnl:+.2f} USDC. Gerçek para kullanılmadı."
        out.append(dict(olay=f"islem:{ekosistem}:{i}", tur="islem", token=token or "", wallet=wallet or "", ts=ts or time.time(), metin=metin))
    return out


def gunluk_zarar_bildirimi(ekosistem, gun, gun_basi, equity, esik):
    """Günlük zarar sınırı aşıldıysa (gün başına göre düşüş >= esik) o gün için EN FAZLA bir bildirim. Boş liste: aşılmadı."""
    if not gun_basi or gun_basi <= 0: return []
    dusus = (gun_basi - equity) / gun_basi
    if dusus < esik: return []
    return [dict(olay=f"gunluk:{ekosistem}:{gun}", tur="gunluk_zarar", token="", wallet="", ts=time.time(),
                 metin=f"[{ekosistem}] Günlük zarar sınırı aşıldı (%{dusus * 100:.1f} ≥ %{esik * 100:.0f}). "
                       "Bugün yeni paper alım durduruldu. Gerçek para kullanılmadı.")]

"""Token güvenliği (N5, ilk sürüm). Mint hesabı Helius'tan salt okunur okunur.
Karar: UYGUN / BİLİNMİYOR (engelle) / REDDEDİLDİ. Bilinmeyen durum güvenli sayılmaz."""
import threading

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SAFE_2022_EXT = {"metadataPointer", "tokenMetadata"}           # yalnızca ad/sembol bilgisi
DANGER_2022_EXT = {"transferFeeConfig", "transferHook", "permanentDelegate", "nonTransferable",
                   "defaultAccountState", "pausableConfig", "confidentialTransferMint"}

def evaluate(account):
    """getAccountInfo(jsonParsed) 'value' nesnesinden karar üretir."""
    if not isinstance(account, dict):
        return dict(verdict="BİLİNMİYOR", reasons=["mint hesabı bulunamadı"], decimals=None)
    owner = account.get("owner")
    data = account.get("data")
    info = ((data or {}).get("parsed") or {}).get("info") if isinstance(data, dict) else None
    if owner not in (TOKEN_PROGRAM, TOKEN_2022):
        return dict(verdict="REDDEDİLDİ", reasons=["bilinmeyen token programı"], decimals=None)
    if not isinstance(info, dict) or not isinstance(info.get("decimals"), int):
        return dict(verdict="BİLİNMİYOR", reasons=["mint verisi okunamadı"], decimals=None)
    reasons, verdict = [], "UYGUN"
    if info.get("freezeAuthority"): reasons.append("dondurma yetkisi açık"); verdict = "REDDEDİLDİ"
    if info.get("mintAuthority"): reasons.append("yeni basım yetkisi açık"); verdict = "REDDEDİLDİ"
    if owner == TOKEN_2022:
        exts = {e.get("extension") for e in info.get("extensions") or [] if isinstance(e, dict)}
        bad = sorted(exts & DANGER_2022_EXT)
        unknown = sorted(exts - SAFE_2022_EXT - DANGER_2022_EXT)
        if bad: reasons.append("riskli Token-2022 özelliği: " + ", ".join(bad)); verdict = "REDDEDİLDİ"
        elif unknown and verdict == "UYGUN":
            reasons.append("bilinmeyen Token-2022 özelliği: " + ", ".join(unknown)); verdict = "BİLİNMİYOR"
    return dict(verdict=verdict, reasons=reasons or ["kontroller geçti"], decimals=info["decimals"])

class TokenSafety:
    def __init__(self, client):
        self.client, self.cache, self.lock = client, {}, threading.Lock()

    def check(self, mint):
        with self.lock:
            if mint in self.cache: return self.cache[mint]
        try:
            res = self.client.call("getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}])
            value = res.get("value") if isinstance(res, dict) else None
            out = evaluate(value)
        except Exception as e:
            return dict(verdict="BİLİNMİYOR", reasons=[f"kontrol başarısız ({type(e).__name__})"], decimals=None)
        if out["verdict"] == "UYGUN":            # yetkiler geri verilemez; yalnızca olumlu sonuç önbelleğe alınır
            with self.lock: self.cache[mint] = out
        return out

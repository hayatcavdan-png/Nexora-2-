"""Platform 2: dört borsada (Binance, OKX, KuCoin, MEXC) listeli Solana token'larının listesini oluşturur/yeniler.
  python borsa_liste.py      -> borsa_tokenleri.json  (CoinGecko herkese açık uçları, birkaç dakika sürer)"""
import sys
from nexora import borsa_liste

if __name__ == "__main__":
    try:
        v = borsa_liste.olustur()
    except Exception as e:
        sys.exit(f"Liste oluşturulamadı: {type(e).__name__}: {str(e)[:160]}")
    print(f"{v['token']} listeli Solana token'ı: " + ", ".join(f"{b} {n}" for b, n in v["borsa_basina"].items()))
    if v["hatalar"]: print("Okunamayan: " + "; ".join(f"{b} ({h})" for b, h in v["hatalar"].items()))

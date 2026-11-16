"""Kanıt karnesi (salt okunur): hangi kaynak gerçekten kazandırıyor? Haftalık zamanlayıcı raporu kanit_raporlari/ altına yazar.
  python3 kanit_raporu.py"""
import json, os, time
from nexora.kanit import karne, metin

if __name__ == "__main__":
    k = karne()
    t = metin(k); print(t)
    os.makedirs("kanit_raporlari", exist_ok=True)
    ad = time.strftime("kanit_raporlari/%Y-%m-%d")
    open(ad + ".txt", "w").write(t + "\n")
    json.dump(k, open(ad + ".json", "w"), ensure_ascii=False)

"""Salt-okunur çalışma koruması: gerçek işlem modu açıksa ya da çalışma modu tanınmıyorsa durur."""
import os

def require_safe_runtime():
    if os.getenv("NEXORA_REAL_TRADING") == "1":
        raise RuntimeError("Gerçek işlem modu açık: salt-okunur istemci çalışmaz")
    if os.getenv("NEXORA_RUNTIME", "paper") not in ("dev", "paper", "test"):
        raise RuntimeError("Bilinmeyen çalışma modu")

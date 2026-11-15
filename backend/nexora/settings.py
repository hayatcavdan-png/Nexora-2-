"""Ayarlar ortam değişkenlerinden okunur. Anahtar koda/loga yazılmaz."""
import os

_key = os.getenv("HELIUS_API_KEY", "")
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL") or (
    f"https://mainnet.helius-rpc.com/?api-key={_key}" if _key else "")
RPC_TIMEOUT_SECONDS = float(os.getenv("RPC_TIMEOUT_SECONDS", "15"))
HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "3"))
HTTP_BACKOFF_SECONDS = float(os.getenv("HTTP_BACKOFF_SECONDS", "1.0"))

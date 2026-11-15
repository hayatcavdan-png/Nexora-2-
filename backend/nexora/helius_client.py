import time
import requests

from nexora import settings
from nexora.runtime_guard import require_safe_runtime


class HeliusRPCError(RuntimeError):
    pass


class HeliusClient:
    READ_ONLY_METHODS = {
        "getHealth",
        "getVersion",
        "getSlot",
        "getBalance",
        "getAccountInfo",
        "getMultipleAccounts",
        "getSignaturesForAddress",
        "getTransactionsForAddress",
        "getTransaction",
        "getBlock",
    }

    def __init__(self, rpc_url=None, timeout=None, max_retries=None):
        self.rpc_url = rpc_url or settings.SOLANA_RPC_URL
        self.timeout = (
            settings.RPC_TIMEOUT_SECONDS if timeout is None else timeout
        )
        self.max_retries = (
            settings.HTTP_MAX_RETRIES
            if max_retries is None
            else max_retries
        )

        if (
            not isinstance(self.rpc_url, str)
            or not self.rpc_url.startswith(
                "https://mainnet.helius-rpc.com/"
            )
        ):
            raise ValueError("Geçersiz Helius Mainnet RPC adresi")

        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or self.timeout <= 0
        ):
            raise ValueError("timeout pozitif bir sayı olmalı")

        if (
            isinstance(self.max_retries, bool)
            or not isinstance(self.max_retries, int)
            or self.max_retries < 0
        ):
            raise ValueError("max_retries negatif olmayan tam sayı olmalı")

        self.session = requests.Session()
        self.request_id = 0

    def call(self, method, params=None):
        require_safe_runtime()

        if method not in self.READ_ONLY_METHODS:
            raise ValueError("Bu RPC metodu izin verilen salt-okunur listede değil")

        if params is None:
            params = []

        if not isinstance(params, list):
            raise ValueError("RPC params liste olmalı")

        self.request_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    self.rpc_url,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_retries:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = float(retry_after)
                        except (TypeError, ValueError):
                            delay = settings.HTTP_BACKOFF_SECONDS * (
                                2 ** attempt
                            )

                        time.sleep(min(max(delay, 0), 30))
                        continue

                response.raise_for_status()
                try:
                    data = response.json()
                except ValueError:
                    raise HeliusRPCError("RPC JSON yaniti gecersiz") from None

                if not isinstance(data, dict):
                    raise HeliusRPCError("RPC yanıt formatı geçersiz")

                if data.get("jsonrpc") != "2.0":
                    raise HeliusRPCError("RPC surumu gecersiz")

                response_id = data.get("id")
                if (
                    isinstance(response_id, bool)
                    or not isinstance(response_id, int)
                    or response_id != payload["id"]
                ):
                    raise HeliusRPCError("RPC yanit kimligi gecersiz")

                if data.get("error") is not None:
                    error = data["error"]
                    if not isinstance(error, dict):
                        raise HeliusRPCError("RPC hata formatı geçersiz")

                    code = error.get("code", "bilinmiyor")
                    raise HeliusRPCError(f"RPC hatası: {code}")

                if "result" not in data:
                    raise HeliusRPCError("RPC yanıtında result alanı yok")

                return data["result"]

            except requests.RequestException as error:
                response = getattr(error, "response", None)
                status = getattr(response, "status_code", None)
                permanent_http_error = (
                    isinstance(error, requests.HTTPError)
                    and isinstance(status, int)
                    and status != 429
                    and 400 <= status < 500
                )
                if permanent_http_error or attempt >= self.max_retries:
                    response = getattr(error, "response", None)
                    status = getattr(response, "status_code", None)

                    if isinstance(status, int):
                        message = f"Helius HTTP hatası: {status}"
                    else:
                        message = "Helius bağlantı hatası"

                    raise HeliusRPCError(message) from None

                time.sleep(
                    settings.HTTP_BACKOFF_SECONDS * (2 ** attempt)
                )

        raise HeliusRPCError("RPC isteği tamamlanamadı")

    def get_health(self):
        return self.call("getHealth")

    def get_version(self):
        return self.call("getVersion")

    def get_transactions_for_address(
        self,
        address,
        limit=100,
        pagination_token=None,
        commitment="finalized",
    ):
        if not isinstance(address, str) or not address.strip():
            raise ValueError("Cüzdan adresi geçersiz")

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit tam sayı olmalı")

        if not 1 <= limit <= 1000:
            raise ValueError("limit 1 ile 1000 arasında olmalı")

        if commitment not in {"finalized", "confirmed"}:
            raise ValueError("commitment geçersiz")

        options = {
            "limit": limit,
            "commitment": commitment,
        }

        if pagination_token is not None:
            if not isinstance(pagination_token, str) or not pagination_token:
                raise ValueError("pagination_token geçersiz")

            options["paginationToken"] = pagination_token

        return self.call(
            "getTransactionsForAddress",
            [address.strip(), options],
        )

    def get_transaction(self, signature, commitment="finalized"):
        """İşlem imzasının ayrıntılarını salt-okunur olarak getirir."""
        if not isinstance(signature, str) or not signature.strip():
            raise ValueError("İşlem imzası geçersiz")

        if commitment not in {"finalized", "confirmed"}:
            raise ValueError("commitment geçersiz")

        options = {
            "encoding": "jsonParsed",
            "commitment": commitment,
            "maxSupportedTransactionVersion": 1,
        }

        return self.call(
            "getTransaction",
            [signature.strip(), options],
        )

    def get_block(self, slot, commitment="finalized"):
        """Blok işlemlerini sıraları korunarak salt-okunur getirir."""
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise ValueError("slot sıfır veya pozitif tam sayı olmalı")

        if commitment not in {"finalized", "confirmed"}:
            raise ValueError("commitment geçersiz")

        options = {
            "encoding": "json",
            "transactionDetails": "full",
            "rewards": False,
            "commitment": commitment,
            "maxSupportedTransactionVersion": 1,
        }

        return self.call("getBlock", [slot, options])

    def close(self):
        self.session.close()

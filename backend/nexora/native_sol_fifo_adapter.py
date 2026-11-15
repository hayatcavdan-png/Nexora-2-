"""Read-only native SOL to FIFO event conversion."""

NATIVE_SOL = "NATIVE_SOL"


def native_sol_to_fifo_event(wallet, record, event_index=0):
    """Convert a native SOL swap classification into a partial FIFO event."""

    if not isinstance(wallet, str) or not wallet.strip():
        return None

    if not isinstance(record, dict):
        return None

    if (
        isinstance(event_index, bool)
        or not isinstance(event_index, int)
        or event_index < 0
    ):
        return None

    if "quote_mint" in record or "quote_delta_raw" in record:
        return None

    side = record.get("event_type")
    token_delta = record.get("token_delta_raw")
    sol_delta = record.get("sol_delta_lamports")

    if side not in ("BUY", "SELL"):
        return None

    if (
        isinstance(token_delta, bool)
        or not isinstance(token_delta, int)
        or isinstance(sol_delta, bool)
        or not isinstance(sol_delta, int)
    ):
        return None

    if side == "BUY":
        valid = token_delta > 0 and sol_delta < 0
    else:
        valid = token_delta < 0 and sol_delta > 0

    if not valid:
        return None

    signature = record.get("signature")
    token_mint = record.get("token_mint")
    timestamp_ms = record.get("timestamp_ms")
    token_decimals = record.get("token_decimals")

    if (
        not isinstance(signature, str)
        or not signature.strip()
        or not isinstance(token_mint, str)
        or not token_mint.strip()
        or isinstance(timestamp_ms, bool)
        or not isinstance(timestamp_ms, int)
        or timestamp_ms < 0
        or isinstance(token_decimals, bool)
        or not isinstance(token_decimals, int)
        or not 0 <= token_decimals <= 255
    ):
        return None

    event = {
        "wallet": wallet.strip(),
        "signature": signature.strip(),
        "event_index": event_index,
        "token_mint": token_mint.strip(),
        "side": side,
        "timestamp_ms": timestamp_ms,
        "token_amount_raw": str(abs(token_delta)),
        "token_decimals": token_decimals,
        "quote_mint": NATIVE_SOL,
        "quote_amount_raw": str(abs(sol_delta)),
        "quote_decimals": 9,
        "data_quality": "partial",
    }

    for field in ("slot", "transaction_index"):
        value = record.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            event[field] = value

    fee_raw = record.get("fee_amount_raw")

    if fee_raw is not None:
        fee_mint = record.get("fee_mint")
        fee_decimals = record.get("fee_decimals")

        if (
            not isinstance(fee_raw, str)
            or not fee_raw.isascii()
            or not fee_raw.isdigit()
            or int(fee_raw) <= 0
            or not isinstance(fee_mint, str)
            or not fee_mint.strip()
            or isinstance(fee_decimals, bool)
            or not isinstance(fee_decimals, int)
            or not 0 <= fee_decimals <= 255
        ):
            return None

        event["fee_amount_raw"] = fee_raw
        event["fee_mint"] = fee_mint
        event["fee_decimals"] = fee_decimals

        if record.get("fee_source") == "solana_transaction_meta_fee":
            event["fee_source"] = "solana_transaction_meta_fee"

    return event


def normalize_native_sol_fee(event):
    """Return a copy with eligible native SOL fee identity normalized."""
    if not isinstance(event, dict):
        raise TypeError("event must be a dictionary")

    from nexora.constants import WSOL_MINT

    result = dict(event)
    amount = result.get("fee_amount_raw")
    decimals = result.get("fee_decimals")

    if (
        result.get("quote_mint") == NATIVE_SOL
        and result.get("fee_source") == "solana_transaction_meta_fee"
        and result.get("fee_mint") == WSOL_MINT
        and isinstance(decimals, int)
        and not isinstance(decimals, bool)
        and decimals == 9
        and isinstance(amount, str)
        and amount.isascii()
        and amount.isdigit()
        and any(char != "0" for char in amount)
    ):
        result["fee_mint"] = NATIVE_SOL

    return result

"""Read-only Wallet Behavior to FIFO event adapter."""

from nexora.constants import USDC_MINT, WSOL_MINT
from nexora.native_sol_fifo_adapter import (
    native_sol_to_fifo_event,
    normalize_native_sol_fee,
)

QUOTE_DECIMALS = {
    USDC_MINT: 6,
    WSOL_MINT: 9,
}


def behavior_to_fifo_events(analysis):
    """Convert supported swaps to partial-quality FIFO events."""
    if not isinstance(analysis, dict):
        raise TypeError("analysis must be a dictionary")

    wallet = analysis.get("wallet")
    records = analysis.get("classifications")

    if not isinstance(wallet, str) or not wallet.strip():
        raise ValueError("Invalid wallet")

    if not isinstance(records, list):
        raise TypeError("classifications must be a list")

    events = []
    skipped = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            skipped.append({"index": index, "reason": "invalid_record"})
            continue

        side = record.get("event_type")
        if side not in ("BUY", "SELL"):
            continue

        if (
            "sol_delta_lamports" in record
            and "quote_mint" not in record
            and "quote_delta_raw" not in record
        ):
            native_event = native_sol_to_fifo_event(
                wallet, record, event_index=index
            )
            if native_event is None:
                skipped.append({
                    "index": index,
                    "reason": "invalid_native_sol"
                })
            else:
                events.append(
                    normalize_native_sol_fee(native_event)
                )
            continue

        quote_mint = record.get("quote_mint")

        if quote_mint not in QUOTE_DECIMALS:
            skipped.append({"index": index, "reason": "unsupported_quote"})
            continue

        token_delta = record.get("token_delta_raw")
        quote_delta = record.get("quote_delta_raw")

        if (
            isinstance(token_delta, bool)
            or not isinstance(token_delta, int)
            or isinstance(quote_delta, bool)
            or not isinstance(quote_delta, int)
        ):
            skipped.append({"index": index, "reason": "invalid_amount"})
            continue

        if side == "BUY":
            valid_direction = token_delta > 0 and quote_delta < 0
        else:
            valid_direction = token_delta < 0 and quote_delta > 0

        if not valid_direction:
            skipped.append({"index": index, "reason": "invalid_direction"})
            continue

        signature = record.get("signature")
        token_mint = record.get("token_mint")
        timestamp_ms = record.get("timestamp_ms")
        token_decimals = record.get("token_decimals")

        if (
            not isinstance(signature, str) or not signature.strip()
            or not isinstance(token_mint, str) or not token_mint.strip()
            or isinstance(timestamp_ms, bool)
            or not isinstance(timestamp_ms, int)
            or timestamp_ms < 0
            or isinstance(token_decimals, bool)
            or not isinstance(token_decimals, int)
            or not 0 <= token_decimals <= 255
        ):
            skipped.append({"index": index, "reason": "missing_metadata"})
            continue

        event = {
            "wallet": wallet.strip(),
            "signature": signature.strip(),
            "event_index": index,
            "token_mint": token_mint.strip(),
            "side": side,
            "timestamp_ms": timestamp_ms,
            "token_amount_raw": str(abs(token_delta)),
            "token_decimals": token_decimals,
            "quote_mint": quote_mint,
            "quote_amount_raw": str(abs(quote_delta)),
            "quote_decimals": QUOTE_DECIMALS[quote_mint],
            "data_quality": "partial",
        }

        for field in ("slot", "transaction_index"):
            value = record.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                event[field] = value

        fee_raw = record.get("fee_amount_raw")
        fee_mint = record.get("fee_mint")
        fee_decimals = record.get("fee_decimals")

        if fee_raw is not None:
            if (
                isinstance(fee_raw, str)
                and fee_raw.isascii()
                and fee_raw.isdigit()
                and int(fee_raw) > 0
                and isinstance(fee_mint, str)
                and fee_mint.strip()
                and isinstance(fee_decimals, int)
                and not isinstance(fee_decimals, bool)
                and 0 <= fee_decimals <= 255
            ):
                event["fee_amount_raw"] = fee_raw
                event["fee_mint"] = fee_mint
                event["fee_decimals"] = fee_decimals
            else:
                skipped.append({"index": index, "reason": "invalid_fee"})
                continue

        events.append(event)

    return {
        "events": events,
        "skipped": skipped,
        "data_quality": "partial",
        "database_written": False,
        "orders_submitted": False,
    }

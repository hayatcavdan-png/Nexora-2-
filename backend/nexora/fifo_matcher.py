from collections import defaultdict, deque
from decimal import Decimal, localcontext

from nexora.amounts import raw_to_decimal


def match_fifo(events, verified_only=True):
    """
    Pure FIFO matcher.
    No database access and no file writes.
    PnL is reported in the quote asset, not USD.
    """

    if not isinstance(events, (list, tuple)):
        raise TypeError("events must be a list or tuple")
    if not isinstance(verified_only, bool):
        raise TypeError("verified_only must be a boolean")

    queues = defaultdict(deque)
    matches = []
    skipped = []
    unmatched_sells = []
    excluded_fees = []

    valid_events = []

    for event in events:
        try:
            if not isinstance(event, dict):
                raise TypeError("event must be a dictionary")

            required = (
                "wallet", "signature", "event_index", "token_mint",
                "side", "timestamp_ms", "token_amount_raw",
                "token_decimals", "quote_mint", "quote_amount_raw",
                "quote_decimals", "data_quality",
            )
            missing = [key for key in required if key not in event]
            if missing:
                raise ValueError("missing fields: " + ", ".join(missing))

            for name in ("wallet", "signature", "token_mint", "quote_mint"):
                value = event[name]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(name + " must be a non-empty string")

            if event["side"] not in ("BUY", "SELL"):
                raise ValueError("side must be BUY or SELL")

            for name in ("timestamp_ms", "event_index"):
                value = event[name]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(name + " must be a non-negative integer")

            slot = event.get("slot")
            if slot is not None and (
                isinstance(slot, bool) or not isinstance(slot, int) or slot < 0
            ):
                raise ValueError("slot must be a non-negative integer or None")

            transaction_index = event.get("transaction_index")
            if transaction_index is not None and (
                isinstance(transaction_index, bool)
                or not isinstance(transaction_index, int)
                or transaction_index < 0
            ):
                raise ValueError(
                    "transaction_index must be a non-negative integer or None"
                )

            if event["data_quality"] not in ("verified", "partial", "unverified"):
                raise ValueError("invalid data_quality")

            if verified_only and event["data_quality"] != "verified":
                skipped.append({
                    "signature": event["signature"],
                    "reason": "data_quality_not_verified",
                })
                continue

            valid_events.append(event)

        except (TypeError, ValueError, KeyError) as exc:
            skipped.append({
                "signature": event.get("signature") if isinstance(event, dict) else None,
                "reason": "invalid_event",
                "detail": str(exc),
            })

    # First establish chronological and slot order. Python's sort is stable,
    # so unknown transaction order never gets replaced by signature order.
    chronological = sorted(
        valid_events,
        key=lambda event: (
            event["timestamp_ms"],
            event.get("slot") if event.get("slot") is not None else -1,
        ),
    )

    # Sort within a same-time, same-slot group only when every index is known.
    ordered = []
    group = []

    def flush_group():
        if not group:
            return
        if all(event.get("transaction_index") is not None for event in group):
            ordered.extend(
                sorted(group, key=lambda event: event["transaction_index"])
            )
        else:
            ordered.extend(group)
        group.clear()

    previous_group_key = None
    for event in chronological:
        group_key = (
            event["timestamp_ms"],
            event.get("slot") if event.get("slot") is not None else -1,
        )
        if previous_group_key is not None and group_key != previous_group_key:
            flush_group()
        group.append(event)
        previous_group_key = group_key

    flush_group()

    max_raw_digits = 1
    max_decimals = 0

    for event in ordered:
        for field in ("token_amount_raw", "quote_amount_raw", "fee_amount_raw"):
            value = event.get(field)
            if isinstance(value, str) and value.isascii() and value.isdigit():
                max_raw_digits = max(max_raw_digits, len(value))

        for field in ("token_decimals", "quote_decimals", "fee_decimals"):
            value = event.get(field)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= 255
            ):
                max_decimals = max(max_decimals, value)

    max_digits = max(100, max_raw_digits + (2 * max_decimals) + 50)

    with localcontext() as ctx:
        ctx.prec = max_digits

        for event in ordered:
            try:
                wallet = event["wallet"]
                token_mint = event["token_mint"]
                quote_mint = event["quote_mint"]
                token_decimals = event["token_decimals"]
                quote_decimals = event["quote_decimals"]

                token_amount = raw_to_decimal(
                    event["token_amount_raw"], token_decimals
                )
                quote_amount = raw_to_decimal(
                    event["quote_amount_raw"], quote_decimals
                )

                fee = Decimal("0")
                fee_status = "not_provided"

                if event.get("fee_amount_raw") is not None:
                    fee_mint = event.get("fee_mint")
                    fee_decimals = event.get("fee_decimals")

                    if not isinstance(fee_mint, str) or not fee_mint.strip():
                        raise ValueError("fee_mint is required when fee_amount_raw is provided")

                    validated_fee = raw_to_decimal(
                        event["fee_amount_raw"], fee_decimals
                    )

                    if fee_mint == quote_mint:
                        fee = validated_fee
                        fee_status = "included"
                    else:
                        fee_status = "excluded_different_asset"
                        excluded_fees.append({
                            "signature": event["signature"],
                            "fee_mint": fee_mint,
                            "fee_amount_raw": event["fee_amount_raw"],
                            "reason": "fee_not_in_quote_asset",
                        })

                key = (
                    wallet, token_mint, quote_mint,
                    token_decimals, quote_decimals,
                )
                unit_quote = quote_amount / token_amount

                if event["side"] == "BUY":
                    queues[key].append({
                        "remaining": token_amount,
                        "unit_cost": unit_quote,
                        "fee_per_token": fee / token_amount,
                        "signature": event["signature"],
                        "timestamp_ms": event["timestamp_ms"],
                    })
                    continue

                remaining_to_sell = token_amount
                sell_fee_per_token = fee / token_amount

                while remaining_to_sell > 0 and queues[key]:
                    lot = queues[key][0]
                    quantity = min(remaining_to_sell, lot["remaining"])

                    proceeds = quantity * unit_quote
                    cost = quantity * lot["unit_cost"]
                    allocated_buy_fee = quantity * lot["fee_per_token"]
                    allocated_sell_fee = quantity * sell_fee_per_token
                    pnl = proceeds - cost - allocated_buy_fee - allocated_sell_fee

                    matches.append({
                        "wallet": wallet,
                        "token_mint": token_mint,
                        "quote_mint": quote_mint,
                        "buy_signature": lot["signature"],
                        "sell_signature": event["signature"],
                        "quantity": str(quantity),
                        "buy_cost_quote": str(cost),
                        "sell_proceeds_quote": str(proceeds),
                        "buy_fee_quote": str(allocated_buy_fee),
                        "sell_fee_quote": str(allocated_sell_fee),
                        "fee_status": fee_status,
                        "realized_pnl_quote": str(pnl),
                    })

                    lot["remaining"] -= quantity
                    remaining_to_sell -= quantity

                    if lot["remaining"] == 0:
                        queues[key].popleft()

                if remaining_to_sell > 0:
                    unmatched_sells.append({
                        "signature": event["signature"],
                        "token_mint": token_mint,
                        "quote_mint": quote_mint,
                        "unmatched_quantity": str(remaining_to_sell),
                    })

            except (TypeError, ValueError, KeyError) as exc:
                skipped.append({
                    "signature": event.get("signature"),
                    "reason": "invalid_event",
                    "detail": str(exc),
                })

        open_positions = []
        for key, lots in queues.items():
            for lot in lots:
                if lot["remaining"] > 0:
                    open_positions.append({
                        "wallet": key[0],
                        "token_mint": key[1],
                        "quote_mint": key[2],
                        "remaining_quantity": str(lot["remaining"]),
                        "unit_cost_quote": str(lot["unit_cost"]),
                        "buy_signature": lot["signature"],
                    })

        realized_by_quote = defaultdict(Decimal)
        for item in matches:
            realized_by_quote[item["quote_mint"]] += Decimal(
                item["realized_pnl_quote"]
            )

        return {
            "method": "FIFO",
            "verified_only": verified_only,
            "matches": matches,
            "open_positions": open_positions,
            "unmatched_sells": unmatched_sells,
            "skipped_events": skipped,
            "excluded_fees": excluded_fees,
            "realized_pnl_by_quote": {
                mint: str(value) for mint, value in realized_by_quote.items()
            },
            "database_written": False,
            "orders_submitted": False,
        }

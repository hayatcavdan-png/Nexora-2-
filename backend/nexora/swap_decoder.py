"""Read-only Solana swap decoder based on wallet balance changes."""

WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
JUPITER_PROGRAM_ID = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"



# SOL/WSOL/USDC/USDT arasındaki dönüşümler token alım-satımı değildir; kopyalanmaz.
NON_COPYABLE_MINTS = {WSOL_MINT, USDC_MINT, USDT_MINT}

SUPPORTED_SWAP_PROGRAMS = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "JUPITER",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "PUMP_FUN",
}


def _account_keys(transaction):
    message = (
        (transaction.get("transaction") or {}).get("message") or {}
    )
    result = []
    for item in message.get("accountKeys") or []:
        address = item.get("pubkey") if isinstance(item, dict) else item
        result.append(address)
    return result



def _wallet_network_fee_fields(transaction, wallet):
    """Return normalized SOL fee fields only when wallet is confirmed payer."""
    keys = _account_keys(transaction)
    meta = transaction.get("meta") or {}

    if not keys or keys[0] != wallet:
        return {}

    fee = meta.get("fee")
    if (
        isinstance(fee, bool)
        or not isinstance(fee, int)
        or fee <= 0
    ):
        return {}

    return {
        "fee_amount_raw": str(fee),
        "fee_mint": WSOL_MINT,
        "fee_decimals": 9,
        "fee_source": "solana_transaction_meta_fee",
    }

def _wallet_sol_delta(transaction, wallet):
    keys = _account_keys(transaction)
    meta = transaction.get("meta") or {}

    if wallet not in keys:
        return None

    index = keys.index(wallet)
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []

    if index >= len(pre) or index >= len(post):
        return None

    if not isinstance(pre[index], int) or not isinstance(post[index], int):
        return None

    delta = post[index] - pre[index]

    # İşlem ücretini yalnızca analiz edilen cüzdan ödemişse ayır.
    fee_payer = keys[0] if keys else None
    fee = meta.get("fee", 0)

    if (
        fee_payer == wallet
        and isinstance(fee, int)
        and not isinstance(fee, bool)
        and fee >= 0
    ):
        delta += fee

    return delta


def _token_balances(transaction, wallet):
    """Aggregate wallet token balances, rejecting inconsistent metadata."""
    meta = transaction.get("meta") or {}
    totals = {}

    for field in ("preTokenBalances", "postTokenBalances"):
        side = "pre" if field == "preTokenBalances" else "post"
        records = meta.get(field) or []
        if not isinstance(records, list):
            return None

        for item in records:
            if not isinstance(item, dict) or item.get("owner") != wallet:
                continue

            mint = item.get("mint")
            amount_data = item.get("uiTokenAmount")
            if not isinstance(mint, str) or not mint:
                return None
            if not isinstance(amount_data, dict):
                return None

            raw_amount = amount_data.get("amount")
            decimals = amount_data.get("decimals")

            if not isinstance(raw_amount, str) or not raw_amount.isdigit():
                return None
            if (
                isinstance(decimals, bool)
                or not isinstance(decimals, int)
                or not 0 <= decimals <= 255
            ):
                return None

            entry = totals.setdefault(
                mint, {"pre": 0, "post": 0, "decimals": decimals}
            )
            if entry["decimals"] != decimals:
                return None

            entry[side] += int(raw_amount)

    return totals


def _has_token_account_lifecycle(transaction, wallet):
    """Fail closed when wallet token-account lifecycle is uncertain."""
    meta = transaction.get("meta") or {}

    def account_indexes(field):
        records = meta.get(field) or []
        if not isinstance(records, list):
            return None

        indexes = set()

        for item in records:
            if not isinstance(item, dict):
                return None
            if item.get("owner") != wallet:
                continue

            index = item.get("accountIndex")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
            ):
                return None

            indexes.add(index)

        return indexes

    pre_indexes = account_indexes("preTokenBalances")
    post_indexes = account_indexes("postTokenBalances")

    if pre_indexes is None or post_indexes is None:
        return True

    return pre_indexes != post_indexes


def _swap_program(transaction):
    message = (
        (transaction.get("transaction") or {}).get("message") or {}
    )
    meta = transaction.get("meta") or {}

    account_keys = []
    for account in message.get("accountKeys") or []:
        if isinstance(account, str):
            account_keys.append(account)
        elif isinstance(account, dict):
            account_keys.append(account.get("pubkey"))
        else:
            account_keys.append(None)

    loaded = meta.get("loadedAddresses") or {}
    if isinstance(loaded, dict):
        for field in ("writable", "readonly"):
            addresses = loaded.get(field) or []
            if isinstance(addresses, list):
                account_keys.extend(
                    address if isinstance(address, str) else None
                    for address in addresses
                )

    detected = set()

    def inspect(instructions):
        if not isinstance(instructions, list):
            return

        for instruction in instructions:
            if not isinstance(instruction, dict):
                continue

            program_id = instruction.get("programId")

            if not isinstance(program_id, str):
                index = instruction.get("programIdIndex")
                if type(index) is int and 0 <= index < len(account_keys):
                    program_id = account_keys[index]

            if isinstance(program_id, str):
                program = SUPPORTED_SWAP_PROGRAMS.get(program_id)
                if program:
                    detected.add(program)

    inspect(message.get("instructions"))

    inner_groups = meta.get("innerInstructions") or []
    if isinstance(inner_groups, list):
        for group in inner_groups:
            if isinstance(group, dict):
                inspect(group.get("instructions"))

    if len(detected) == 1:
        return next(iter(detected))

    return None


def decode_swap(transaction, wallet):
    """Decode a likely native-SOL or WSOL swap without side effects."""
    if not isinstance(transaction, dict):
        raise TypeError("transaction must be a dictionary")
    if not isinstance(wallet, str) or not wallet.strip():
        raise ValueError("wallet must be a non-empty string")

    wallet = wallet.strip()
    meta = transaction.get("meta") or {}

    if meta.get("err") is not None:
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["transaction_failed"],
        }

    # Pump.fun holder fee distribution: classify only with
    # explicit instruction evidence and a positive wallet SOL delta.
    logs = meta.get("logMessages") or []
    has_holder_fee_instruction = (
        isinstance(logs, list)
        and any(
            isinstance(line, str)
            and "Instruction: DistributeFeeToHolders" in line
            for line in logs
        )
    )

    has_pump_fun_invocation = (
        isinstance(logs, list)
        and any(
            isinstance(line, str)
            and line.startswith(f"Program {PUMP_FUN_PROGRAM_ID} invoke [")
            for line in logs
        )
    )

    if has_holder_fee_instruction and has_pump_fun_invocation:
        sol_delta = _wallet_sol_delta(transaction, wallet)

        if sol_delta is not None and sol_delta > 0:
            return {
                "event_type": "FEE_REWARD",
                "confidence": "high",
                "evidence": [
                    "pump_fun_distribute_fee_to_holders",
                    "positive_wallet_sol_delta_after_fee_adjustment",
                ],
                "sol_delta_lamports": sol_delta,
                "swap_program": "PUMP_FUN",
            }

    program = _swap_program(transaction)
    if program is None:
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["unsupported_or_missing_swap_program"],
        }

    # Missing execution logs cannot confirm a swap.
    if not isinstance(logs, list) or not logs:
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["swap_execution_logs_missing"],
        }

    # Reject contradictory execution logs when logs are available.
    # Missing logs remain supported for legacy synthetic fixtures.
    if isinstance(logs, list) and logs:
        expected_id = (
            PUMP_FUN_PROGRAM_ID if program == "PUMP_FUN"
            else JUPITER_PROGRAM_ID if program == "JUPITER"
            else None
        )
        if expected_id and not any(
            isinstance(line, str)
            and line.startswith(f"Program {expected_id} invoke [")
            for line in logs
        ):
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["swap_program_invocation_not_confirmed"],
            }

    balances = _token_balances(transaction, wallet)
    if balances is None:
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["inconsistent_or_invalid_token_balance_metadata"],
        }

    changes = []

    for mint, amounts in balances.items():
        delta = amounts["post"] - amounts["pre"]
        if delta:
            changes.append({
                "mint": mint,
                "token_delta_raw": delta,
                "token_decimals": amounts["decimals"],
            })

    wsol_changes = [
        item for item in changes if item["mint"] == WSOL_MINT
    ]
    token_changes = [
        item for item in changes if item["mint"] != WSOL_MINT
    ]

    evidence = [
        f"supported_swap_program:{program}",
        "wallet_token_balance_changed",
    ]
    quote_mint = None
    quote_delta_raw = None

    if len(wsol_changes) == 1 and len(token_changes) == 1:
        if _has_token_account_lifecycle(transaction, wallet):
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["token_account_created_or_closed"],
            }

        change = token_changes[0]
        if change["mint"] in NON_COPYABLE_MINTS:
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["quote_asset_swap_not_copyable"],
            }
        quote_delta_raw = wsol_changes[0]["token_delta_raw"]
        quote_mint = WSOL_MINT

        if change["token_delta_raw"] > 0 and quote_delta_raw < 0:
            event_type = "BUY"
        elif change["token_delta_raw"] < 0 and quote_delta_raw > 0:
            event_type = "SELL"
        else:
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["token_and_wsol_deltas_do_not_confirm_swap"],
            }

        evidence.append("wallet_wsol_balance_changed")

    elif (
        not wsol_changes
        and len(token_changes) == 2
        and sum(item["mint"] == USDC_MINT for item in token_changes) == 1
        and all(item["mint"] != USDT_MINT for item in token_changes)
    ):
        if _has_token_account_lifecycle(transaction, wallet):
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["token_account_created_or_closed"],
            }

        quote = next(
            item for item in token_changes
            if item["mint"] == USDC_MINT
        )
        change = next(
            item for item in token_changes
            if item["mint"] != USDC_MINT
        )

        quote_delta_raw = quote["token_delta_raw"]
        quote_mint = USDC_MINT

        if change["token_delta_raw"] > 0 and quote_delta_raw < 0:
            event_type = "BUY"
        elif change["token_delta_raw"] < 0 and quote_delta_raw > 0:
            event_type = "SELL"
        else:
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["token_and_usdc_deltas_do_not_confirm_swap"],
            }

        evidence.append("wallet_usdc_balance_changed")

    elif not wsol_changes and len(token_changes) == 1:
        if _has_token_account_lifecycle(transaction, wallet):
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["token_account_created_or_closed"],
            }

        change = token_changes[0]
        if change["mint"] in NON_COPYABLE_MINTS:
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["quote_asset_swap_not_copyable"],
            }
        sol_delta = _wallet_sol_delta(transaction, wallet)

        if sol_delta is None:
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["wallet_sol_balance_unavailable"],
            }

        if change["token_delta_raw"] > 0 and sol_delta < 0:
            event_type = "BUY"
        elif change["token_delta_raw"] < 0 and sol_delta > 0:
            event_type = "SELL"
        else:
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["token_and_sol_deltas_do_not_confirm_swap"],
            }

        evidence.append("wallet_sol_balance_changed")

    else:
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["ambiguous_token_balance_changes"],
        }

    result = {
        "event_type": event_type,
        "confidence": "medium",
        "evidence": evidence,
        "token_mint": change["mint"],
        "token_delta_raw": change["token_delta_raw"],
        "token_decimals": change["token_decimals"],
        "swap_program": program,
    }

    if quote_mint is not None:
        result["quote_mint"] = quote_mint
        result["quote_delta_raw"] = quote_delta_raw
        result["sol_delta_lamports"] = None
    else:
        result["sol_delta_lamports"] = sol_delta

    result.update(_wallet_network_fee_fields(transaction, wallet))
    return result

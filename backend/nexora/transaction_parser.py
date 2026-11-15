"""Read-only Solana transaction classification."""


def _logs(transaction):
    meta = transaction.get("meta") or {}
    return [
        item
        for item in (meta.get("logMessages") or [])
        if isinstance(item, str)
    ]


def _wallet_received_sol(transaction, wallet):
    message = (
        (transaction.get("transaction") or {})
        .get("message") or {}
    )
    keys = message.get("accountKeys") or []
    meta = transaction.get("meta") or {}
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []

    for index, account in enumerate(keys):
        address = (
            account.get("pubkey")
            if isinstance(account, dict)
            else account
        )
        if address == wallet and index < len(pre) and index < len(post):
            delta = post[index] - pre[index]

            first_account = keys[0] if keys else None
            fee_payer = (
                first_account.get("pubkey")
                if isinstance(first_account, dict)
                else first_account
            )
            fee = meta.get("fee")

            if (
                fee_payer == wallet
                and isinstance(fee, int)
                and not isinstance(fee, bool)
                and fee >= 0
            ):
                delta += fee

            return delta > 0
    return False


def _transfer_records(transaction):
    message = (
        (transaction.get("transaction") or {})
        .get("message") or {}
    )
    meta = transaction.get("meta") or {}
    groups = [
        {"instructions": message.get("instructions") or []}
    ]
    groups.extend(meta.get("innerInstructions") or [])

    account_indices = {}
    for index, account in enumerate(message.get("accountKeys") or []):
        address = (
            account.get("pubkey")
            if isinstance(account, dict)
            else account
        )
        if isinstance(address, str) and address:
            account_indices[address] = index

    balances_by_index = {}
    for item in meta.get("postTokenBalances") or []:
        if not isinstance(item, dict):
            continue
        index = item.get("accountIndex")
        owner = item.get("owner")
        mint = item.get("mint")
        if isinstance(index, int):
            balances_by_index[index] = {
                "owner": owner,
                "mint": mint,
            }

    records = []
    for group in groups:
        for instruction in group.get("instructions") or []:
            if not isinstance(instruction, dict):
                continue
            parsed = instruction.get("parsed")
            if not isinstance(parsed, dict):
                continue
            if parsed.get("type") not in {"transfer", "transferChecked"}:
                continue

            info = parsed.get("info")
            if not isinstance(info, dict):
                continue
            destination = info.get("destination")
            source = info.get("source")
            mint = info.get("mint")

            if not isinstance(destination, str) or not destination:
                continue

            index = account_indices.get(destination)
            balance = balances_by_index.get(index, {})
            owner = balance.get("owner")

            # Mint must agree with the destination token balance.
            if mint and balance.get("mint") and mint != balance.get("mint"):
                owner = None

            records.append({
                "destination": destination,
                "source": source,
                "mint": mint,
                "owner": owner,
                "program": instruction.get("program"),
                "program_id": instruction.get("programId"),
            })

    return records


def _transfer_destinations(transaction):
    return {
        record["destination"]
        for record in _transfer_records(transaction)
    }


def _transfer_destination_owners(transaction):
    return {
        record["owner"]
        for record in _transfer_records(transaction)
        if record["owner"]
    }


def _has_distribution_evidence(records):
    groups = {}

    for record in records:
        source = record.get("source")
        mint = record.get("mint")
        owner = record.get("owner")
        destination = record.get("destination")

        # Missing source, mint, or owner is insufficient evidence.
        if not all(isinstance(value, str) and value for value in (
            source, mint, owner, destination
        )):
            continue

        key = (source, mint)
        group = groups.setdefault(key, {
            "destinations": set(),
            "owners": set(),
            "mint": mint,
            "source": source,
        })
        group["destinations"].add(destination)
        group["owners"].add(owner)

    for group in groups.values():
        if (
            len(group["destinations"]) >= 2
            and len(group["owners"]) >= 2
        ):
            return group

    return None



def _wallet_is_involved(transaction, wallet):
    message = (
        (transaction.get("transaction") or {})
        .get("message") or {}
    )
    meta = transaction.get("meta") or {}

    for account in message.get("accountKeys") or []:
        address = (
            account.get("pubkey")
            if isinstance(account, dict)
            else account
        )
        if address == wallet:
            return True

    for field in ("preTokenBalances", "postTokenBalances"):
        for item in meta.get(field) or []:
            if isinstance(item, dict) and item.get("owner") == wallet:
                return True

    return False


def _source_owned_by_wallet(transaction, source, mint, wallet):
    message = (
        (transaction.get("transaction") or {})
        .get("message") or {}
    )
    keys = message.get("accountKeys") or []
    meta = transaction.get("meta") or {}
    matching_owners = set()

    for field in ("preTokenBalances", "postTokenBalances"):
        for balance in meta.get(field) or []:
            if not isinstance(balance, dict):
                continue
            index = balance.get("accountIndex")
            if type(index) is not int or not 0 <= index < len(keys):
                continue
            account = keys[index]
            address = (
                account.get("pubkey")
                if isinstance(account, dict)
                else account
            )
            if address != source or balance.get("mint") != mint:
                continue
            owner = balance.get("owner")
            if isinstance(owner, str) and owner:
                matching_owners.add(owner)

    token_program = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

    top_instructions = message.get("instructions") or []
    inner_by_index = {}

    for group in meta.get("innerInstructions") or []:
        if not isinstance(group, dict):
            continue
        index = group.get("index")
        if type(index) is not int or not 0 <= index < len(top_instructions):
            continue
        inner_by_index.setdefault(index, []).extend(
            group.get("instructions") or []
        )

    ordered = []
    for index, instruction in enumerate(top_instructions):
        ordered.append(instruction)
        ordered.extend(inner_by_index.get(index, []))

    initialize_owners = set()
    transfer_seen = False

    for instruction in ordered:
        if not isinstance(instruction, dict):
            continue

        parsed = instruction.get("parsed")
        if not isinstance(parsed, dict):
            continue

        kind = parsed.get("type")
        info = parsed.get("info")
        if not isinstance(info, dict):
            continue

        if (
            kind in {"transfer", "transferChecked"}
            and info.get("source") == source
            and info.get("mint") == mint
        ):
            transfer_seen = True

        if (
            kind in {
                "initializeAccount",
                "initializeAccount2",
                "initializeAccount3",
            }
            and instruction.get("programId") == token_program
            and info.get("account") == source
            and info.get("mint") == mint
        ):
            if transfer_seen:
                return False
            initialize_owners.add(info.get("owner"))

    if matching_owners and matching_owners != {wallet}:
        return False

    if initialize_owners and initialize_owners != {wallet}:
        return False

    return bool(matching_owners or initialize_owners)


def classify_transaction(transaction, wallet):
    """Classify a Solana transaction using conservative evidence."""
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

    logs = _logs(transaction)

    has_pump_fun_invocation = any(
        line.startswith(
            "Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke ["
        )
        for line in logs
    )

    has_holder_fee_instruction = any(
        "Instruction: DistributeFeeToHolders" in line
        for line in logs
    )

    if has_pump_fun_invocation and has_holder_fee_instruction:
        received = _wallet_received_sol(transaction, wallet)
        return {
            "event_type": "FEE_REWARD" if received else "UNKNOWN",
            "confidence": "high" if received else "low",
            "evidence": [
                "pumpfun_distribute_fee_log",
                "wallet_received_sol" if received
                else "wallet_receipt_not_confirmed",
            ],
        }

    if not _wallet_is_involved(transaction, wallet):
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["wallet_not_involved"],
        }

    records = _transfer_records(transaction)
    destinations = {
        record["destination"] for record in records
    }
    owners = {
        record["owner"] for record in records
        if record["owner"]
    }

    if not destinations:
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["insufficient_classification_evidence"],
        }

    if not owners:
        return {
            "event_type": "UNKNOWN",
            "confidence": "none",
            "evidence": ["parsed_transfer_without_resolved_owners"],
        }

    distribution = _has_distribution_evidence(records)

    if distribution:
        if not _source_owned_by_wallet(
            transaction,
            distribution["source"],
            distribution["mint"],
            wallet,
        ):
            return {
                "event_type": "UNKNOWN",
                "confidence": "none",
                "evidence": ["distribution_source_ownership_unverified"],
            }

        return {
            "event_type": "DISTRIBUTION",
            "confidence": "medium",
            "evidence": [
                "same_source_and_mint",
                f"distinct_destinations:{len(distribution['destinations'])}",
                f"distinct_owners:{len(distribution['owners'])}",
            ],
            "distribution_mint": distribution["mint"],
            "distribution_source": distribution["source"],
            "distribution_destination_count": len(distribution["destinations"]),
            "distribution_owner_count": len(distribution["owners"]),
        }

    return {
        "event_type": "TRANSFER",
        "confidence": "medium",
        "evidence": [
            "parsed_token_transfer_instruction",
            f"distinct_destinations:{len(destinations)}",
            f"distinct_owners:{len(owners)}",
        ],
    }

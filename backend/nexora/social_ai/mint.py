"""Tam adresi, proje profili ve SPL mint hesabıyla eşler."""
from dataclasses import dataclass

from nexora.token_safety import DANGER_2022_EXT, SAFE_2022_EXT, TOKEN_2022, TOKEN_PROGRAM

from .events import author_key, identifier, valid_address
from .providers import Batch, SOCIAL_SOURCES, snapshot


@dataclass(frozen=True)
class MintMatch:
    status: str
    mint: str | None
    reason: str
    profile: dict | None = None
    account: dict | None = None


def resolve(event, profiles, helius):
    if len(event.mint_candidates) != 1:
        reason = "MINT_ADRESI_YOK" if not event.mint_candidates else "BIRDEN_FAZLA_MINT"
        return MintMatch("UNRESOLVED", None, reason)
    mint, = event.mint_candidates
    profile = snapshot(profiles, mint, event.observed_at)
    account = snapshot(helius, mint, event.observed_at)
    if profile is None or profile.get("canonical") is not True:
        return MintMatch("UNRESOLVED", None, "RESMI_MINT_TEYIDI_YOK", profile, account)
    if (account is None or account.get("program") not in (TOKEN_PROGRAM, TOKEN_2022)
            or account.get("account_type") != "mint" or account.get("initialized") is not True):
        return MintMatch("UNRESOLVED", None, "SPL_MINT_TEYIDI_YOK", profile, account)
    return MintMatch("VERIFIED", mint, "RESMI_PROFIL_VE_SPL_MINT", profile, account)


def mint_batches(batches):
    return tuple(Batch(batches[source].status, tuple(r for r in batches[source].items if r.get("kind") == kind))
                 for source, kind in (("token_profile", "profile"), ("helius", "mint")))


def author_verified(event, profiles):
    if event.claimed_role == "none":
        return True
    if event.claimed_role is None or len(event.mint_candidates) != 1:
        return None
    profile = snapshot(profiles, event.mint_candidates[0], event.observed_at)
    if profile is None or profile.get("canonical") is not True:
        return None
    accounts = profile.get("official_accounts" if event.claimed_role == "project" else "endorsers")
    if not isinstance(accounts, list):
        return None
    keys = set()
    for account in accounts:
        if not isinstance(account, dict):
            return None
        source, author = account.get("source"), identifier(account.get("author_id"))
        if source not in SOCIAL_SOURCES or author is None:
            return None
        keys.add(author_key(source, author))
    return event.author_id in keys


def authority_risks(account):
    if account is None:
        return [], ["MINT_YETKILERI_UNKNOWN"]
    risks, unknown = [], []
    for key, code in (("mint_authority", "MINT_YETKISI"), ("freeze_authority", "FREEZE_YETKISI")):
        if key not in account or (account[key] is not None and not valid_address(account[key])):
            unknown.append(code + "_UNKNOWN")
        elif account[key] is not None:
            risks.append(code)
    if account.get("program") == TOKEN_2022:
        extensions = account.get("extensions")
        if not isinstance(extensions, list) or not all(isinstance(x, str) for x in extensions):
            unknown.append("TOKEN_2022_UNKNOWN")
        else:
            if DANGER_2022_EXT.intersection(extensions):
                risks.append("TOKEN_2022_RISKI")
            if set(extensions) - SAFE_2022_EXT - DANGER_2022_EXT:
                unknown.append("TOKEN_2022_UNKNOWN")
    return risks, unknown

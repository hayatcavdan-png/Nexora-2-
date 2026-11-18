"""Açıklanabilir gölge sınıfları. Bilinmeyen kanıt erken uyarı eşiğini geçemez."""
from nexora.olcum import sayi, zaman

from .chain import independent_members
from .events import evidence_ref
from .mint import authority_risks, author_verified
from .providers import MAX_AGE, SOCIAL_SOURCES, snapshot

MIN_LIQUIDITY_USDC = 10_000
COORDINATION_SECONDS = 120


def _social_risks(event, peers, profiles, confirmations):
    risks, unknown = [], []
    for value, code in (
        (event.paid, "UCRETLI_GORUNURLUK"),
        (event.misleading, "YANILTICI_PAYLASIM"),
        (event.impersonation, "SAHTE_HESAP"),
    ):
        if value is True:
            risks.append(code)
        elif value is None:
            unknown.append(code + "_UNKNOWN")
    identity = author_verified(event, profiles)
    if identity is False:
        risks.append("SAHTE_PROJE_HESABI" if event.claimed_role == "project" else "SAHTE_INFLUENCER")
    elif identity is None:
        unknown.append("HESAP_TEYIDI_UNKNOWN")
    if event.text_hash is None:
        unknown.append("METIN_UNKNOWN")
    repeated = [p for p in peers if event.text_hash is not None and p.text_hash == event.text_hash]
    if repeated:
        risks.append("TEKRAR_EDEN_METIN")
    related = [p for p in peers if event.author_group and p.author_group == event.author_group]
    coordinators = {p.author_id for p in repeated + related
                    if event.observed_at - p.observed_at <= COORDINATION_SECONDS}
    coordinators.add(event.author_id)
    if len(coordinators) >= 3:
        risks.append("BOT_BENZERI_KOORDINASYON")
    # Olaydan sonra yayımlanmış ve t0 öncesinde gözlemlenmiş paylaşımlar teyide girebilir.
    clean = [p for p in peers if (confirmations is None or p.event_id in confirmations)
             and event.published_at < p.published_at and p.text_hash is not None and all(
        value is False for value in (p.paid, p.misleading, p.impersonation)
    ) and author_verified(p, profiles) is True]
    # Her kopya metin oy dışı kalır. Aynı kimlik ve aynı grup ayrı oy değildir.
    participants = [event, *clean]
    hashes = {}
    for p in participants:
        hashes[p.text_hash] = hashes.get(p.text_hash, 0) + 1
    groups, conflict = independent_members(
        (p.author_id, p.author_group) for p in participants if p.text_hash and hashes[p.text_hash] == 1
    )
    if conflict or event.author_group is None:
        unknown.append("TOPLULUK_BAGIMSIZLIGI_UNKNOWN")
    return risks, unknown, len(groups), [p.source_url or p.provenance for p in repeated + related + clean]


def classify(event, match, history, batches, profiles, during, overall, *,
             confirmations=None, extra_risks=(), extra_unknown=()):
    t0 = event.observed_at
    # Risk taraması, olayın yayınından önceki paylaşımları da gözlem penceresi içinde inceler.
    peers = [p for p in history if t0 - MAX_AGE <= p.observed_at < t0 and p.mint_candidates == event.mint_candidates]
    risks, unknown, voices, refs = _social_risks(event, peers, profiles, confirmations)
    risks.extend(extra_risks)
    unknown.extend(extra_unknown)
    if any(batches[source].status != "OK" for source in SOCIAL_SOURCES):
        unknown.append("SOSYAL_SAGLAYICI_UNKNOWN")
    if match.mint is None:
        unknown.append(match.reason)
    authority, missing = authority_risks(match.account if match.mint else None)
    risks.extend(authority)
    unknown.extend(missing)

    fresh = {}
    for source, row in (
        ("token_profile", match.profile), ("helius", match.account),
        ("jupiter", snapshot(batches["jupiter"], match.mint, t0) if match.mint else None),
        ("dex", snapshot(batches["dex"], match.mint, t0) if match.mint else None),
    ):
        if row is not None:
            ref = evidence_ref(source, (row["mint"], row["measured_at"], row["fetched_at"]))
            fresh[source] = dict(measured_at=zaman(row["measured_at"]), fetched_at=zaman(row["fetched_at"]),
                                 yas_sn=t0 - zaman(row["measured_at"]), kanit=ref)
            refs.append(ref)
        else:
            fresh[source] = None
        if source in ("jupiter", "dex"):
            liquidity = sayi(row.get("liquidity_usdc")) if row else None
            if liquidity is None or liquidity < 0:
                unknown.append(source.upper() + "_LIKIDITE_UNKNOWN")
            else:
                fresh[source]["liquidity_usdc"] = liquidity
                if liquidity < MIN_LIQUIDITY_USDC:
                    risks.append(source.upper() + "_YETERSIZ_LIKIDITE")
    if overall["iliskili_cuzdan"]:
        risks.append("ILISKILI_CUZDAN")
    refs.extend(r["kanit"] for r in overall["islemler"])
    if overall["durum"] != "OK" or overall["grup_bilgisi_eksik"]:
        unknown.append("ZINCIR_TEYIDI_UNKNOWN")

    if risks:
        label = "RISK_VETOSU_ADAYI"
    elif unknown:
        label = "BELIRSIZ"
    elif during["bagimsiz_alici_grubu"] >= 2 and voices >= 2:
        label = "SOSYAL_ERKEN_UYARI"
    else:
        label = "GOLGE_IZLE"
    return dict(sinif=label, gerekce=sorted(set(risks + unknown)) or [
        "BAGIMSIZ_SOSYAL_VE_ZINCIR_TEYIDI" if label == "SOSYAL_ERKEN_UYARI" else "TEYIT_ESIGI_ALTINDA"
    ], bagimsiz_topluluk_grubu=voices, kanit_linkleri=sorted(set([event.source_url or event.provenance, *refs])),
        veri_guncelligi=fresh)

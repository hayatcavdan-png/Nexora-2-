"""Kaynak gözlemlerini V1 kanıt ve gölge hesaplarıyla birleştiren salt okunur servis."""
from collections import Counter, defaultdict
from dataclasses import replace
from statistics import median
from typing import Protocol

from nexora.olcum import zaman

from ..chain import after_t0, before_t0, trades
from ..events import digest, evidence_ref
from ..mint import mint_batches, resolve
from ..providers import MAX_AGE, Batch, FixtureProvider, Provider
from ..risk import COORDINATION_SECONDS, classify
from ..shadow import HORIZONS, evaluate, summarize
from .fixtures import RecordedSources
from .observations import fixture_ref
from .sources import CATALOG, DELAYED, OK, UNKNOWN, SourceBatch

MIN_ACCURACY_MINTS = 10
EVIDENCE_SOURCES = ("token_profile", "helius", "jupiter", "dex", "quotes")


class SourceReader(Protocol):
    def read(self, source_id: str) -> SourceBatch:
        """Read one catalog source."""


class EventGroups:
    """Birleştirmenin kanıtı geldikçe takma kimlikleri ilk görülen olaya bağlar."""
    def __init__(self):
        self.anchors = []
        self.parent = []
        self.references = {}
        self.texts = {}
        self.controllers = {}
        self.membership = {}

    def root(self, index):
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def add(self, item):
        event = item.event
        references = (item.fingerprint, *item.aliases, *item.origins)
        matches = {self.root(self.references[key]) for key in references if key in self.references}
        # An explicit origin is never inferred from a ticker, engagement or a generic link.
        text = (event.text_hash, event.mint_candidates) if event.text_hash else None
        controller = (event.author_group, event.mint_candidates) if (
            event.author_group and len(event.mint_candidates) == 1
        ) else None
        for index, key in ((self.texts, text), (self.controllers, controller)):
            prior = index.get(key)
            if prior is not None and event.observed_at - self.anchors[prior].event.observed_at <= MAX_AGE:
                matches.add(self.root(prior))
        if matches:
            anchor = min(matches)
            for index in matches:
                self.parent[index] = anchor
        else:
            anchor = len(self.parent)
            self.parent.append(anchor)
            self.anchors.append(item)
        for key in references:
            self.references[key] = anchor
        if text:
            self.texts[text] = anchor
        if controller:
            self.controllers[controller] = anchor
        self.membership[event.event_id] = anchor
        return anchor, not matches

    def members(self, observations):
        grouped = defaultdict(list)
        for item in observations:
            grouped[self.root(self.membership[item.event.event_id])].append(item)
        return grouped


def _wallet_evidence(item, batch, mint, published):
    if not item.wallet_claims:
        return dict(durum=UNKNOWN, alim_teyidi_sayisi=None, ortak_kume=None, kanitlar=[])
    t0 = item.event.observed_at
    rows, ambiguous = trades(batch, mint, published - MAX_AGE, t0, t0, strict=True)
    by_wallet = defaultdict(set)
    refs = set()
    for signature, _, _, wallet, cluster, side in rows:
        key = digest("radar-wallet", wallet)
        if side == "buy" and key in item.wallet_claims:
            by_wallet[key].add(cluster)
            refs.add(evidence_ref("helius", signature))
    known = batch.status == OK and mint is not None and not ambiguous and len(by_wallet) == len(item.wallet_claims)
    shared = None
    if len(by_wallet) > 1 and all(len(groups) == 1 and None not in groups for groups in by_wallet.values()):
        shared = len({next(iter(groups)) for groups in by_wallet.values()}) < len(by_wallet)
    return dict(durum=OK if known else UNKNOWN, alim_teyidi_sayisi=len(by_wallet) if known else None,
                ortak_kume=shared if known else None, kanitlar=sorted(refs) if not ambiguous else [])


def _mint_status(match):
    if match.mint is not None:
        return "VERIFIED"
    if ((match.profile is not None and match.profile.get("canonical") is False)
            or (match.account is not None and match.account.get("account_type") not in (None, "mint"))):
        return "WRONG_MINT"
    return UNKNOWN


def _post_analysis(item, history, confirmations, profiles, mint_accounts, batches, as_of):
    event = item.event
    original_time = item.origin_published_at or event.published_at
    t0 = event.observed_at
    timely = t0 - original_time <= MAX_AGE
    point = replace(event, published_at=original_time) if original_time != event.published_at else event
    match = resolve(point, profiles, mint_accounts)
    before, overall = before_t0(batches["helius"], match.mint, point)
    wallets = _wallet_evidence(item, batches["helius"], match.mint, original_time)
    unknown = []
    if not timely:
        unknown.append(DELAYED)
    if item.relay:
        unknown.append("ORIJINAL_HESAP_TEYIDI_UNKNOWN")
    if item.wallet_claims and wallets["durum"] != OK:
        unknown.append("CUZDAN_IDDIASI_UNKNOWN")
    decision = classify(point, match, history, batches, profiles, before["yayin_ile_gozlem_arasi"], overall,
                        confirmations=confirmations, extra_unknown=unknown)
    if not timely:
        decision["bagimsiz_topluluk_grubu"] = None
    return dict(
        olay=dict(event_id=event.event_id, first_source=item.source_id, published_at=original_time,
                  surfaced_at=event.published_at, fetched_at=event.fetched_at, observed_at=t0,
                  lag_seconds=t0 - original_time, kanit=event.source_url or fixture_ref(item),
                  token_mint=match.mint, mint_status=_mint_status(match)),
        mint_gerekcesi=match.reason, karar=decision, t0_zincir=before, cuzdana_ozel_teyit=wallets,
        golge_sonuclari=evaluate(batches["quotes"], match.mint if timely else None, t0, as_of),
        golge_zincir={f"{minute}dk": after_t0(batches["helius"], match.mint, point, as_of, minute)
                      for minute in HORIZONS},
        timely=timely,
    )


def _group_details(members):
    origins = {origin for item in members for origin in item.origins}
    originals = [item for item in members if not item.relay and origins.intersection((item.fingerprint, *item.aliases))]
    if not originals and not origins:
        originals = [item for item in members if not item.relay]
    first = members[0].event.observed_at
    spread = {item.event.author_id for item in members if item.event.observed_at - first <= COORDINATION_SECONDS}
    return dict(
        kaynaklar=sorted({item.source_id for item in members}),
        ilk_gozlem_kaynaklari=sorted({item.source_id for item in members if item.event.observed_at == first}),
        orijinal_kaynak=originals[0].source_id if originals else None,
        tekrar_sayisi=len(members) - 1,
        koordinasyon_bulgusu="BOT_BENZERI_KOORDINASYON" if len(spread) >= 3 else None,
    )


def _performance(source_id, source_batch, results, members):
    samples = [result for result in results if result["olay"]["first_source"] == source_id]
    rows = source_batch.items
    observed = source_batch.status in (OK, DELAYED) or bool(rows)
    start, end = source_batch.coverage_from, source_batch.coverage_until
    covered = [r for r in results if r["timely"] and start is not None and end is not None
               and start <= r["olay"]["observed_at"] <= end]
    detected = sum(source_id in r["dagilim"]["ilk_gozlem_kaynaklari"] for r in covered)
    mints = Counter(r["olay"]["mint_status"] for r in samples)
    tested_mints = mints["VERIFIED"] + mints["WRONG_MINT"]
    warnings = [r for r in samples if r["karar"]["sinif"] == "SOSYAL_ERKEN_UYARI"]
    resolved_warnings = [r for r in warnings if r["golge_sonuclari"]["30dk"]["durum"] == OK]
    profitable = sum(r["golge_sonuclari"]["30dk"]["net_usdc"] > 0 for r in resolved_warnings)
    distinct = len({r["olay"]["token_mint"] for r in resolved_warnings})
    scores = summarize([r for r in samples if r["timely"]])
    return dict(
        durum=OK if observed else UNKNOWN,
        paylasim_sayisi=len(rows) if observed else None,
        sinyal_sayisi=len(samples) if observed else None,
        tekrar_sayisi=(len(rows) - sum(item.source_id == source_id for item in members)) if observed else None,
        medyan_gecikme_sn=median(item.event.observed_at - item.event.published_at for item in rows) if rows else None,
        ilk_gozlem_kapsam=dict(ilk_gozlemde=detected, evren=len(covered), oran=detected / len(covered))
        if covered else dict(ilk_gozlemde=None, evren=None, oran=None),
        mint=dict(yanlis=mints["WRONG_MINT"], olculen=tested_mints, unknown=mints[UNKNOWN],
                  yanlis_orani=mints["WRONG_MINT"] / tested_mints if tested_mints else None) if samples else None,
        unknown_orani=sum(r["karar"]["sinif"] == "BELIRSIZ" for r in samples) / len(samples) if samples else None,
        net_fark_usdc={horizon: dict(tum_olaylara=row["tum_olaylara_gore_fark_usdc"],
                                    islem_yoka=row["islem_yoka_gore_fark_usdc"], olculen=row["olculen"],
                                    unknown=row["unknown"])
                       for horizon, row in scores.items()} if samples else None,
        uyari_dogrulugu_30dk=dict(uyari=len(warnings), olculen=len(resolved_warnings), pozitif=profitable,
                                 farkli_mint=distinct, oran=(profitable / len(resolved_warnings) if
                                 distinct >= MIN_ACCURACY_MINTS and len(resolved_warnings) == len(warnings) else None))
        if samples else None,
    )


class SocialRadar:
    def __init__(self, sources: SourceReader, evidence: Provider, as_of, *, fixture=False):
        self.sources, self.evidence, self.as_of, self.fixture = sources, evidence, zaman(as_of), fixture
        if self.as_of is None:
            raise ValueError("Geçerli rapor kesim zamanı gerekli.")

    @classmethod
    def from_fixture(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Fixture nesne olmalı.")
        as_of = zaman(data.get("as_of"))
        records, evidence = data.get("sources"), data.get("providers")
        if as_of is None or not isinstance(records, dict) or not isinstance(evidence, dict):
            raise ValueError("Fixture as_of, sources ve providers alanları gerekli.")
        return cls(RecordedSources(records, as_of), FixtureProvider(evidence), as_of, fixture=True)

    def _read_sources(self):
        sources = {}
        for source_id in CATALOG:
            batch = self.sources.read(source_id)
            items = tuple(item for item in batch.items if item.event.observed_at <= self.as_of)
            if batch.last_checked is not None and batch.last_checked > self.as_of:
                # An after-cutoff health snapshot cannot establish earlier source availability.
                batch = SourceBatch(items=items, access_mode=batch.access_mode, enabled=batch.enabled)
            sources[source_id] = replace(batch, items=items)
        return sources

    def _status(self, sources):
        return [batch.describe(CATALOG[source_id], self.as_of) for source_id, batch in sources.items()]

    def source_status(self):
        return self._status(self._read_sources())

    def report(self):
        sources = self._read_sources()
        as_of = self.as_of
        batches = {key: self.evidence.read(key) for key in EVIDENCE_SOURCES}
        coverage = defaultdict(list)
        for source_id, batch in sources.items():
            if batch.coverage_from is not None and batch.coverage_until is not None:
                coverage[CATALOG[source_id].platform].append((batch.coverage_from, batch.coverage_until))
        profiles, mint_accounts = mint_batches(batches)
        observations = sorted(
            (item for batch in sources.values() for item in batch.items if item.event.observed_at <= as_of),
            key=lambda item: (item.event.observed_at, item.relay, item.event.event_id),
        )
        grouped = EventGroups()
        history, analyzed, eligible = [], {}, {}
        latest = {}
        for item in observations:
            anchor, is_new = grouped.add(item)
            event = item.event
            t0 = event.observed_at
            latest[event.source] = t0
            history = [peer for peer in history if peer.observed_at >= t0 - MAX_AGE]
            if is_new:
                for platform in ("x", "telegram"):
                    available = ((platform in latest and latest[platform] >= t0 - MAX_AGE)
                                 or any(start <= t0 <= end for start, end in coverage[platform]))
                    batches[platform] = Batch(OK if available else UNKNOWN)
                confirmations = {peer.event_id for peer in history if eligible.get(peer.event_id)
                                 and grouped.root(grouped.membership[peer.event_id]) != anchor}
                result = _post_analysis(item, history, confirmations, profiles, mint_accounts, batches, as_of)
                analyzed[anchor] = result
                eligible[event.event_id] = (not item.relay and result["timely"]
                                            and result["olay"]["mint_status"] == "VERIFIED")
            history.append(event)
        members = grouped.members(observations)
        results = [dict(analyzed[anchor], dagilim=_group_details(group)) for anchor, group in members.items()]
        roots = [grouped.anchors[anchor] for anchor in members]
        summary = summarize([result for result in results if result["timely"]])
        rejected = Counter(reason for batch in sources.values() for reason in batch.rejected)
        return dict(
            schema_version=1, as_of=as_of, mod="MOCK" if self.fixture else "GOZLEM", read_only=True,
            durum=OK if results else UNKNOWN,
            sources=self._status(sources), reddedilen_olaylar=dict(sorted(rejected.items())), olaylar=results,
            ufuk_ozeti=summary, avantaj="AVANTAJ YOK" if all(r["avantaj"] == "AVANTAJ YOK" for r in summary.values())
            else UNKNOWN,
            kaynak_performansi={source_id: _performance(source_id, batch, results, roots)
                                for source_id, batch in sources.items()},
            api_maliyeti=dict(dis_ag_cagrisi=0, tahmini_usd=0) if self.fixture else None,
        )

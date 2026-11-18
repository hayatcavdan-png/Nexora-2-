"""Gözlem anındaki kararı ve sonradan ölçülen sonuçları ayrı alanlarda sunar."""
from nexora.olcum import zaman

from .chain import after_t0, before_t0
from .events import events_at
from .mint import mint_batches, resolve
from .providers import MAX_AGE, SOURCES, FixtureProvider, Provider
from .risk import classify
from .shadow import HORIZONS, evaluate, n16_links, summarize


def report(fixture):
    if not isinstance(fixture, dict):
        raise ValueError("Fixture nesne olmalı.")
    as_of = zaman(fixture.get("as_of"))
    data = fixture.get("providers")
    if as_of is None or not isinstance(data, dict):
        raise ValueError("Fixture as_of ve providers alanları gerekli.")
    return _report(FixtureProvider(data), as_of)


def _report(provider: Provider, as_of):
    batches = {source: provider.read(source) for source in SOURCES}
    profiles, mint_accounts = mint_batches(batches)
    events, rejected = events_at(batches, as_of)

    results, history = [], []
    for event in events:
        t0 = event.observed_at
        history = [item for item in history if t0 - MAX_AGE <= item.observed_at]
        match = resolve(event, profiles, mint_accounts)
        before, overall = before_t0(batches["helius"], match.mint, event)
        decision = classify(event, match, history, batches, profiles, before["yayin_ile_gozlem_arasi"], overall)
        history.append(event)
        event_data = dict(
            event_id=event.event_id, source=event.source, source_id=event.source_id, source_url=event.source_url,
            author_id=event.author_id, published_at=event.published_at, observed_at=t0, text_hash=event.text_hash,
            token_mint=match.mint, token_match_confidence=match.status, metrics=event.metrics, fetched_at=event.fetched_at,
            provenance=event.provenance, t0=t0, yayin_gozlem_gecikmesi_sn=t0 - event.published_at,
        )
        results.append(dict(
            olay=event_data, mint_gerekcesi=match.reason, karar=decision, t0_zincir=before,
            golge_sonuclari=evaluate(batches["quotes"], match.mint, t0, as_of),
            golge_zincir={f"{minute}dk": after_t0(batches["helius"], match.mint, event, as_of, minute)
                          for minute in HORIZONS},
            n16=n16_links(batches["n16"], batches["helius"], event, match.mint, as_of),
        ))
    summary = summarize(results)
    return dict(
        mod="OFFLINE_GOLGE", as_of=as_of, durum="OK" if results else "UNKNOWN",
        saglayicilar={s: dict(durum=b.status, kayit_sayisi=len(b.items)) for s, b in batches.items()},
        reddedilen_olaylar=rejected, olaylar=results, ufuk_ozeti=summary,
        avantaj="AVANTAJ YOK" if any(r["avantaj"] == "AVANTAJ YOK" for r in summary.values()) else "UNKNOWN",
        api_maliyeti=dict(dis_ag_cagrisi=0, tahmini_usd=0),
    )

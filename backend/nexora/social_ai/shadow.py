"""Sonuç ve N16 karşılaştırması. Bu kayıtlar t0 sınıflandırmasına girmez."""
from collections import defaultdict
from math import fsum

from nexora.olcum import GIRIS_TOLERANS, UFUKLAR, etiket_sonucu, ham_miktar, net_getiri, politika, sayi, zaman

from .chain import trades
from .events import evidence_ref, identifier
from .providers import MAX_AGE, known_times

HORIZONS = {5: UFUKLAR["5dk"][1], 15: 120, 30: UFUKLAR["30dk"][1], 60: 300}
MAX_ENTRY_USDC = 5.0
NET_USDC_DECIMALS = 6


def _first_quote(batch, mint, side, due, tolerance, as_of, qty=None):
    choices = defaultdict(list)
    for row in batch.items:
        if row.get("mint") != mint or row.get("side") != side:
            continue
        if qty is not None and ham_miktar(row.get("qty_raw")) != qty:
            continue
        clocks = known_times(row, min(as_of, due + tolerance), earliest=due, field="measured_at", strict=False)
        if clocks:
            measured, fetched = clocks
            choices[fetched, measured].append(row)
    if not choices:
        return None
    rows = choices[min(choices)]
    return rows[0] if all(row == rows[0] for row in rows) else None


def _quote_values(row):
    notional, fee, slippage, impact = (sayi(row.get(k)) for k in (
        "usdc", "network_fee_usdc", "slippage_bps", "price_impact_bps"
    ))
    qty = ham_miktar(row.get("qty_raw"))
    if (qty is None or notional is None or notional <= 0 or fee is None or fee < 0
            or slippage is None or not 0 <= slippage < 10_000 or impact is None or not 0 <= impact < 10_000):
        return None
    return qty, notional, fee, slippage, impact


def _result(due, reason, entry=None, exit_=None, net=None):
    def detail(row):
        if row is None:
            return None
        qty, usdc, fee, slip, impact = _quote_values(row)
        measured, fetched = zaman(row["measured_at"]), zaman(row["fetched_at"])
        return dict(measured_at=measured, fetched_at=fetched, qty_raw=str(qty), usdc=usdc, network_fee_usdc=fee,
                    slippage_bps=slip, price_impact_bps=impact, kanit=evidence_ref(
                        "quotes", (row["mint"], row["side"], measured, fetched, qty)
                    ))

    return dict(durum="OK" if net is not None else "UNKNOWN", gerekce=reason, vade=due,
                giris=detail(entry), cikis=detail(exit_),
                net_usdc=round(net[0], NET_USDC_DECIMALS) if net is not None else None,
                getiri_pct=net[1] if net is not None else None)


def evaluate(batch, mint, t0, as_of):
    entry = _first_quote(batch, mint, "buy", t0, GIRIS_TOLERANS, as_of) if mint else None
    entry_values = _quote_values(entry) if entry else None
    outcomes = {}
    for minutes, tolerance in HORIZONS.items():
        due = t0 + minutes * 60
        key = f"{minutes}dk"
        if mint is None or batch.status != "OK" or as_of < due:
            reason = "UFUK_BEKLIYOR" if mint and batch.status == "OK" else "MINT_VEYA_TEKLIF_UNKNOWN"
            outcomes[key] = _result(due, reason)
            continue
        if not entry or entry.get("executable") is not True or not entry_values or entry_values[1] > MAX_ENTRY_USDC:
            outcomes[key] = _result(due, "GIRIS_TEKLIFI_UNKNOWN")
            continue
        qty, spend, entry_fee, _, _ = entry_values
        exit_ = _first_quote(batch, mint, "sell", due, tolerance, as_of, qty)
        if exit_ is None or exit_.get("executable") is not True:
            reason = "CIKIS_YOLU_YOK" if exit_ is not None and exit_.get("executable") is False else "CIKIS_TEKLIFI_UNKNOWN"
            outcomes[key] = _result(due, reason, entry)
            continue
        exit_values = _quote_values(exit_)
        net = net_getiri(spend, exit_values[1], entry_fee + exit_values[2]) if exit_values else None
        outcomes[key] = _result(due, "MALIYET_DAHIL_TEKLIF" if net else "TEKLIF_TUTARSIZ",
                                entry, exit_ if net else None, net)
    return outcomes


def n16_links(batch, helius, event, mint, as_of):
    if batch.status != "OK" or helius.status != "OK" or mint is None:
        return dict(durum="UNKNOWN", kayitlar=[])
    t0 = event.observed_at
    start, end = t0 - MAX_AGE, t0 + MAX_AGE
    rows, conflict = trades(helius, mint, start, end, as_of, strict=False)
    if conflict:
        return dict(durum="UNKNOWN", kayitlar=[])
    purchases = {r[0]: r[1:3] for r in rows if r[5] == "buy"}
    matches = defaultdict(list)
    for row in batch.items:
        event_row, labels = row.get("olay"), row.get("etiketler")
        if not isinstance(event_row, dict) or not isinstance(labels, dict) or event_row.get("token") != mint:
            continue
        event_id, sig = identifier(event_row.get("event_id")), identifier(event_row.get("sig"))
        block_time, n16_t0, saved = (zaman(event_row.get(k)) for k in ("block_time", "ts", "kayit_ts"))
        proof = purchases.get(sig)
        if (event_id and proof and n16_t0 is not None and saved is not None and start <= n16_t0 <= min(end, saved)
                and saved <= as_of
                and block_time == proof[0] and block_time <= n16_t0):
            matches[event_id].append((event_row, labels))
    linked = []
    for event_id, versions in sorted(matches.items()):
        if any(row != versions[0] for row in versions):
            continue
        event_row, labels = versions[0]
        n16_t0 = zaman(event_row["ts"])
        results = {}
        for horizon in (*UFUKLAR, "kaynak"):
            label = labels.get(horizon)
            if label is not None and (not isinstance(label, dict) or label.get("event_id") != event_id
                                      or label.get("ufuk") != horizon):
                results[horizon] = dict(durum="UNKNOWN", net_usdc=None)
                continue
            status, value, _ = etiket_sonucu(event_row, label, horizon, as_of)
            results[horizon] = dict(durum="OK" if status == "OK" else "UNKNOWN",
                                    net_usdc=round(value, 6) if status == "OK" else None)
        signature = event_row["sig"]
        block_time, fetched_at = purchases[signature]
        linked.append(dict(kanit=evidence_ref("n16", event_id), t0=n16_t0, t0_farki_sn=n16_t0 - t0,
                           zincir_kaniti=evidence_ref("helius", signature), block_time=block_time,
                           fetched_at=fetched_at, sonuclar=results))
    return dict(durum="OK" if linked else "UNKNOWN", kayitlar=linked)


def summarize(events):
    summary = {}
    for minutes in HORIZONS:
        key = f"{minutes}dk"
        nets = [e["golge_sonuclari"][key]["net_usdc"] for e in events]
        classes = [e["karar"]["sinif"] for e in events]
        choices = [None if c == "BELIRSIZ" else c == "SOSYAL_ERKEN_UYARI" for c in classes]
        selected = politika(choices, nets)
        baseline = politika([True] * len(nets), nets)
        no_action = politika([False] * len(nets), nets)
        vs_no_action, vs_all = None, None
        if selected["sinyal_basi_usdc"] is not None:
            # Farkları, rapor için yuvarlanan politika ortalamaları yerine olayların netlerinden hesapla.
            selected_total = round(fsum(net for choice, net in zip(choices, nets) if choice is True),
                                   NET_USDC_DECIMALS)
            vs_no_action = selected_total / len(nets)
            if baseline["sinyal_basi_usdc"] is not None:
                # Seçilen işlemler iki politikada da aynı olduğu için farkı yalnızca atlanan işlemler belirler.
                skipped_total = round(fsum(net for choice, net in zip(choices, nets) if choice is False),
                                      NET_USDC_DECIMALS)
                vs_all = -skipped_total / len(nets)

        advantage = "UNKNOWN"
        if vs_all is None or not 0 < selected["secili"] < len(nets):
            reason = "KARSILASTIRMA_YETERSIZ"
        elif vs_all <= 0 or vs_no_action <= 0:
            advantage = "AVANTAJ YOK"
            reason = "NET_FARK_POZITIF_DEGIL"
        else:
            reason = "POZITIF_FARK_DOGRULANMADI"
        summary[key] = dict(
            olculen=sum(net is not None for net in nets), unknown=sum(net is None for net in nets),
            sosyal_erken_uyari=selected, tum_olaylar=baseline, islem_yok=no_action,
            tum_olaylara_gore_fark_usdc=vs_all, islem_yoka_gore_fark_usdc=vs_no_action,
            avantaj=advantage, avantaj_gerekcesi=reason,
        )
    return summary

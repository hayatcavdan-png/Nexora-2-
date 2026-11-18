"""Helius mock işlemlerini iki zaman damgasıyla ve ilişkili cüzdanları gruplayarak özetler."""
from collections import defaultdict

from .events import evidence_ref, identifier
from .providers import MAX_AGE, known_times


def independent_members(pairs):
    """Bir kimlik çelişkili gruplara düşüyorsa bu grupları bağımsız teyit sayma."""
    by_member = defaultdict(set)
    for member, group in pairs:
        by_member[member].add(group)
    conflicts = {g for groups in by_member.values() if len(groups) > 1 for g in groups if g}
    return {g for groups in by_member.values() for g in groups if g} - conflicts, bool(conflicts)


def trades(batch, mint, start, end, cutoff, *, strict):
    signatures = defaultdict(set)
    for row in batch.items:
        if mint is None or row.get("kind") != "trade" or row.get("mint") != mint:
            continue
        clocks = known_times(row, cutoff, earliest=0, field="block_time", strict=strict)
        signature, wallet = identifier(row.get("signature")), identifier(row.get("wallet"))
        side = row.get("side")
        if clocks and signature and wallet and side in ("buy", "sell"):
            # Aynı işlemin geç tekrar çekimi zaman veya ilişkileri geriye dönük değiştirmez.
            signatures[signature].add((*clocks, wallet, identifier(row.get("cluster_id")), side))
    result, conflict = [], False
    for signature, versions in sorted(signatures.items()):
        first = min(row[1] for row in versions)
        rows = [row for row in versions if row[1] == first]
        inside = [row for row in rows if start <= row[0] <= end]
        if inside:
            if len(rows) == 1:
                result.append((signature, *inside[0]))
            else:
                conflict = True
    return result, conflict


def _flow(rows, start, end, cutoff, available):
    groups, conflict = independent_members((r[3], r[4]) for r in rows if r[5] == "buy")
    wallet_tags = [(r[3], r[4]) for r in rows]
    related = (len(wallet_tags) > len({wallet for wallet, _ in wallet_tags})
               or len({(w, g) for w, g in wallet_tags if g}) > len({g for _, g in wallet_tags if g}))
    return dict(
        durum="OK" if available else "UNKNOWN",
        baslangic=start, bitis=end, veri_kesim_zamani=cutoff,
        alim_sayisi=sum(r[5] == "buy" for r in rows) if available else None,
        satim_sayisi=sum(r[5] == "sell" for r in rows) if available else None,
        bagimsiz_alici_grubu=len(groups) if available else None,
        grup_bilgisi_eksik=conflict or any(r[4] is None for r in rows) if available else None,
        iliskili_cuzdan=related if available else None,
        islemler=[dict(kanit=evidence_ref("helius", sig), block_time=block, fetched_at=fetched, side=side)
                  for sig, block, fetched, _, _, side in sorted(rows, key=lambda r: (r[1], r[2], r[0]))],
    )


def before_t0(batch, mint, event):
    published, t0 = event.published_at, event.observed_at
    start = published - MAX_AGE
    available = batch.status == "OK" and mint is not None
    rows, conflict = trades(batch, mint, start, t0, t0, strict=True)
    before = _flow([r for r in rows if r[1] < published], start, published, t0, available and not conflict)
    during = _flow([r for r in rows if r[1] >= published], published, t0, t0, available and not conflict)
    combined = _flow(rows, start, t0, t0, available and not conflict)
    # Yayın sınırını aşan tekrar ve grup çelişkileri de risk hesabına girer.
    return dict(yayindan_once=before, yayin_ile_gozlem_arasi=during), combined


def after_t0(batch, mint, event, as_of, minutes):
    t0 = event.observed_at
    end = t0 + minutes * 60
    cutoff = min(as_of, end)
    rows, conflict = trades(batch, mint, t0, end, cutoff, strict=False)
    available = batch.status == "OK" and mint is not None and as_of >= end
    return _flow([r for r in rows if r[1] > t0], t0, end, cutoff, available and not conflict)

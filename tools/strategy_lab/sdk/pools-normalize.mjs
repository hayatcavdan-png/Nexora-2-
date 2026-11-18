/** Pure bounded metadata extraction; no orders, keys or network. */
const B58 = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;
export function validAddress(raw) {
  return typeof raw === 'string' && B58.test(raw);
}
export function cleanPools(source, raw, mint, max = 20) {
  if (!['raydium', 'orca'].includes(source) || !validAddress(mint)) return [];
  if (!Array.isArray(raw)) return [];
  const out = [];
  const seen = new Set();
  for (const pool of raw.slice(0, 150)) {
    if (typeof pool !== 'object' || pool === null) continue;
    const id = String(pool.id ?? pool.address ?? '');
    const mintA = String(pool.mintA?.address ?? pool.mintA ?? pool.tokenMintA ?? '');
    const mintB = String(pool.mintB?.address ?? pool.mintB ?? pool.tokenMintB ?? '');
    if (!validAddress(id) || !validAddress(mintA) || !validAddress(mintB) ||
        ![mintA, mintB].includes(mint) || seen.has(id)) continue;
    seen.add(id);
    out.push({ source, pool_id: id, mint, status: 'UNVERIFIED_POOL_OBSERVATION' });
    if (out.length >= max) break;
  }
  return out;
}

/** Optional read-only Raydium SDK V2 + Orca Whirlpools CLI.

 Usage: NEXORA_SDK_READONLY=1 SOLANA_RPC_URL=https://... node scan.mjs MINT
 No owner, keypair, wallet, createPool, swap or execute methods.
 Default is OFF. Requires optional npm dependencies.
 */
import { validAddress, cleanPools } from './pools-normalize.mjs';

const mint = process.argv[2];
const enabled = process.env.NEXORA_SDK_READONLY === '1';
const rpcUrl = process.env.SOLANA_RPC_URL ?? '';
const empty = (status) => ({
  schema_version: 1, mode: 'SDK_READ_ONLY', status,
  real_order: false, pools: [], warnings: ['observations_not_buy_signals'],
});
function output(value) { process.stdout.write(JSON.stringify(value) + '\n'); }
if (!enabled) { output(empty('DISABLED')); process.exit(0); }
if (!validAddress(mint) || !rpcUrl.startsWith('https://')) {
  output(empty('INVALID_MINT_OR_RPC')); process.exit(0);
}
const results = [];
const providers = {};
try {
  // Raydium SDK uses the public API. Supply no signing identity.
  const { Raydium } = await import('@raydium-io/raydium-sdk-v2');
  const { Connection } = await import('@solana/web3.js');
  const sdk = await Raydium.load({
    connection: new Connection(rpcUrl, 'finalized'),
    disableLoadToken: true,
    disableFeatureCheck: true,
  });
  const response = await sdk.api.fetchPoolByMints({
    mint1: mint, sort: 'liquidity', order: 'desc', page: 1, pageSize: 20,
  });
  results.push(...cleanPools('raydium', response?.data ?? [], mint));
  providers.raydium = 'READ_ONLY_OK';
} catch (_) {
  providers.raydium = 'UNAVAILABLE';
}
try {
  // Orca's generated on-chain client fetches Whirlpool accounts by mint.
  const { createSolanaRpc, address } = await import('@solana/kit');
  const { fetchAllWhirlpoolWithFilter, whirlpoolTokenMintAFilter,
          whirlpoolTokenMintBFilter } = await import('@orca-so/whirlpools-client');
  const rpc = createSolanaRpc(rpcUrl);
  const a = await fetchAllWhirlpoolWithFilter(rpc, whirlpoolTokenMintAFilter(address(mint)));
  const b = await fetchAllWhirlpoolWithFilter(rpc, whirlpoolTokenMintBFilter(address(mint)));
  const convert = (item) => ({
    id: String(item.address),
    tokenMintA: String(item.data?.tokenMintA ?? ''),
    tokenMintB: String(item.data?.tokenMintB ?? ''),
  });
  results.push(...cleanPools('orca', [...a, ...b].slice(0, 80).map(convert), mint));
  providers.orca = 'READ_ONLY_OK';
} catch (_) {
  providers.orca = 'UNAVAILABLE';
}
const seen = new Set();
const pools = results.filter((x) => {
  if (seen.has(x.source + ':' + x.pool_id)) return false;
  seen.add(x.source + ':' + x.pool_id); return true;
}).slice(0, 40);
output({
  schema_version: 1, mode: 'SDK_READ_ONLY',
  status: Object.values(providers).includes('READ_ONLY_OK') ? 'PARTIAL_OR_OK' : 'PROVIDERS_UNAVAILABLE',
  providers, real_order: false, pools,
  warnings: ['not_new_pool_proof', 'not_liquidity_proof', 'do_not_trade'],
});

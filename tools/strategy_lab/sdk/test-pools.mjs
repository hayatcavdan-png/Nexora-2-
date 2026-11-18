import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cleanPools, validAddress } from './pools-normalize.mjs';
const M = '4wBqpZM9xaSheZzJSMawUKKwhdpChKbZ5eu5ky4Vigw';
const B = 'So11111111111111111111111111111111111111112';
test('SDK pool parser accepts only exact mint and addresses', () => {
  const pools = cleanPools('raydium', [
    { id: B, mintA: { address: M }, mintB: { address: B } },
    { id: B, mintA: { address: M }, mintB: { address: B } },
    { id: 'bad', mintA: { address: M }, mintB: { address: B } },
    { id: M, mintA: { address: B }, mintB: { address: B } }
  ], M);
  assert.equal(pools.length, 1);
  assert.deepEqual(Object.keys(pools[0]).sort(), ['mint','pool_id','source','status']);
  assert.equal(pools[0].source, 'raydium');
});
test('Orca parsed account fields and unsafe input are rejected', () => {
  const pools = cleanPools('orca', [{address: B, tokenMintA: M, tokenMintB: B}], M);
  assert.equal(pools.length, 1);
  assert.equal(cleanPools('orca', [{address: B, tokenMintA: B, tokenMintB: B}], M).length, 0);
  assert.equal(validAddress('https://t.me/whatever'), false);
  assert.equal(cleanPools('telegram', [], M).length, 0);
});

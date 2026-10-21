import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { receiptRows, receiptTotals, selectRows } from '../../docs/explore/receipts.mjs';
const receipt = JSON.parse(await readFile(new URL('../../docs/demo/evidence/FIXTURE_SUITE_EVAL_2026-10-18.json', import.meta.url)));
const rows = receiptRows(receipt);
test('original receipt totals are derived, not separately authored', () => {
  assert.deepEqual(receiptTotals(rows), { runs: 21, claims: 84, incidents: 8, withheld: 12 });
});
test('all recorded outcomes remain visible', () => {
  assert.equal(selectRows(rows).length, 21);
  assert.equal(selectRows(rows, '', 'verified_complete').length, 9);
  assert.equal(selectRows(rows, '', 'uncertain').length, 10);
  assert.equal(selectRows(rows, '', 'incomplete').length, 2);
});
test('search is case insensitive and supports evidence', () => {
  assert.ok(selectRows(rows, ' ACCEPTANCE_SURFACE_MODIFIED ').length > 0);
  assert.equal(selectRows(rows, 'not-an-existing-case').length, 0);
  assert.ok(selectRows(rows, 'pytest', 'uncertain').every(x => x.completion_status === 'uncertain'));
});
test('wrong provenance is rejected rather than relabeled', () => {
  assert.throws(() => receiptRows({ ...receipt, scope: 'live' }));
});
test('invalid counts and duplicate cases fail closed', () => {
  assert.throws(() => receiptRows({ ...receipt, fixtures: [...receipt.fixtures, receipt.fixtures[0]] }));
  for (const bad of [-1, NaN, 1.5, '4']) {
    assert.throws(() => receiptRows({ ...receipt, fixtures: [{ ...rows[0], claims_adjudicated: bad }] }));
  }
});
test('HTML-like evidence stays plain data', () => {
  const payload = '<img src=x onerror=alert(1)>';
  assert.equal(receiptRows({ ...receipt, fixtures: [{ ...rows[0], evidence_strings: [payload] }] })[0].evidence_strings[0], payload);
});
test('UI uses text nodes and has no worker-control endpoints', async () => {
  const source = await readFile(new URL('../../docs/explore/app.mjs', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /innerHTML|outerHTML|insertAdjacentHTML|\/v1\/|7420|WebSocket/);
  assert.match(source, /node\.textContent = text/);
  assert.match(source, /credentials: 'omit'/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseHTML } from 'linkedom';

const html = await readFile(new URL('../../../docs/explore/index.html', import.meta.url), 'utf8');
const receipt = JSON.parse(await readFile(new URL('../../../docs/demo/evidence/FIXTURE_SUITE_EVAL_2026-10-18.json', import.meta.url)));
async function setup(suffix, fail = false) {
  const { document, window } = parseHTML(html);
  Object.defineProperty(document.querySelector('#status'), 'value', { value: 'all', writable: true });
  const location = { hash: '#tampered_acceptance_eval' };
  const writes = [];
  const history = {
    pushState(_state, _title, fragment) { writes.push(fragment); location.hash = fragment; },
    replaceState(_state, _title, fragment) { location.hash = fragment; },
  };
  Object.assign(globalThis, { document, window, history, location, fetch: async () => ({ ok: !fail, status: fail ? 404 : 200, json: async () => receipt }) });
  await import(new URL(`../../../docs/explore/app.mjs?${suffix}`, import.meta.url));
  await new Promise(resolve => setImmediate(resolve));
  return { document, window, location, writes };
}
test('selection retains its button node, filters explain retained details, and fragments navigate', async () => {
  const { document, window, location, writes } = await setup('navigation');
  assert.match(document.querySelector('#totals').textContent, /21 cases \/ 84 claims/);
  const buttons = [...document.querySelectorAll('#cases button')];
  assert.equal(buttons.length, 21);
  const target = buttons.find(button => button.dataset.fixture === 'captured_live_eval');
  target.click();
  assert.equal(document.querySelector('#cases button[data-fixture="captured_live_eval"]'), target, 'do not destroy the active/focused button');
  assert.equal(target.getAttribute('aria-pressed'), 'true');
  assert.equal(writes.length, 1);
  target.click();
  assert.equal(writes.length, 1, 'same selection should not duplicate history');
  const search = document.querySelector('#search');
  search.value = 'no matching case here';
  search.dispatchEvent(new window.Event('input'));
  assert.match(document.querySelector('#message').textContent, /0 of 21/);
  assert.match(document.querySelector('#selection-note').textContent, /outside the current filter/);
  search.value = '';
  search.dispatchEvent(new window.Event('input'));
  assert.equal(document.querySelector('#selection-note').textContent, '');
  location.hash = '#premature_stop_eval';
  window.dispatchEvent(new window.Event('hashchange'));
  assert.match(document.querySelector('#detail h2').textContent, /premature stop eval/);
  location.hash = '#captured_live_eval';
  window.dispatchEvent(new window.Event('popstate'));
  assert.match(document.querySelector('#detail h2').textContent, /captured live eval/);
  assert.equal(writes.length, 1, 'history navigation must not create another entry');
  const heading = document.querySelector('#detail h2');
  window.dispatchEvent(new window.Event('hashchange'));
  assert.equal(document.querySelector('#detail h2'), heading, 'paired history events must not announce the same detail twice');
});
test('receipt failure shows an honest empty state, not loading or fabricated results', async () => {
  const { document } = await setup('failure', true);
  assert.equal(document.querySelector('#totals').textContent, 'Receipt unavailable');
  assert.equal(document.querySelectorAll('#cases button').length, 0);
  assert.match(document.querySelector('#detail').textContent, /No results loaded/);
  assert.match(document.querySelector('#message').textContent, /404/);
});

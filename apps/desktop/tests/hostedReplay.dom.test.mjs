import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { parseHTML } from 'linkedom';
import ts from 'typescript';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

// Node's type stripping does not transform JSX. Transpile the production modules
// with the already-installed TypeScript compiler; no mock component/client logic.
const temp = await mkdtemp(fileURLToPath(new URL('./.hosted-dom-', import.meta.url)));
for (const name of ['HostedReplay.tsx', 'ResultPanel.tsx', 'client.ts', 'result.ts']) {
  const source = await readFile(new URL(`../src/hosted/${name}`, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } });
  await writeFile(join(temp, name.replace(/\.tsx?$/, '.mjs')), outputText.replace(/from "(\.\/[^".]+)(?:\.ts)?"/g, 'from "$1.mjs"'));
}
const { HostedReplay } = await import(pathToFileURL(join(temp, 'HostedReplay.mjs')));
const { ReplayClient } = await import(pathToFileURL(join(temp, 'client.mjs')));
after(() => rm(temp, { recursive: true, force: true }));

const fixtureIds = ['premature_stop_eval', 'tampered_acceptance_eval'];
const results = Object.fromEntries(await Promise.all(fixtureIds.map(async (id) => [id, JSON.parse(await readFile(new URL(`../src/hosted/test-fixtures/${id}.json`, import.meta.url), 'utf8'))])));
const labels = { replay: true, not_live_control: true };
const catalogue = (available = true) => ({ ...labels, execution_available: available, fixtures: fixtureIds.map((id) => ({ ...labels, id, title: id === fixtureIds[0] ? 'False completion without tests' : 'Reward hacking: edited acceptance test' })) });
const visitor = { visitor_token: 'A'.repeat(43), expires_in_seconds: 900 };
const run = (fixture = fixtureIds[0], state = 'running', id = 'run-1') => ({ ...labels, fixture_id: fixture, state, run_id: id, error: null });
const json = (body, status = 200) => Response.json(body, { status });
function deferred() { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; }
async function flush() { await act(async () => { await new Promise((resolve) => setImmediate(resolve)); }); }
async function mount(t, handler, options = {}) {
  const { document, window } = parseHTML('<html><body><div id="root"></div></body></html>');
  const previous = Object.fromEntries(['document', 'window', 'IS_REACT_ACT_ENVIRONMENT'].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  Object.assign(globalThis, { document, window, IS_REACT_ACT_ENVIRONMENT: true });
  const calls = [];
  let key = 0;
  const client = new ReplayClient({ wait: async () => {}, key: () => `attempt-${++key}`, ...options, fetcher: async (url, init) => {
    calls.push({ url, init });
    assert.ok(url.startsWith('/api/replay/'), 'only the restricted API is called');
    return handler(url, init, calls);
  } });
  const root = createRoot(document.getElementById('root'));
  t.after(async () => {
    await act(async () => root.unmount());
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  });
  await act(async () => root.render(React.createElement(HostedReplay, { client })));
  await flush();
  const buttons = () => [...document.querySelectorAll('button')];
  const replay = (index = 0) => document.querySelectorAll('.scenario button')[index];
  const button = (text) => { const found = buttons().find((b) => b.textContent === text); assert.ok(found, `button ${text} exists`); return found; };
  async function click(element, times = 1) { await act(async () => { for (let i = 0; i < times; i++) element.click(); }); await flush(); }
  return { document, calls, replay, button, click, text: () => document.body.textContent, result: () => document.querySelector('.result-panel') };
}
function standard(extra, available = true) {
  return (url, init, calls) => {
    if (url.endsWith('/fixtures')) return json(catalogue(available));
    if (url.endsWith('/visitors')) return json(visitor, 201);
    return extra(url, init, calls);
  };
}

for (const fixture of fixtureIds) test(`mounted ${fixture}: catalogue → running → completed → validated evidence`, async (t) => {
  const poll = deferred(); const evidence = deferred();
  const ui = await mount(t, standard((url, init) => {
    if (url.endsWith('/runs') && init.method === 'POST') return json(run(fixture), 202);
    if (url.endsWith('/result')) return evidence.promise;
    return json(run(fixture, 'completed'));
  }), { wait: () => poll.promise });
  assert.equal(ui.document.querySelectorAll('.scenario').length, 2);
  assert.equal(ui.result(), null);
  await ui.click(ui.replay(fixtureIds.indexOf(fixture)), 2);
  assert.match(ui.text(), /Reading the recording/);
  assert.equal(ui.result(), null, 'running is not a verdict');
  assert.ok(ui.replay().disabled);
  assert.equal(ui.calls.filter((c) => c.url.endsWith('/runs')).length, 1, 'rapid repeat clicks produce one start');
  await act(async () => poll.resolve()); await flush();
  assert.match(ui.text(), /Execution ended/);
  assert.equal(ui.result(), null, 'completed status alone is not evidence');
  assert.match(ui.text(), /No verdict without a result payload/);
  await act(async () => evidence.resolve(json(results[fixture]))); await flush();
  assert.ok(ui.result());
  assert.match(ui.result().textContent, /Model inference: not attempted/);
  assert.match(ui.result().textContent, /No live worker was controlled/);
  assert.match(ui.result().textContent, /worst-first/);
  assert.match(ui.result().textContent, /not a chronological claim history/);
  assert.deepEqual([...ui.document.querySelectorAll('.claim-list li span')].map((n) => n.textContent), results[fixture].claim_verdicts.map((c) => c.claim));
  assert.deepEqual([...ui.document.querySelectorAll('.evidence-list li')].map((n) => n.textContent), results[fixture].evidence_summary);
  assert.equal(ui.document.querySelectorAll('.verification-list li').length, results[fixture].verification_sequence.length);
  if (fixture === fixtureIds[1]) assert.match(ui.result().textContent, /tests\/test_core.py/);
  assert.equal(ui.replay().disabled, false);
});

test('unavailable runner keeps scenarios visible but disables starts', async (t) => {
  const ui = await mount(t, standard(() => { throw new Error('must not start'); }, false));
  assert.match(ui.text(), /No replay has run and no result is being simulated/);
  assert.equal(ui.result(), null);
  assert.ok(ui.replay().disabled);
  await ui.click(ui.replay());
  assert.equal(ui.calls.length, 1);
  await ui.click(ui.button('Check availability again'));
  assert.equal(ui.calls.length, 2);
  assert.ok(ui.calls.every((c) => c.url.endsWith('/fixtures')));
});

test('interrupted polling checks the same run without another start', async (t) => {
  let polls = 0;
  const ui = await mount(t, standard((url) => {
    if (url.endsWith('/runs')) return json(run(), 202);
    if (url.endsWith('/result')) return json(results[fixtureIds[0]]);
    if (++polls === 1) throw new TypeError('network interrupted');
    return json(run(fixtureIds[0], 'completed'));
  }));
  await ui.click(ui.replay());
  assert.match(ui.text(), /Status needs a check/);
  assert.equal(ui.result(), null);
  await ui.click(ui.button('Check same attempt'), 2);
  assert.ok(ui.result());
  assert.equal(ui.calls.filter((c) => c.url.endsWith('/runs')).length, 1);
  assert.equal(ui.calls.filter((c) => c.url.endsWith('/visitors')).length, 1);
  assert.equal(polls, 2);
});

for (const [label, response, message] of [
  ['malformed', () => json({ ...results[fixtureIds[0]], inference_status: 'attempted' }), /unexpected response/],
  ['missing', () => json({ detail: 'result_unavailable' }, 404), /no result payload/],
]) test(`${label} result never renders claim evidence`, async (t) => {
  const ui = await mount(t, standard((url) => url.endsWith('/result') ? response() : json(run(fixtureIds[0], 'completed'))));
  await ui.click(ui.replay());
  assert.equal(ui.result(), null);
  assert.equal(ui.document.querySelectorAll('.claim-list li').length, 0);
  assert.match(ui.text(), message);
  assert.match(ui.text(), /No verdict/);
});

test('expired result access requires explicit new visit and does not auto-start', async (t) => {
  const ui = await mount(t, standard((url) => url.endsWith('/result') ? json({ detail: 'visitor_expired_or_unknown' }, 401) : json(run(fixtureIds[0], 'completed'))));
  await ui.click(ui.replay());
  assert.match(ui.text(), /Access expired/);
  assert.match(ui.text(), /does not recover or cancel/);
  assert.ok(ui.replay().disabled);
  assert.equal(ui.result(), null);
  const before = ui.calls.length;
  await ui.click(ui.button('Start a new visit'));
  assert.equal(ui.calls.length, before);
  assert.equal(ui.result(), null);
  assert.equal(ui.document.querySelector('.run-id'), null);
  assert.equal(ui.replay().disabled, false);
});

test('fifth-run quota recovery clears evidence and requires an intentional next replay', async (t) => {
  let starts = 0; let visits = 0;
  const ui = await mount(t, (url) => {
    if (url.endsWith('/fixtures')) return json(catalogue());
    if (url.endsWith('/visitors')) { visits++; return json(visitor, 201); }
    if (url.endsWith('/result')) return json(results[fixtureIds[0]]);
    starts++;
    return starts === 5 ? json({ detail: 'visitor_run_limit' }, 429) : json(run(fixtureIds[0], 'completed', `run-${starts}`));
  });
  for (let i = 0; i < 4; i++) { await ui.click(ui.replay()); assert.ok(ui.result()); }
  await ui.click(ui.replay());
  assert.match(ui.text(), /This visit’s limit is reached/);
  assert.match(ui.text(), /No new run was admitted/);
  assert.equal(ui.result(), null, 'old evidence is not left attached to an unsuccessful new attempt');
  assert.equal(visits, 1);
  assert.ok(ui.replay().disabled);
  const before = ui.calls.length;
  await ui.click(ui.button('Start a new visit'));
  assert.equal(ui.calls.length, before, 'reset does not create a visitor or run automatically');
  assert.equal(ui.result(), null);
  assert.equal(ui.document.querySelector('.run-id'), null);
  assert.equal(ui.replay().disabled, false);
  await ui.click(ui.replay());
  assert.equal(visits, 2);
  assert.equal(starts, 6);
  assert.ok(ui.result());
});

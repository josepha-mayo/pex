import { receiptRows, selectRows, receiptTotals } from './receipts.mjs';
const receiptURL = '../demo/evidence/FIXTURE_SUITE_EVAL_2026-10-18.json';
const list = document.querySelector('#cases');
const search = document.querySelector('#search');
const status = document.querySelector('#status');
const detail = document.querySelector('#detail');
const message = document.querySelector('#message');
let rows = [];
let selected = null;
function element(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}
function show(row, navigation = 'push') {
  selected = row.fixture;
  detail.replaceChildren();
  detail.append(element('p', 'RECORDED CASE · NOT A LIVE RUN', 'eyebrow'));
  detail.append(element('h2', row.fixture.replaceAll('_', ' ')));
  detail.append(element('p', row.completion_status.replaceAll('_', ' '), 'verdict'));
  detail.append(element('p', row.completion_reason || 'No reason recorded.'));
  detail.append(element('p', `${row.claims_adjudicated} adjudicated claims · ${row.integrity_incidents} integrity incidents`));
  detail.append(element('h3', 'Intervention sequence'));
  const sequence = element('ol', '');
  row.interventions.forEach(action => sequence.append(element('li', action.replaceAll('_', ' '))));
  detail.append(sequence, element('h3', 'Evidence recorded'));
  const evidence = element('ul', '');
  row.evidence_strings.forEach(value => evidence.append(element('li', value)));
  if (!row.evidence_strings.length) evidence.append(element('li', 'No evidence strings were recorded for this case.'));
  detail.append(evidence);
  const link = element('a', 'Inspect the original JSON receipt ↗');
  link.href = receiptURL;
  detail.append(link);
  const fragment = `#${encodeURIComponent(row.fixture)}`;
  if (navigation === 'replace') history.replaceState(null, '', fragment);
  else if (navigation === 'push' && location.hash !== fragment) history.pushState(null, '', fragment);
  updateSelection();
}
function updateSelection() {
  for (const button of list.querySelectorAll('button')) {
    button.setAttribute('aria-pressed', String(button.dataset.fixture === selected));
  }
  const visible = selectRows(rows, search.value, status.value);
  document.querySelector('#selection-note').textContent = selected && !visible.some(row => row.fixture === selected)
    ? 'The selected case is outside the current filter. Its recorded details remain below.' : '';
}
function render() {
  const visible = selectRows(rows, search.value, status.value);
  list.replaceChildren();
  for (const row of visible) {
    const button = element('button', '');
    button.type = 'button';
    button.dataset.fixture = row.fixture;
    button.setAttribute('aria-pressed', String(selected === row.fixture));
    button.append(element('span', row.fixture.replaceAll('_', ' ')), element('small', row.completion_status.replaceAll('_', ' ')));
    button.addEventListener('click', () => show(row));
    list.append(button);
  }
  message.textContent = `${visible.length} of ${rows.length} recorded cases${visible.length ? '' : ' · Try a different search or filter.'}`;
  updateSelection();
}
search.addEventListener('input', render);
status.addEventListener('change', render);
function navigateToFragment() {
  let id = '';
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { /* Ignore malformed fragments. */ }
  const row = rows.find(item => item.fixture === id);
  if (row && row.fixture !== selected) show(row, 'none');
}
window.addEventListener('popstate', navigateToFragment);
window.addEventListener('hashchange', navigateToFragment);
async function load() {
  try {
    const response = await fetch(receiptURL, { credentials: 'omit' });
    if (!response.ok) throw new Error(`Receipt unavailable (${response.status})`);
    rows = receiptRows(await response.json());
    const totals = receiptTotals(rows);
    document.querySelector('#totals').textContent = `${totals.runs} cases / ${totals.claims} claims / ${totals.incidents} incidents / ${totals.withheld} completion approvals withheld`;
    let id = '';
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { /* Ignore malformed navigation. */ }
    const first = rows.find(row => row.fixture === id) || rows.find(row => row.fixture === 'tampered_acceptance_eval') || rows[0];
    render();
    if (first) show(first, 'replace');
  } catch (error) {
    document.querySelector('#totals').textContent = 'Receipt unavailable';
    message.textContent = `The receipt could not be loaded. ${error.message}. Use the original receipt link or reload to retry.`;
    detail.replaceChildren(element('h2', 'No results loaded'), element('p', 'Nothing here has been inferred or replaced with example data.'));
  }
}
load();

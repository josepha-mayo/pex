// Recorded receipt navigation only. This module never controls a bridge or worker.
export function receiptRows(receipt) {
  if (receipt?.scope !== 'curated_replay_fixture_suite_not_a_benchmark' || !Array.isArray(receipt.fixtures)) {
    throw new Error('Not a recorded PEX replay-suite receipt');
  }
  const ids = new Set();
  return receipt.fixtures.map(row => {
    if (!row || typeof row.fixture !== 'string' || !/^[a-z0-9_-]+$/.test(row.fixture) || ids.has(row.fixture)
      || !['verified_complete', 'uncertain', 'incomplete'].includes(row.completion_status)
      || !Number.isSafeInteger(row.claims_adjudicated) || row.claims_adjudicated < 0
      || !Number.isSafeInteger(row.integrity_incidents) || row.integrity_incidents < 0
      || !Array.isArray(row.evidence_strings) || !row.evidence_strings.every(x => typeof x === 'string')
      || !Array.isArray(row.interventions) || !row.interventions.every(x => typeof x === 'string')) {
      throw new Error('Malformed or duplicate replay row');
    }
    ids.add(row.fixture);
    return row;
  });
}
export function selectRows(rows, query = '', status = 'all') {
  const needle = query.trim().toLowerCase();
  return rows.filter(row => (status === 'all' || row.completion_status === status)
    && [row.fixture, ...row.evidence_strings].join(' ').toLowerCase().includes(needle));
}
export function receiptTotals(rows) {
  return rows.reduce((total, row) => ({
    runs: total.runs + 1,
    claims: total.claims + row.claims_adjudicated,
    incidents: total.incidents + row.integrity_incidents,
    withheld: total.withheld + Number(row.completion_status !== 'verified_complete'),
  }), { runs: 0, claims: 0, incidents: 0, withheld: 0 });
}

import type { ReplayResult } from "./result";
export function ResultPanel({ result }: { result: ReplayResult }) {
  return <section className="result-panel" aria-labelledby="result-heading">
    <p className="eyebrow">ACTUAL DETERMINISTIC REPLAY RESULT</p>
    <h2 id="result-heading">The claim vs. the evidence.</h2>
    <p className="result-scope">PEX adjudicated this recorded trajectory. Model inference: not attempted. No live worker was controlled.</p>
    <div className="result-summary"><div><span>Completion assessment</span><strong>{result.completion_status}</strong><p>{result.completion_reason}</p></div><div><span>Recorded scenario expectation</span><strong>{result.declared_expectation_met ? "Met" : "Not met"}</strong><p>This checks the fixture’s declared outcome, not a new live task.</p></div></div>
    <h3>Claim assessments, worst-first</h3><p className="result-hint">Selected assessments, limited to five and sorted by severity. This is not a chronological claim history.</p>
    {result.claim_verdicts.length ? <ol className="claim-list">{result.claim_verdicts.map((claim, index) => <li key={index}><span>{claim.claim || "(empty claim)"}</span><strong>{claim.status || "(empty status)"}</strong></li>)}</ol> : <p>No claim assessments were included.</p>}
    <h3>Evidence summary</h3><p className="result-hint">Entries may describe different points in the trajectory, including earlier missing evidence.</p>
    {result.evidence_summary.length ? <ul className="evidence-list">{result.evidence_summary.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p>No evidence summary was included.</p>}
    <h3>Verification sequence</h3>
    {result.verification_sequence.length ? <ol className="verification-list">{result.verification_sequence.map((item, index) => <li key={index}><strong>{item.status || "(empty status)"}</strong><span>{item.modified_acceptance_files.length ? `Modified acceptance files: ${item.modified_acceptance_files.join(", ")}` : "No modified acceptance files reported at this step."}</span></li>)}</ol> : <p>No verification steps were included.</p>}
    <div className="result-counts"><span><strong>{result.events_adjudicated}</strong> events adjudicated</span><span><strong>{result.claims_adjudicated}</strong> claims adjudicated</span><span><strong>{result.integrity_incidents}</strong> integrity incidents</span></div>
    <details><summary>Interventions ({result.interventions.length})</summary><ol>{result.interventions.map((item, index) => <li key={index}>{item}</li>)}</ol></details>
    <p className="result-hint">Bounded evidence summary, not raw logs or a downloadable receipt. Recorded replay · not live control.</p>
  </section>;
}

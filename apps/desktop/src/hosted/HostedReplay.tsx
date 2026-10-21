import { useEffect, useState } from "react";
import { ReplayClient } from "./client";
import type { Catalogue } from "./client";
import { ResultPanel } from "./ResultPanel";

export function HostedReplay({ client: suppliedClient }: { client?: ReplayClient } = {}) {
  const [client] = useState(() => suppliedClient ?? new ReplayClient());
  const [state, setState] = useState(client.state);
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  async function load() {
    setLoading(true); setLoadError("");
    try { setCatalogue(await client.catalogue()); }
    catch { setLoadError("The replay catalogue could not be loaded. Check that the separate replay service is configured and available. No run was requested."); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    const unsubscribe = client.subscribe(setState);
    void load();
    return () => { unsubscribe(); client.dispose(); };
  }, [client]);
  const unresolved = ["starting", "running", "interrupted", "expired", "quota_exhausted"].includes(state.phase);
  return <div className="replay-shell">
    <header><a className="brand" href="./hosted.html" aria-label="PEX replay home">P<span>EX</span><i /></a><span className="mode">RECORDED REPLAY · NOT LIVE CONTROL</span><span className="local-tag">Local preview</span></header>
    <main>
      <section className="intro"><p className="eyebrow">DON’T TRUST THE CLAIM. CHECK THE WORK.</p><h1>An agent says “done.”<br /><span>What actually happened?</span></h1><p className="lede">PEX supervises coding agents against their goals. Explore two recorded failure scenarios, without connecting a worker or sharing credentials.</p></section>
      <div className="workspace">
        <section className="scenarios" aria-labelledby="scenarios-heading"><div className="section-label"><span>01 / CHOOSE A SCENARIO</span><span>CURATED RECORDINGS</span></div><h2 id="scenarios-heading">Put the claim to the test.</h2>
          {loading && <p role="status">Loading the fixture catalogue…</p>}
          {loadError && <div role="alert"><p>{loadError}</p><button onClick={() => void load()} disabled={loading}>Retry catalogue</button></div>}
          {catalogue?.fixtures.map((fixture, index) => <article className="scenario" key={fixture.id}><span className="scenario-number">0{index + 1}</span><div><p className="scenario-kind">{fixture.id === "premature_stop_eval" ? "UNSUPPORTED COMPLETION" : "ACCEPTANCE TAMPERING"}</p><h3>{fixture.title}</h3><p>{fixture.id === "premature_stop_eval" ? "A worker claims the task is finished, but the required test evidence is missing." : "A worker edits the acceptance test instead of satisfying the original requirement."}</p><span className="recorded">Recorded trajectory · not a live agent</span></div><button disabled={!catalogue.execution_available || state.busy || unresolved} onClick={() => void client.start(fixture.id)} aria-label={`Start recorded replay: ${fixture.title}`}>Replay <span aria-hidden="true">↗</span></button></article>)}
          {catalogue && !catalogue.execution_available && <div className="availability" role="status"><strong>Execution is not connected yet.</strong><p>You can inspect the scenarios, but the isolated replay runner is unavailable. No replay has run and no result is being simulated.</p><button className="text-button" onClick={() => void load()} disabled={loading}>Check availability again</button></div>}
        </section>
        <section className="execution" aria-labelledby="execution-heading"><div className="section-label">02 / EXECUTION STATUS</div><div className={`status-mark ${state.phase}`} aria-hidden="true">{state.phase === "completed" ? "□" : "◎"}</div><p className="eyebrow">{state.phase === "idle" ? "READY WHEN THE RUNNER IS" : state.phase.replaceAll("_", " ").toUpperCase()}</p><h2 id="execution-heading">{state.phase === "completed" ? "Execution ended." : state.phase === "failed" ? "Replay did not finish." : state.phase === "quota_exhausted" ? "This visit’s limit is reached." : state.phase === "expired" ? "Access expired." : state.phase === "running" ? "Reading the recording." : state.phase === "interrupted" ? "Status needs a check." : "Evidence over confidence."}</h2><p role="status" aria-live="polite">{state.message}</p>
          {state.run && <p className="run-id">Run {state.run.run_id}<br />Recorded replay · not live control</p>}
          {state.phase === "interrupted" && <button onClick={() => void client.retry()} disabled={state.busy}>Check same attempt</button>}
          {["expired", "quota_exhausted"].includes(state.phase) && <button onClick={() => client.newVisit()}>Start a new visit</button>}
          <div className="evidence-note"><strong>{state.result ? "Evidence received separately from execution status." : "No verdict without a result payload."}</strong><p>“Completed” alone never verifies a claim. Only a validated result from this run can show PEX’s claim assessments and evidence.</p></div>
        </section>
      </div>
      {state.result && <ResultPanel result={state.result} />}
      <footer><span>PEX / GOAL-AWARE AGENT SUPERVISION</span><span>No provider keys. No workspace access. Temporary, in-memory visitor access.</span></footer>
    </main>
  </div>;
}

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseResult, readBoundedJson } from "./result.ts";
import { ReplayClient, parseCatalogue, parseRun, parseVisitor } from "./client.ts";

const labels = { replay: true, not_live_control: true };
const fixture = "premature_stop_eval";
const run = (state = "running") => ({ run_id: "run-1", fixture_id: fixture, state, error: state === "failed" ? "runner_failed" : null, ...labels });
const visitor = { visitor_token: "A".repeat(43), expires_in_seconds: 900 };
function setup(responses: Array<unknown | Error>, options: ConstructorParameters<typeof ReplayClient>[0] = {}) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetcher = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    if (url.endsWith("/result") && responses.length === 0) return Response.json({ detail: "result_unavailable" }, { status: 404 });
    const item = responses.shift();
    if (item instanceof Error) throw item;
    if (item instanceof Response) return item;
    assert.notEqual(item, undefined, "unexpected request");
    return Response.json(item);
  }) as typeof fetch;
  return { calls, client: new ReplayClient({ fetcher, wait: async () => {}, key: () => "attempt-1", ...options }) };
}
test("catalogue and runs require explicit honest labels and constrained identities", () => {
  assert.throws(() => parseCatalogue({ fixtures: [], execution_available: true }));
  assert.throws(() => parseCatalogue({ ...labels, execution_available: true, fixtures: [{ ...labels, id: "../../v1", title: "bad" }] }));
  assert.throws(() => parseRun({ ...run(), run_id: "../../v1" }));
  assert.throws(() => parseRun({ ...run(), state: "verified" }));
  assert.throws(() => parseRun({ ...run(), replay: false }));
  assert.equal(parseCatalogue({ ...labels, execution_available: false, fixtures: [] }).execution_available, false);
});
test("immediate 202 start polls to execution completion without a verdict", async () => {
  const { client, calls } = setup([visitor, Response.json(run(), { status: 202 }), run("completed")]);
  await client.start(fixture);
  assert.equal(client.state.phase, "completed");
  assert.match(client.state.message, /No verdict can be shown/);
  assert.deepEqual(calls.map((c) => c.url), ["/api/replay/visitors", "/api/replay/runs", "/api/replay/runs/run-1", "/api/replay/runs/run-1/result"]);
  assert.equal((calls[2].init.headers as Record<string, string>).Authorization, `Bearer ${"A".repeat(43)}`);
  assert.ok(calls.every((c) => c.init.credentials === "omit" && c.init.cache === "no-store" && c.init.redirect === "error"));
  assert.ok(calls.every((c) => !c.url.includes("secret-test")));
});
test("parallel repeated clicks do not issue a second start", async () => {
  const { client, calls } = setup([visitor, run("completed")]);
  await Promise.all([client.start(fixture), client.start(fixture), client.retry()]);
  assert.equal(calls.filter((c) => c.url.endsWith("/runs")).length, 1);
});
test("uncertain start retries reuse the exact idempotency key and visitor", async () => {
  const { client, calls } = setup([visitor, new TypeError("network"), run("completed")]);
  await client.start(fixture);
  assert.equal(client.state.phase, "interrupted");
  await client.start("tampered_acceptance_eval");
  assert.equal(calls.length, 2);
  await client.retry();
  assert.equal(calls[1].init.body, calls[2].init.body);
  assert.equal(calls.filter((c) => c.url.endsWith("visitors")).length, 1);
});
test("bounded polling pauses without inventing a failed execution and resumes GET", async () => {
  const { client, calls } = setup([visitor, run(), run(), run("completed")], { maxPolls: 1 });
  await client.start(fixture);
  assert.equal(client.state.phase, "interrupted");
  assert.equal(client.state.run?.state, "running");
  await client.retry();
  assert.equal(client.state.phase, "completed");
  assert.equal(calls.filter((c) => c.init.method === "POST").length, 2);
});
test("expiry stops polling; explicit new visit is required", async () => {
  let now = 0;
  const { client, calls } = setup([visitor, run()], { now: () => now, wait: async () => { now = 901000; } });
  await client.start(fixture);
  assert.equal(client.state.phase, "expired");
  await client.retry();
  assert.equal(calls.length, 2);
  client.newVisit();
  assert.equal(client.state.phase, "idle");
  assert.equal(client.state.run, null);
});
test("server expiry and unavailable runner are honest errors", async () => {
  const a = setup([visitor, Response.json({ detail: "visitor_expired_or_unknown" }, { status: 401 })]);
  await a.client.start(fixture);
  assert.equal(a.client.state.phase, "expired");
  const b = setup([visitor, Response.json({ detail: "isolated_replay_runner_unavailable" }, { status: 503 })]);
  await b.client.start(fixture);
  assert.match(b.client.state.message, /no replay ran/);
  assert.equal(b.client.state.run, null);
});
test("503 failed replay body is execution failure, never success", async () => {
  const { client } = setup([visitor, Response.json(run("failed"), { status: 503 })]);
  await client.start(fixture);
  assert.equal(client.state.phase, "failed");
  assert.match(client.state.message, /No verdict/);
});
test("mismatched run identity is rejected", async () => {
  const { client } = setup([visitor, run(), { ...run("completed"), run_id: "other" }]);
  await client.start(fixture);
  assert.equal(client.state.phase, "interrupted");
  assert.match(client.state.message, /unexpected response/);
});
test("disposed UI cannot continue polling", async () => {
  let client: ReplayClient;
  const setupResult = setup([visitor, run()], { wait: async () => { client.dispose(); } });
  client = setupResult.client;
  await client.start(fixture);
  assert.equal(setupResult.calls.length, 2);
});
test("hosted entry stays independent of desktop controls and persistent tokens", () => {
  const source = ["./client.ts", "./HostedReplay.tsx", "./main.tsx"]
    .map((path) => readFileSync(new URL(path, import.meta.url), "utf8")).join("\n");
  for (const forbidden of ["localStorage", "sessionStorage", "document.cookie", "@tauri", 'from "../App"', 'fetch("/v1', "URLSearchParams"]) assert.ok(!source.includes(forbidden), forbidden);
  assert.match(source, /No verdict without a result payload/);
});

test("visitor capability shape and lifetime fail closed", () => {
  assert.deepEqual(parseVisitor(visitor), visitor);
  for (const token of ["", "short", "A".repeat(44), "A".repeat(43) + "\n", "A".repeat(42) + "/", "Bearer " + "A".repeat(43)]) {
    assert.throws(() => parseVisitor({ ...visitor, visitor_token: token }));
  }
  for (const ttl of [Infinity, -Infinity, NaN, 0, -1, 901, "900", null]) {
    assert.throws(() => parseVisitor({ ...visitor, expires_in_seconds: ttl }));
  }
});

// Snapshots of actual local deterministic replay-job output, not live-model output.
// Source: build/replay-job-evidence/{fixture}.json, generated 2026-10-20.
const actualResult = (name = fixture) => JSON.parse(readFileSync(new URL(`./test-fixtures/${name}.json`, import.meta.url), "utf8"));
test("actual result schemas for both recorded fixtures parse without changing evidence", () => {
  for (const name of [fixture, "tampered_acceptance_eval"]) {
    const result = actualResult(name);
    assert.deepEqual(parseResult(result, name), result);
    assert.equal(result.inference_status, "not_attempted");
    assert.equal(result.declared_expectation_met, true);
  }
});
test("result schema rejects missing, unknown, mismatched and unbounded values", () => {
  const result = actualResult();
  for (const patch of [
    { fixture_id: "tampered_acceptance_eval" }, { schema_version: "next" }, { replay: false },
    { not_live_control: false }, { inference_status: "completed" }, { execution_mode: "live" },
    { completion_reason: "x".repeat(401) }, { completion_status: "x".repeat(65) },
    { evidence_summary: Array(5).fill("x") }, { evidence_summary: ["x".repeat(161)] },
    { claim_verdicts: Array(6).fill({ claim: "x", status: "x" }) },
    { claim_verdicts: [{ claim: "x", status: "x", invented: true }] },
    { claim_verdicts: [{ claim: "x".repeat(201), status: "supported" }] },
    { verification_sequence: [{ status: "x", modified_acceptance_files: Array(17).fill("x") }] },
    { interventions: Array(33).fill("x") }, { events_adjudicated: -1 },
    { claims_adjudicated: 1001 }, { integrity_incidents: 1.5 }, { declared_expectation_met: "true" },
    { unknown: "field" }, { completion_status: "verified" },
    { claim_verdicts: [{ claim: "All tests passed", status: "verified" }] },
    { verification_sequence: [{ status: "passed", modified_acceptance_files: [] }] },
  ]) assert.throws(() => parseResult({ ...result, ...patch }, fixture));
  const missing = { ...result }; delete missing.completion_reason;
  assert.throws(() => parseResult(missing, fixture));
  const huge = { ...result, verification_sequence: Array.from({ length: 16 }, () => ({ status: "supported", modified_acceptance_files: Array(16).fill("x".repeat(240)) })) };
  assert.throws(() => parseResult(huge, fixture), /response_too_large/);
});
test("response body is bounded before parsing regardless of Content-Length", async () => {
  assert.deepEqual(await readBoundedJson(Response.json(actualResult())), actualResult());
  await assert.rejects(readBoundedJson(new Response("x".repeat(16385))), /response_too_large/);
  await assert.rejects(readBoundedJson(new Response("é".repeat(8193))), /response_too_large/);
  await assert.rejects(readBoundedJson(new Response("{}", { headers: { "Content-Length": "16385" } })), /response_too_large/);
  let cancelled = false;
  const stream = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(16384)); controller.enqueue(new Uint8Array(1)); }, cancel() { cancelled = true; } });
  await assert.rejects(readBoundedJson(new Response(stream, { headers: { "Content-Length": "1" } })), /response_too_large/);
  assert.equal(cancelled, true);
  await assert.rejects(readBoundedJson(new Response("<html>Not JSON</html>")), /invalid_response/);
});
test("completion fetches actual evidence separately through the same bearer", async () => {
  const { client, calls } = setup([visitor, run("completed"), actualResult()]);
  await client.start(fixture);
  assert.equal(client.state.phase, "completed");
  assert.deepEqual(client.state.result, actualResult());
  assert.match(client.state.message, /No model inference or live worker/);
  assert.equal(calls[2].url, "/api/replay/runs/run-1/result");
  assert.equal((calls[2].init.headers as Record<string, string>).Authorization, `Bearer ${"A".repeat(43)}`);
});
test("mismatched or oversized results never become visible evidence", async () => {
  for (const payload of [actualResult("tampered_acceptance_eval"), new Response("x".repeat(16385))]) {
    const { client } = setup([visitor, run("completed"), payload]);
    await client.start(fixture);
    assert.equal(client.state.phase, "interrupted");
    assert.equal(client.state.result, null);
  }
});
test("pending results retry the same run without a second POST", async () => {
  const { client, calls } = setup([visitor, run("completed"), Response.json({ detail: "result_pending" }, { status: 202 }), run("completed"), actualResult()]);
  await client.start(fixture);
  assert.equal(client.state.phase, "interrupted");
  assert.equal(client.state.result, null);
  await client.retry();
  assert.equal(client.state.phase, "completed");
  assert.deepEqual(client.state.result, actualResult());
  assert.equal(calls.filter((c) => c.url === "/api/replay/runs" && c.init.method === "POST").length, 1);
});
test("expired result access cannot display evidence", async () => {
  const { client } = setup([visitor, run("completed"), Response.json({ detail: "visitor_expired_or_unknown" }, { status: 401 })]);
  await client.start(fixture);
  assert.equal(client.state.phase, "expired");
  assert.equal(client.state.result, null);
});

test("fifth-run visitor quota is terminal until an intentional new visit", async () => {
  const responses: unknown[] = [visitor];
  for (let i = 0; i < 4; i++) responses.push(run("completed"), actualResult());
  responses.push(Response.json({ detail: "visitor_run_limit" }, { status: 429 }));
  const { client, calls } = setup(responses, { key: (() => { let i = 0; return () => `attempt-${++i}`; })() });
  for (let i = 0; i < 5; i++) await client.start(fixture);
  assert.equal(client.state.phase, "quota_exhausted");
  assert.equal(client.state.run, null);
  assert.equal(client.state.result, null);
  assert.match(client.state.message, /No new run was admitted/);
  assert.match(client.state.message, /does not recover or cancel/);
  const before = calls.length;
  await client.retry();
  await client.start(fixture);
  assert.equal(calls.length, before);
  assert.equal(calls.filter((call) => call.url.endsWith("visitors")).length, 1);
  client.newVisit();
  assert.equal(client.state.phase, "idle");
  assert.equal(calls.length, before, "new visit action clears local state without automatically issuing requests");
});
test("transient run capacity retries the same attempt and visitor", async () => {
  const { client, calls } = setup([visitor, Response.json({ detail: "run_capacity" }, { status: 429 }), run("completed"), actualResult()]);
  await client.start(fixture);
  assert.equal(client.state.phase, "interrupted");
  assert.match(client.state.message, /capacity is full/);
  await client.retry();
  assert.equal(client.state.phase, "completed");
  assert.deepEqual(client.state.result, actualResult());
  assert.equal(calls[1].init.body, calls[2].init.body);
  assert.equal(calls.filter((call) => call.url.endsWith("visitors")).length, 1);
});
test("claim assessments disclose bounded severity ordering, not chronology", () => {
  const source = readFileSync(new URL("./ResultPanel.tsx", import.meta.url), "utf8");
  assert.match(source, /Claim assessments, worst-first/);
  assert.match(source, /limited to five and sorted by severity/);
  assert.match(source, /not a chronological claim history/);
  assert.match(source, /Verification sequence/);
});

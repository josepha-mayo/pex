import test from "node:test";
import assert from "node:assert/strict";
import { createWorkspaceClient, parseWorkspace, type WorkspaceView } from "./workspace.ts";
const origin = "https://owner.example.test";
const snapshot = () => ({ schema: "pex.owner-workspace.v1", observed_at: "2026-10-26T23:00:00+00:00", sessions: [{ id: "s1", harness_type: "opencode", status: "working", goal_id: "g1", last_activity: null }], goals: [{ id: "g1", title: "Authored task", paused: false, completion: { status: "uncertain", reason: "no_current_supported_completion_evidence", as_of: "2026-10-26T23:00:00Z" } }], truncated: { sessions: false, goals: false } });
const response = () => new Response(JSON.stringify(snapshot()));
function fixture(send: typeof fetch) { const views: WorkspaceView[] = []; let allowed = true; let denied = 0;
  const client = createWorkspaceClient({ origin, send, authorized: () => allowed, changed: v => views.push(v), denied: () => denied++ });
  return { client, views, disallow: () => { allowed = false; }, denials: () => denied }; }

test("manual read uses exact owner route and safe cookie transport", async () => {
  let calls = 0; const f = fixture((async (url, init) => { calls++; assert.equal(url, origin + "/owner/workspace"); assert.equal(init?.method, "GET"); assert.equal(init?.credentials, "same-origin"); assert.equal(init?.redirect, "error"); assert.equal(init?.cache, "no-store"); return response(); }) as typeof fetch);
  assert.equal(calls, 0); await f.client.load(); assert.equal(calls, 1); assert.equal(f.views.at(-1)?.data?.goals[0].completion.status, "uncertain");
  f.client.lock(); assert.equal(f.views.at(-1)?.data, undefined);
});
test("lock and newer generation suppress late workspace responses", async () => {
  let resolve!: (r: Response) => void; let signal: AbortSignal | undefined;
  const f = fixture((async (_url, init) => { signal = init?.signal as AbortSignal; return new Promise<Response>(r => { resolve = r; }); }) as typeof fetch);
  const pending = f.client.load(); f.client.lock(); assert.equal(signal?.aborted, true); resolve(response()); await pending; assert.equal(f.views.some(v => v.phase === "ready"), false);
});
test("session expiry and duplicate clicks do not reveal data or duplicate reads", async () => {
  let resolve!: (r: Response) => void; let calls = 0;
  const f = fixture((async () => { calls++; return new Promise<Response>(r => { resolve = r; }); }) as typeof fetch);
  const pending = f.client.load(); await f.client.load(); f.disallow(); resolve(response()); await pending;
  assert.equal(calls, 1); assert.equal(f.views.some(v => v.phase === "ready"), false);
});
test("denial locks, errors and oversized replies clear old data without retry", async () => {
  for (const reply of [new Response("", {status:401}), new Response("", {status:503}), new Response("x".repeat(32769))]) {
    let calls = 0; const f = fixture((async () => { calls++; return reply; }) as typeof fetch); await f.client.load();
    assert.equal(calls, 1); assert.equal(f.views.at(-1)?.data, undefined);
    if (reply.status === 401) assert.equal(f.denials(), 1); else assert.equal(f.views.at(-1)?.phase, "unavailable");
  }
});
test("schema rejects private fields, unknown truth labels, excessive rows and malformed identifiers", () => {
  const extra = {...snapshot(), private: "secret"}; assert.throws(() => parseWorkspace(extra));
  const status = snapshot(); status.goals[0].completion.status = "success"; assert.throws(() => parseWorkspace(status));
  const rows = snapshot(); rows.sessions = Array(21).fill(rows.sessions[0]); assert.throws(() => parseWorkspace(rows));
  const id = snapshot(); id.sessions[0].id = "x\n"; assert.throws(() => parseWorkspace(id));
  const nested = snapshot(); Object.assign(nested.sessions[0], {metadata:{secret:"hidden"}}); assert.throws(() => parseWorkspace(nested));
  assert.throws(() => createWorkspaceClient({origin:"http://localhost",authorized:()=>true,changed(){},denied(){}}));
});

// Python server title limits count Unicode code points, not UTF-16 units.
test("title length agrees with server for astral and mixed Unicode", () => {
  for (const title of ["😀".repeat(160), "😀".repeat(161), "😀".repeat(320), "界a😀".repeat(106) + "é😀"]) {
    const value = snapshot(); value.goals[0].title = title;
    assert.equal(parseWorkspace(value).goals[0].title, title);
  }
  for (const title of ["😀".repeat(321), "界a😀".repeat(107), "a".repeat(321)]) {
    const value = snapshot(); value.goals[0].title = title;
    assert.throws(() => parseWorkspace(value));
  }
});

test("authored run metadata validates and private extra fields fail closed", () => {
  const base = { ...snapshot(), run_evidence: { state: "not_configured" } };
  assert.equal(parseWorkspace(base).run_evidence?.state, "not_configured");
  assert.throws(() => parseWorkspace({ ...base, run_evidence: { state: "empty", prompt: "private" } }));
  const recorded = { state: "recorded", phase: "arm_terminal", observed_at: "2026-10-27T12:00:00Z", worker_model: "opencode/deepseek-v4.1-flash-free", supervisor_model: "nvidia/nemotron-3-super-120b-a12b", paired_terminal: false, arms: { baseline: { status: "natural_stop", worker_calls: 1 }, pex: { status: "not_started", worker_calls: null } } };
  assert.equal(parseWorkspace({ ...base, run_evidence: recorded }).run_evidence?.state, "recorded");
  assert.throws(() => parseWorkspace({ ...base, run_evidence: { ...recorded, paired_terminal: true } }));
  assert.throws(() => parseWorkspace({ ...base, run_evidence: { ...recorded, grade: "private" } }));
  assert.throws(() => parseWorkspace({ ...base, run_evidence: { ...recorded, worker_model: "private" } }));
});

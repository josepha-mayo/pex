import { parseResult, readBoundedJson } from "./result.ts";
import type { ReplayResult } from "./result.ts";
// This entry deliberately has no dependency on the desktop bridge or credentials.
export type Fixture = { id: string; title: string; replay: true; not_live_control: true };
export type Run = { run_id: string; fixture_id: string; state: "running" | "completed" | "failed"; error: string | null; replay: true; not_live_control: true };
export type Catalogue = { fixtures: Fixture[]; execution_available: boolean };
export type ReplayState = {
  phase: "idle" | "starting" | "running" | "completed" | "failed" | "interrupted" | "expired" | "quota_exhausted";
  run: Run | null;
  result: ReplayResult | null;
  message: string;
  busy: boolean;
};
const INITIAL: ReplayState = { phase: "idle", run: null, result: null, message: "Choose a recorded scenario to begin.", busy: false };
const ID = /^[a-zA-Z0-9_-]{1,64}$/;
const FIXTURES = new Set(["premature_stop_eval", "tampered_acceptance_eval"]);
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
function labels(v: Record<string, unknown>) { return v.replay === true && v.not_live_control === true; }
export function parseCatalogue(value: unknown): Catalogue {
  if (!isObject(value) || !labels(value) || !Array.isArray(value.fixtures) || typeof value.execution_available !== "boolean") throw new Error("invalid_response");
  const fixtures = value.fixtures.map((f: unknown): Fixture => {
    if (!isObject(f) || !labels(f) || typeof f.id !== "string" || !FIXTURES.has(f.id) || typeof f.title !== "string") throw new Error("invalid_response");
    return { id: f.id, title: f.title, replay: true, not_live_control: true };
  });
  return { fixtures, execution_available: value.execution_available };
}
export function parseRun(value: unknown): Run {
  if (!isObject(value) || !labels(value) || typeof value.run_id !== "string" || !ID.test(value.run_id) || typeof value.fixture_id !== "string" || !FIXTURES.has(value.fixture_id) || !["running", "completed", "failed"].includes(String(value.state)) || !(value.error === null || typeof value.error === "string")) throw new Error("invalid_response");
  return value as Run;
}
// The server currently issues secrets.token_urlsafe(32): exactly 43 URL-safe characters.
// Browser access is deliberately bounded to at most the contract's 15-minute visit.
export function parseVisitor(value: unknown): { visitor_token: string; expires_in_seconds: number } {
  if (!isObject(value) || typeof value.visitor_token !== "string" || value.visitor_token.length !== 43 || !/^[A-Za-z0-9_-]{43}$/.test(value.visitor_token) || typeof value.expires_in_seconds !== "number" || !Number.isFinite(value.expires_in_seconds) || value.expires_in_seconds <= 0 || value.expires_in_seconds > 900) throw new Error("invalid_response");
  return { visitor_token: value.visitor_token, expires_in_seconds: value.expires_in_seconds };
}
class ApiError extends Error {
  status: number;
  constructor(status: number, code: string) { super(code); this.status = status; }
}
export function errorCopy(error: unknown): string {
  const code = error instanceof Error ? error.message : "unknown";
  const known: Record<string, string> = {
    isolated_replay_runner_unavailable: "Replay execution is not connected. The catalogue is available, but no replay ran.",
    run_capacity: "Replay capacity is full. Retry this same request in a moment.",
    visitor_capacity: "Visitor capacity is full. Please try again later.",
    origin_denied: "This page is not an approved replay origin. Check the local service configuration.",
    response_too_large: "The service response exceeded the safe size limit. No verdict can be shown.",
    result_pending: "Execution ended, but its result is not ready. Check this same attempt again.",
    run_failed: "The service reports failed execution. No verdict is available.",
    invalid_response: "The service returned an unexpected response. No verdict can be shown.",
    run_timeout: "Replay execution exceeded its time limit. No verdict is available.",
    run_cancelled: "Replay execution was cancelled. No verdict is available.",
    runner_failed: "Replay execution failed. No verdict is available.",
    run_not_found: "This replay could not be found for your visitor session.",
    service_stopping: "The replay service is shutting down. Please try later.",
    curated_fixture_unavailable: "The recorded fixture is unavailable on the service.",
    idempotency_conflict: "The service rejected this request identity. Do not assume a new run was started.",
  };
  return known[code] ?? "The service could not be reached reliably. The request may have been accepted. Retry to check the same attempt, not start a duplicate.";
}
export class ReplayClient {
  private token: string | null = null;
  private expiresAt = 0;
  private attempt: { fixture: string; key: string } | null = null;
  private active = false;
  private stopped = false;
  private listeners = new Set<(state: ReplayState) => void>();
  state: ReplayState = { ...INITIAL };
  private fetcher: typeof fetch;
  private now: () => number;
  private wait: (ms: number) => Promise<void>;
  private key: () => string;
  private maxPolls: number;
  constructor(options: { fetcher?: typeof fetch; now?: () => number; wait?: (ms: number) => Promise<void>; key?: () => string; maxPolls?: number } = {}) {
    this.fetcher = options.fetcher ?? fetch;
    this.now = options.now ?? Date.now;
    this.wait = options.wait ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    this.key = options.key ?? (() => crypto.randomUUID());
    this.maxPolls = options.maxPolls ?? 40;
  }
  subscribe(listener: (state: ReplayState) => void) { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; }
  private publish(patch: Partial<ReplayState>) { this.state = { ...this.state, ...patch }; if (!this.stopped) this.listeners.forEach((fn) => fn(this.state)); }
  dispose() { this.stopped = true; this.token = null; this.listeners.clear(); }
  private async request(path: string, method = "GET", body?: unknown, protectedRead = false): Promise<unknown> {
    if (protectedRead && (!this.token || this.now() >= this.expiresAt)) throw new ApiError(401, "visitor_expired_or_unknown");
    const response = await this.fetcher(`/api/replay/${path}`, {
      method, credentials: "omit", cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8000),
      headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...(protectedRead ? { Authorization: `Bearer ${this.token}` } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const value: unknown = await readBoundedJson(response);
    if (response.status === 202 && isObject(value) && value.detail === "result_pending") throw new ApiError(202, "result_pending");
    // Failed idempotent starts return a run body with HTTP 503.
    if (!response.ok && !(response.status === 503 && isObject(value) && value.state === "failed" && labels(value))) throw new ApiError(response.status, isObject(value) && typeof value.detail === "string" ? value.detail : "request_failed");
    return value;
  }
  async catalogue() { return parseCatalogue(await this.request("fixtures")); }
  async start(fixture: string) {
    if (this.active || this.stopped || !FIXTURES.has(fixture)) return;
    if (this.attempt && !["completed", "failed", "idle"].includes(this.state.phase)) return; // retry unresolved work instead
    this.attempt = { fixture, key: this.key() };
    this.publish({ ...INITIAL });
    await this.retry();
  }
  async retry() {
    if (this.active || this.stopped || !this.attempt || ["expired", "quota_exhausted"].includes(this.state.phase)) return;
    this.active = true;
    this.publish({ busy: true, result: null, phase: this.state.run ? "running" : "starting", message: "Connecting to the isolated replay service…" });
    try {
      if (!this.token) {
        const visitor = parseVisitor(await this.request("visitors", "POST"));
        if (this.stopped) return;
        this.token = visitor.visitor_token;
        this.expiresAt = this.now() + visitor.expires_in_seconds * 1000;
      }
      if (this.stopped) return;
      let run = parseRun(this.state.run
        ? await this.request(`runs/${this.state.run.run_id}`, "GET", undefined, true)
        : await this.request("runs", "POST", { fixture_id: this.attempt.fixture, idempotency_key: this.attempt.key }, true));
      for (let count = 0; ; count++) {
        if (this.stopped) return;
        if (run.fixture_id !== this.attempt.fixture || (this.state.run && run.run_id !== this.state.run.run_id)) throw new Error("invalid_response");
        this.publish({ run, phase: run.state, message: run.state === "completed" ? "Replay execution ended. This is not a verified claim." : run.state === "failed" ? errorCopy(new Error(run.error ?? "runner_failed")) : "Recorded replay is running. Checking execution status…" });
        if (run.state === "completed") {
          try {
            const result = parseResult(await this.request(`runs/${run.run_id}/result`, "GET", undefined, true), run.fixture_id);
            if (this.stopped) return;
            this.publish({ result, message: "Deterministic PEX replay evidence received. No model inference or live worker execution was attempted." });
          } catch (error) {
            if (error instanceof ApiError && error.status === 404 && error.message === "result_unavailable") this.publish({ message: "Replay execution ended, but this run has no result payload. No verdict can be shown." });
            else throw error;
          }
          break;
        }
        if (run.state === "failed") break;
        if (count >= this.maxPolls) { this.publish({ phase: "interrupted", message: "Automatic checking paused after its bounded window. Execution may still be running. Check the same run again." }); break; }
        await this.wait(1000);
        if (this.stopped) return;
        run = parseRun(await this.request(`runs/${run.run_id}`, "GET", undefined, true));
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        this.token = null;
        this.publish({ phase: "expired", result: null, message: "Your temporary visitor access expired. This run can no longer be read. Starting a new visit does not recover or cancel it." });
      } else if (error instanceof ApiError && error.status === 429 && error.message === "visitor_run_limit") {
        this.publish({ phase: "quota_exhausted", result: null, message: "This temporary visit has reached its replay limit. No new run was admitted. You can intentionally start a new visit, but this discards access to this visit’s old runs; it does not recover or cancel them." });
      } else this.publish({ phase: "interrupted", message: errorCopy(error) });
    } finally { this.active = false; this.publish({ busy: false }); }
  }
  newVisit() {
    if (this.active) return;
    this.token = null; this.expiresAt = 0; this.attempt = null;
    this.publish({ ...INITIAL });
  }
}

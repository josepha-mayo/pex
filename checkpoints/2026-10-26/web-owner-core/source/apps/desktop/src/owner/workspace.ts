/** Read-only, bounded owner projection. No polling, worker controls or provider calls. */
export type Workspace = {
  schema: "pex.owner-workspace.v1"; observed_at: string;
  sessions: { id: string; harness_type: string; status: string; goal_id: string | null; last_activity: string | null }[];
  goals: { id: string; title: string; paused: boolean; completion: { status: string; reason: string; as_of: string } }[];
  truncated: { sessions: boolean; goals: boolean };
};
export type WorkspaceView = { phase: "idle" | "loading" | "ready" | "unavailable"; message: string; data?: Workspace };
const id = (v: unknown): v is string => typeof v === "string" && /^[A-Za-z0-9_.:-]{1,128}$/.test(v) && !v.endsWith("\n");
const stamp = (v: unknown): v is string => typeof v === "string" && v.length <= 40 && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
const keys = (v: unknown, names: string[]): v is Record<string, any> => !!v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).sort().join() === names.sort().join();
const harnesses = new Set("cursor codex claude_code opencode devin grok_build grok_bot pi omp hermes prime zcode kimi deepseek qwen synthetic unknown".split(" "));
const statuses = new Set("discovered idle working blocked needs_decision drifting verifying stopped error detached".split(" "));
const completions = new Set(["uncertain", "in_progress", "verified_complete", "incomplete"]);
const reasons = new Set(["goal_not_currently_executable", "newer_active_session_work", "current_intent_stop_evidence_supported", "current_intent_stop_evidence_unsatisfied", "active_session_without_terminal_evidence", "no_current_supported_completion_evidence"]);
export function parseWorkspace(value: unknown): Workspace {
  if (!keys(value, ["schema", "observed_at", "sessions", "goals", "truncated"]) || value.schema !== "pex.owner-workspace.v1" || !stamp(value.observed_at) ||
      !Array.isArray(value.sessions) || value.sessions.length > 20 || !Array.isArray(value.goals) || value.goals.length > 20 ||
      !keys(value.truncated, ["sessions", "goals"]) || typeof value.truncated.sessions !== "boolean" || typeof value.truncated.goals !== "boolean") throw new Error("invalid");
  for (const s of value.sessions) if (!keys(s, ["id", "harness_type", "status", "goal_id", "last_activity"]) || !id(s.id) || !harnesses.has(s.harness_type) || !statuses.has(s.status) || (s.goal_id !== null && !id(s.goal_id)) || (s.last_activity !== null && !stamp(s.last_activity))) throw new Error("invalid");
  for (const g of value.goals) if (!keys(g, ["id", "title", "paused", "completion"]) || !id(g.id) || typeof g.title !== "string" || !g.title.length || g.title.length > 320 || /[\x00-\x1f]/.test(g.title) || typeof g.paused !== "boolean" || !keys(g.completion, ["status", "reason", "as_of"]) || !completions.has(g.completion.status) || !reasons.has(g.completion.reason) || !stamp(g.completion.as_of)) throw new Error("invalid");
  return value as Workspace;
}

export function createWorkspaceClient({ origin, authorized, changed, denied, send = fetch }: {
  origin: string; authorized: () => boolean; changed: (view: WorkspaceView) => void; denied: () => void; send?: typeof fetch;
}) {
  const base = new URL(origin);
  if (base.protocol !== "https:" || base.origin !== origin) throw new Error("HTTPS required");
  let generation = 0; let active: AbortController | null = null;
  const lock = () => { generation++; active?.abort(); active = null; changed({ phase: "idle", message: "Load recorded sessions and goal outcomes. No workers will be started." }); };
  return {
    lock,
    async load() {
      if (!authorized() || active) return;
      const mine = ++generation; const controller = new AbortController(); active = controller;
      const timer = setTimeout(() => controller.abort(), 5000);
      changed({ phase: "loading", message: "Reading recorded workspace…" });
      try {
        const response = await send(new URL("/owner/workspace", base).href, { method: "GET", credentials: "same-origin", redirect: "error", cache: "no-store", signal: controller.signal });
        if (response.status === 401 || response.status === 403) throw new Error("denied");
        if (!response.ok) throw new Error("unavailable");
        const reader = response.body?.getReader(); if (!reader) throw new Error("invalid");
        const chunks: Uint8Array[] = []; let length = 0;
        try { while (true) { const part = await reader.read(); if (part.done) break; length += part.value.byteLength;
          if (length > 32768) { await reader.cancel(); throw new Error("invalid"); } chunks.push(part.value); }
        } finally { reader.releaseLock(); }
        const bytes = new Uint8Array(length); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
        const data = parseWorkspace(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)));
        if (mine !== generation || !authorized()) return;
        changed({ phase: "ready", message: "Recorded state, not a live worker feed. Refresh to check again.", data });
      } catch (error) {
        if (mine !== generation || !authorized()) return;
        if (error instanceof Error && error.message === "denied") { lock(); denied(); }
        else changed({ phase: "unavailable", message: "Workspace could not be read safely. No cached rows are shown and no action was retried." });
      } finally { clearTimeout(timer); if (active === controller) active = null; }
    },
  };
}

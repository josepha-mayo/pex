// Recorded supervision replays: the demo bridge can inject a bounded fixture
// trajectory through the real pipeline so the supervision loop is visible
// without a worker install. Every surface labels the result as a replay —
// never a live worker and never a benchmark result.

import type { SessionRow } from "./types.ts";

export type DemoFixture = {
  id: string;
  title: string;
  // One-line "what this arc proves" from the fixture itself.
  summary?: string;
  // Set when the fixture was exported from a recorded live session
  // (scripts/capture_replay.py) — the replay is real captured traffic,
  // which is a stronger claim than a synthetic trajectory.
  capturedFromLive?: string;
  // Set when the fixture is designed to attach to an existing goal (e.g.
  // the second-act ruling-continuity trajectory).
  attachHint?: string;
};

// A fixture id is bridge-minted and bounded; arbitrary strings are refused
// before any request so a poisoned listing cannot reach the replay route.
const FIXTURE_ID = /^[a-z0-9][a-z0-9_-]{0,62}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseFixture(raw: unknown): DemoFixture | null {
  if (!isRecord(raw)) return null;
  const { id, title, summary, captured_from_live_session: captured, attach_hint } = raw;
  if (typeof id !== "string" || !FIXTURE_ID.test(id)) return null;
  if (typeof title !== "string" || !title.trim()) return null;
  if (summary !== undefined && typeof summary !== "string") return null;
  if (attach_hint !== undefined && typeof attach_hint !== "string") return null;
  const fixture: DemoFixture = { id, title: title.trim() };
  if (typeof summary === "string" && summary.trim()) {
    fixture.summary = summary.trim().slice(0, 240);
  }
  if (typeof captured === "string" && captured.trim()) {
    fixture.capturedFromLive = captured.trim();
  }
  if (typeof attach_hint === "string" && attach_hint.trim()) {
    fixture.attachHint = attach_hint.trim().slice(0, 240);
  }
  return fixture;
}

// The replay surface exists only while the bridge honestly advertises it: a
// missing route, an unlabeled payload, or a single malformed fixture removes
// the control entirely rather than offering a partial demo.
export function parseTrajectoriesResponse(payload: unknown): DemoFixture[] | null {
  if (!isRecord(payload)) return null;
  if (payload.replay !== true || payload.not_live_control !== true) return null;
  if (!Array.isArray(payload.fixtures)) return null;
  const fixtures: DemoFixture[] = [];
  for (const raw of payload.fixtures) {
    const fixture = parseFixture(raw);
    if (!fixture) return null;
    fixtures.push(fixture);
  }
  return fixtures.length ? fixtures : null;
}

export function parseReplaySessionId(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  if (payload.replay !== true || payload.not_live_control !== true) return null;
  const { session_id: sessionId } = payload;
  return typeof sessionId === "string" && sessionId.trim() ? sessionId.trim() : null;
}

/** "attached" means the run borrowed an existing goal's ledger; else minted. */
export function parseReplayGoalSource(payload: unknown): "attached" | null {
  if (!isRecord(payload)) return null;
  return payload.goal_source === "attached" ? "attached" : null;
}

export type ReplayVerdict = {
  // Intervention actions the supervisor actually took, in order.
  actions: string[];
  // The constraint the first contradicting nudge cited — when a replay runs
  // attached to a ruled goal this is the journaled ruling itself.
  citedConstraint?: string;
  // Adjudicated completion from the goal projection — absent means the run
  // was not adjudicated, never that it passed.
  status?: string;
  reason?: string;
};

// The replay response carries the observed supervision arc plus the goal's
// completion projection so the post-run card can state the verdict without a
// second fetch. Malformed entries drop out rather than fabricate an arc.
export function parseReplayVerdict(payload: unknown): ReplayVerdict | null {
  if (!isRecord(payload)) return null;
  if (payload.replay !== true || payload.not_live_control !== true) return null;
  const actions: string[] = [];
  let citedConstraint: string | undefined;
  if (Array.isArray(payload.interventions)) {
    for (const raw of payload.interventions) {
      if (!isRecord(raw)) continue;
      const action = raw.action_taken ?? raw.type;
      // NOOP is a deliberate stay-quiet observation, not an arc step — the
      // audit trail drops it and so does this summary.
      if (typeof action === "string" && action.trim() && action.trim() !== "NOOP") {
        actions.push(action.trim());
      }
      if (citedConstraint === undefined && Array.isArray(raw.evidence)) {
        for (const item of raw.evidence) {
          if (typeof item === "string" && item.startsWith("agent_contradiction:")) {
            const constraint = item.slice("agent_contradiction:".length).trim();
            if (constraint) citedConstraint = constraint;
            break;
          }
        }
      }
    }
  }
  const verdict: ReplayVerdict = { actions };
  if (citedConstraint !== undefined) verdict.citedConstraint = citedConstraint;
  if (isRecord(payload.completion)) {
    const { status, reason } = payload.completion;
    if (typeof status === "string" && status.trim()) verdict.status = status.trim();
    if (typeof reason === "string" && reason.trim()) verdict.reason = reason.trim();
  }
  return verdict;
}

export function isReplaySession(session: SessionRow | null | undefined): boolean {
  return session?.metadata?.replay === true && session?.metadata?.not_live_control === true;
}

// Provenance for a replay session's intent authority: attached replays run
// under an existing goal's ledger (recorded rulings govern); fixture replays
// mint their own goal.
export function replayGoalSourceCopy(session: SessionRow | null | undefined): string {
  if (!isReplaySession(session)) return "";
  return session?.metadata?.replay_goal_source === "attached"
    ? " · governed by an existing goal's ledger"
    : "";
}

// A live worker is the honest counterpart to a replay: a real harness (not the
// in-process synthetic adapter) whose transport was probed as Deep or Strong.
// Basic/observe-only/unprobed sessions get no live label — PEX can see them
// but does not claim live control.
const LIVE_SUPPORT = new Set(["deep", "strong"]);

export function isLiveWorkerSession(session: SessionRow | null | undefined): boolean {
  if (!session || isReplaySession(session) || session.harness_type === "synthetic") return false;
  const label = session.capabilities?.support_label;
  return typeof label === "string" && LIVE_SUPPORT.has(label.toLowerCase());
}

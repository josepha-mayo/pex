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

// Curated judge path: the grid is a narrative, not an alphabetical list. The
// first runs are the most legible cheats (claims done, no tests), then the
// tamper family, then constraint/drift arcs, then the durable-ruling act
// (continuity → selfcheck → the compliance control), then captured-live
// provenance last. Anything unlisted sorts alphabetically at the end.
const FIXTURE_ORDER = [
  "premature_stop_eval",
  "tampered_acceptance_eval",
  "stale_evidence_eval",
  "config_injection_eval",
  "xfail_marker_eval",
  "dataset_before_eval",
  "constraint_violation_eval",
  "constraint_block_eval",
  "nudge_dispute_eval",
  "drift_loop_eval",
  "ruling_continuity_eval",
  "ruling_selfcheck_eval",
  "ruling_compliance_eval",
  "captured_live_eval",
  "captured_handoff_eval",
];

export function orderFixtures(fixtures: DemoFixture[]): DemoFixture[] {
  const rank = new Map(FIXTURE_ORDER.map((id, index) => [id, index]));
  return [...fixtures].sort((a, b) => {
    const ra = rank.get(a.id) ?? FIXTURE_ORDER.length;
    const rb = rank.get(b.id) ?? FIXTURE_ORDER.length;
    return ra - rb || a.id.localeCompare(b.id);
  });
}

// The first fixture in the curated order is the most legible entry point —
// judges get a "start here" affordance instead of an arbitrary first click.
export function isRecommendedStart(fixture: DemoFixture): boolean {
  return fixture.id === FIXTURE_ORDER[0];
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
  // Set when the same trajectory was run twice back-to-back: whether the
  // observed arcs were identical — the determinism claim, checked live.
  determinism?: "identical" | "diverged";
  // The fixture's declared arc scored by the bridge against this exact run —
  // the same contract eval_replays.py enforces suite-wide. Absent when the
  // fixture declares no contract; `met: null` means scoring was skipped.
  declared?: {
    met: boolean | null;
    failures: string[];
    summary?: string;
  };
  // The worker's own strongest claim and what independent verification made
  // of it — a narration-only supervisor would have accepted the claim as-is.
  narrationCheck?: {
    claim: string;
    status: string;
  };
  // Verbatim deciding evidence for this session's claims — sealed-surface
  // diffs, pytest exits, staleness markers. This is what "independent
  // verification" means concretely; the card quotes it.
  verifiedFacts?: string[];
};

// Two arcs count as identical when the intervention chain, the cited
// constraint, and the adjudicated completion all match — determinism is
// claimed only on full agreement.
export function replayVerdictsIdentical(a: ReplayVerdict | null, b: ReplayVerdict | null): boolean {
  if (!a || !b) return false;
  return (
    JSON.stringify(a.actions) === JSON.stringify(b.actions) &&
    (a.citedConstraint || "") === (b.citedConstraint || "") &&
    (a.status || "") === (b.status || "")
  );
}

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
  if (isRecord(payload.declared)) {
    const { met, failures, expectation } = payload.declared;
    const declared: NonNullable<ReplayVerdict["declared"]> = {
      met: met === true ? true : met === false ? false : null,
      failures: Array.isArray(failures)
        ? failures
            .filter((f): f is string => typeof f === "string" && f.trim().length > 0)
            .map((f) => f.trim().slice(0, 240))
            .slice(0, 8)
        : [],
    };
    if (isRecord(expectation) && typeof expectation.summary === "string" && expectation.summary.trim()) {
      declared.summary = expectation.summary.trim().slice(0, 240);
    }
    verdict.declared = declared;
  }
  if (isRecord(payload.narration_check)) {
    const { claim, status } = payload.narration_check;
    if (typeof claim === "string" && claim.trim() && typeof status === "string" && status.trim()) {
      verdict.narrationCheck = {
        claim: claim.trim().slice(0, 240),
        status: status.trim().slice(0, 64),
      };
    }
  }
  if (Array.isArray(payload.verified_facts)) {
    const facts = payload.verified_facts
      .filter((item): item is string => typeof item === "string" && Boolean(item.trim()))
      .map((item) => item.trim().slice(0, 200))
      .slice(0, 6);
    if (facts.length) verdict.verifiedFacts = facts;
  }
  return verdict;
}

export function isReplaySession(session: SessionRow | null | undefined): boolean {
  return session?.metadata?.replay === true && session?.metadata?.not_live_control === true;
}

// The replay vendor id embeds the fixture: replay-<fixture>-<hex> (or
// replay-inline-<hex> for judge-authored trajectories). The rail labels the
// run by its source so several replays stay distinguishable.
const REPLAY_VENDOR_ID = /^replay-([a-z0-9][a-z0-9_-]{0,62})-[0-9a-f]{4,}$/;

export function replayFixtureLabel(session: SessionRow | null | undefined): string | null {
  if (!isReplaySession(session) || typeof session?.id !== "string") return null;
  const vendor = session.id.split(":").pop() || "";
  const match = REPLAY_VENDOR_ID.exec(vendor);
  if (!match) return null;
  return match[1] === "inline" ? "custom trajectory" : match[1];
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

// One-line summary of a replay session's observed supervision arc, derived
// from the session's fetched interventions — works for reopened sessions,
// not just the run the client just performed.
export function replayArcCopy(
  session: SessionRow | null | undefined,
  interventions: { action_taken?: string; evidence?: string[] }[] | null | undefined,
  completionStatus?: string | null,
): string {
  if (!isReplaySession(session)) return "";
  const actions = (interventions || [])
    .map((item) => item.action_taken)
    .filter((item): item is string => typeof item === "string" && item !== "NOOP");
  const parts: string[] = [];
  if (actions.length) {
    parts.push(`arc: ${actions.map((a) => a.toLowerCase().replace(/_/g, " ")).join(" → ")}`);
  }
  const cited = (interventions || [])
    .flatMap((item) => item.evidence || [])
    .find((item) => typeof item === "string" && item.startsWith("agent_contradiction:"));
  if (cited) {
    const constraint = cited.slice("agent_contradiction:".length).trim();
    if (constraint) parts.push(`cites “${constraint}”`);
  }
  if (typeof completionStatus === "string" && completionStatus.trim()) {
    parts.push(`completion ${completionStatus.trim()}`);
  }
  return parts.join(" · ");
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

import assert from "node:assert/strict";
import test from "node:test";

import {
  isLiveWorkerSession,
  isReplaySession,
  replayGoalSourceCopy,
  parseReplayGoalSource,
  parseReplaySessionId,
  parseReplayVerdict,
  parseTrajectoriesResponse,
  replayArcCopy,
  replayFixtureLabel,
  replayVerdictsIdentical,
} from "./demoReplay.ts";
import type { SessionRow } from "./types.ts";

const listed = {
  replay: true,
  not_live_control: true,
  fixtures: [
    { id: "premature_stop_eval", title: "False completion without tests", replay: true, events: 3 },
    { id: "tampered_acceptance_eval", title: "Reward hacking", replay: true, events: 6 },
    {
      id: "captured_live_eval",
      title: "Captured live tamper run",
      summary: "What this arc proves.",
      replay: true,
      events: 32,
      captured_from_live_session: "opencode:ses_x",
    },
    {
      id: "ruling_continuity_eval",
      title: "Second act: the ruling still governs",
      replay: true,
      events: 4,
      attach_hint: "Attach to a goal carrying a recorded ruling.",
    },
  ],
};

test("the replay control only appears for an honestly labeled fixture list", () => {
  const fixtures = parseTrajectoriesResponse(listed);
  assert.equal(fixtures?.length, 4);
  assert.equal(fixtures?.[1]?.id, "tampered_acceptance_eval");
  assert.equal(fixtures?.[2]?.capturedFromLive, "opencode:ses_x");
  assert.equal(fixtures?.[0]?.capturedFromLive, undefined);
  assert.equal(fixtures?.[2]?.summary, "What this arc proves.");
  assert.equal(fixtures?.[0]?.summary, undefined);
  assert.equal(fixtures?.[3]?.attachHint, "Attach to a goal carrying a recorded ruling.");
  assert.equal(fixtures?.[0]?.attachHint, undefined);

  for (const payload of [
    null, "[]", 42,
    { fixtures: [] },
    { replay: false, not_live_control: true, fixtures: listed.fixtures },
    { replay: true, not_live_control: false, fixtures: listed.fixtures },
    { replay: true, not_live_control: true },
    { replay: true, not_live_control: true, fixtures: "none" },
    { replay: true, not_live_control: true, fixtures: [] },
  ]) {
    assert.equal(parseTrajectoriesResponse(payload), null);
  }
});

test("one malformed fixture removes the entire replay control", () => {
  for (const bad of [
    { title: "No id" },
    { id: "ok", title: "" },
    { id: "../escape", title: "traversal" },
    { id: "ID With Spaces", title: "x" },
    { id: 42, title: "x" },
    { id: "ok_id", title: "x", summary: 42 },
    { id: "ok_id", title: "x", attach_hint: 42 },
    "tampered_acceptance_eval",
  ]) {
    const payload = {
      replay: true,
      not_live_control: true,
      fixtures: [...listed.fixtures, bad],
    };
    assert.equal(parseTrajectoriesResponse(payload), null);
  }
});

test("a replay result must return a labeled session id", () => {
  assert.equal(
    parseReplaySessionId({
      replay: true, not_live_control: true, session_id: "synthetic:replay-x",
    }),
    "synthetic:replay-x",
  );
  for (const payload of [
    null, {},
    { replay: true, not_live_control: true },
    { replay: true, not_live_control: true, session_id: "" },
    { replay: false, not_live_control: true, session_id: "synthetic:replay-x" },
    { replay: true, not_live_control: false, session_id: "synthetic:replay-x" },
    { replay: true, not_live_control: true, session_id: 7 },
  ]) {
    assert.equal(parseReplaySessionId(payload), null);
  }
});

test("goal_source: attached is the only attach signal the UI trusts", () => {
  assert.equal(
    parseReplayGoalSource({
      replay: true, not_live_control: true,
      session_id: "synthetic:replay-x", goal_source: "attached",
    }),
    "attached",
  );
  for (const payload of [
    null, {},
    { replay: true, not_live_control: true, session_id: "x", goal_source: "fixture" },
    { replay: true, not_live_control: true, session_id: "x", goal_source: "ATTACHED" },
    { replay: true, not_live_control: true, session_id: "x" },
  ]) {
    assert.equal(parseReplayGoalSource(payload), null);
  }
});

test("replay sessions stay honestly labeled and only when both markers hold", () => {
  const replay: SessionRow = {
    id: "synthetic:replay-tampered_acceptance_eval-1",
    harness_type: "synthetic",
    status: "idle",
    metadata: { replay: true, not_live_control: true },
  };
  assert.equal(isReplaySession(replay), true);
  for (const metadata of [
    undefined, {}, { replay: false }, { replay: true },
    { not_live_control: true }, { replay: true, not_live_control: false },
    { replay: "true", not_live_control: true },
  ]) {
    assert.equal(isReplaySession({ ...replay, metadata }), false);
  }
  assert.equal(isReplaySession(null), false);
  assert.equal(isReplaySession(undefined), false);
});

test("replay goal-source copy surfaces attached provenance only", () => {
  const base: SessionRow = {
    id: "synthetic:replay-x-1",
    harness_type: "synthetic",
    status: "idle",
    metadata: { replay: true, not_live_control: true },
  };
  assert.equal(replayGoalSourceCopy(base), "");
  const attached = {
    ...base,
    metadata: { ...base.metadata, replay_goal_source: "attached" },
  };
  assert.match(replayGoalSourceCopy(attached), /existing goal/);
  const fixture = {
    ...base,
    metadata: { ...base.metadata, replay_goal_source: "fixture" },
  };
  assert.equal(replayGoalSourceCopy(fixture), "");
  assert.equal(replayGoalSourceCopy({ ...base, metadata: {} }), "");
});

test("replay verdict carries the observed arc and the adjudicated completion", () => {
  const verdict = parseReplayVerdict({
    replay: true,
    not_live_control: true,
    session_id: "synthetic:replay-x-1",
    interventions: [
      {
        action_taken: "SEND_NUDGE",
        evidence: ["agent_contradiction:Do not modify the sealed baseline test file"],
      },
      { type: "SUPPRESSED_COOLDOWN" },
      { action_taken: "NOOP" },
      { action_taken: 42 },
      "not-a-record",
    ],
    completion: { status: "uncertain", reason: "no_current_supported_completion_evidence" },
  });
  assert.deepEqual(verdict, {
    actions: ["SEND_NUDGE", "SUPPRESSED_COOLDOWN"],
    citedConstraint: "Do not modify the sealed baseline test file",
    status: "uncertain",
    reason: "no_current_supported_completion_evidence",
  });
  assert.deepEqual(
    parseReplayVerdict({ replay: true, not_live_control: true, session_id: "s" }),
    { actions: [] },
  );
  assert.equal(parseReplayVerdict({ replay: true, not_live_control: false }), null);
  assert.equal(parseReplayVerdict(null), null);
});

test("replay rail label names the source fixture or the custom trajectory", () => {
  const base: SessionRow = {
    id: "synthetic:replay-ruling_continuity_eval-c720e688",
    harness_type: "synthetic",
    status: "stopped",
    metadata: { replay: true, not_live_control: true },
  };
  assert.equal(replayFixtureLabel(base), "ruling_continuity_eval");
  const inline = { ...base, id: "synthetic:replay-inline-a6795034" };
  assert.equal(replayFixtureLabel(inline), "custom trajectory");
  const nonReplay = { ...base, metadata: { replay: true, not_live_control: false } };
  assert.equal(replayFixtureLabel(nonReplay), null);
  const oddId = { ...base, id: "synthetic:other-1" };
  assert.equal(replayFixtureLabel(oddId), null);
});

test("a reopened replay restates its arc, citation, and verdict from interventions", () => {
  const session = {
    id: "synthetic:replay-x-1",
    harness_type: "synthetic",
    status: "stopped",
    metadata: { replay: true, not_live_control: true },
  } as SessionRow;
  const copy = replayArcCopy(
    session,
    [
      { action_taken: "SEND_NUDGE", evidence: ["agent_contradiction:Do not modify the sealed baseline test file"] },
      { action_taken: "SUPPRESSED_COOLDOWN" },
      { action_taken: "NOOP" },
    ],
    "uncertain",
  );
  assert.match(copy, /send nudge → suppressed cooldown/);
  assert.match(copy, /sealed baseline test file/);
  assert.match(copy, /completion uncertain/);
  assert.doesNotMatch(copy, /noop/i);
  assert.equal(replayArcCopy(session, [], "uncertain"), "completion uncertain");
  assert.equal(
    replayArcCopy({ ...session, metadata: { replay: true, not_live_control: false } }, []),
    "",
  );
});

test("two arcs count identical only on full agreement", () => {
  const base = { actions: ["SEND_NUDGE", "SUPPRESSED_COOLDOWN"], citedConstraint: "x", status: "uncertain" };
  assert.equal(replayVerdictsIdentical(base, { ...base }), true);
  assert.equal(replayVerdictsIdentical(base, { ...base, actions: ["SEND_NUDGE"] }), false);
  assert.equal(replayVerdictsIdentical(base, { ...base, status: "verified_complete" }), false);
  assert.equal(replayVerdictsIdentical(base, { ...base, citedConstraint: "y" }), false);
  assert.equal(replayVerdictsIdentical(base, null), false);
  assert.equal(replayVerdictsIdentical(base, { actions: ["SEND_NUDGE", "SUPPRESSED_COOLDOWN"], status: "uncertain" }), false);
});

test("live worker label requires a real harness with a Deep or Strong transport", () => {
  const live = {
    id: "opencode:ses_1",
    harness_type: "opencode",
    status: "running",
    capabilities: { support_label: "deep" },
  } as SessionRow;
  assert.equal(isLiveWorkerSession(live), true);
  assert.equal(isLiveWorkerSession({ ...live, capabilities: { support_label: "strong" } } as SessionRow), true);
  for (const support_label of ["basic", "observe_only", "unavailable", undefined]) {
    assert.equal(isLiveWorkerSession({ ...live, capabilities: { support_label } } as SessionRow), false);
  }
  assert.equal(isLiveWorkerSession({ ...live, capabilities: undefined } as SessionRow), false);
  assert.equal(isLiveWorkerSession({ ...live, harness_type: "synthetic" } as SessionRow), false);
  assert.equal(
    isLiveWorkerSession({ ...live, metadata: { replay: true, not_live_control: true } } as SessionRow),
    false,
  );
  assert.equal(isLiveWorkerSession(null), false);
});

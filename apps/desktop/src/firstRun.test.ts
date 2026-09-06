import assert from "node:assert/strict";
import test from "node:test";

import { firstRunGuidance, statusWithFirstRunGuidance, supervisorAvailability } from "./firstRun.ts";
import type { Goal, SessionRow, StatusCopy, SupervisorInfo } from "./types.ts";

const worker: SessionRow = {
  id: "codex:thread-1",
  harness_type: "codex",
  status: "idle",
};

const goal: Goal = { id: "goal-1", title: "Ship", objective: "Ship the release" };

test("first-run guidance does not infer readiness from stale session or goal state", () => {
  for (const [sessionFresh, goalFresh] of [[false, true], [true, false]]) {
    const guidance = firstRunGuidance({ current: worker, attachedGoal: null, sessionFresh, goalFresh });
    assert.deepEqual(guidance?.cta, null);
    assert.equal(guidance?.state, "unavailable");
  }
});

test("first-run guidance distinguishes no usable worker from an attachable unbound worker", () => {
  const noWorker = firstRunGuidance({ sessionFresh: true, goalFresh: true });
  assert.deepEqual(noWorker?.cta, { intent: "connect", label: "How to connect a worker" });

  const desktopOnly = firstRunGuidance({
    current: { ...worker, id: "codex:desktop", metadata: { source: "desktop" } },
    sessionFresh: true,
    goalFresh: true,
  });
  assert.equal(desktopOnly?.cta?.intent, "connect");

  for (const current of [
    { ...worker, status: "detached" },
    { ...worker, status: "unknown" },
    { ...worker, capabilities: { support_label: "unavailable" } },
  ]) {
    const unavailable = firstRunGuidance({ current, sessionFresh: true, goalFresh: true });
    assert.equal(unavailable?.cta?.intent, "connect");
  }

  const unbound = firstRunGuidance({ current: worker, sessionFresh: true, goalFresh: true });
  assert.deepEqual(unbound?.cta, { intent: "goal", label: "Set a goal for Codex" });
});

test("first-run guidance ends onboarding only for a current matching attached goal", () => {
  assert.equal(
    firstRunGuidance({
      current: { ...worker, goal_id: goal.id },
      attachedGoal: goal,
      sessionFresh: true,
      goalFresh: true,
    }),
    null,
  );
  const unresolved = firstRunGuidance({
    current: { ...worker, goal_id: goal.id },
    attachedGoal: null,
    sessionFresh: true,
    goalFresh: true,
  });
  assert.equal(unresolved?.state, "unavailable");
  assert.equal(unresolved?.cta, null);
});

test("supervisor availability never treats configuration as an inference receipt", () => {
  const configured: SupervisorInfo = { model_loaded: true, provider: "openrouter" };
  assert.equal(supervisorAvailability({ supervisor: configured, supervisorFresh: false }).state, "unavailable");
  const deterministic = supervisorAvailability({ supervisor: null, supervisorFresh: true });
  assert.equal(deterministic.state, "unavailable");
  const deterministicOnly = supervisorAvailability({ supervisor: {}, supervisorFresh: true });
  assert.equal(deterministicOnly.state, "deterministic_only");
  const unverified = supervisorAvailability({ supervisor: configured, supervisorFresh: true });
  assert.equal(unverified.state, "configured_unverified");
  assert.match(unverified.copy, /does not prove connection or inference/i);
});

test("first-run wording only replaces a genuinely quiet unpaused status", () => {
  const guidance = firstRunGuidance({ current: worker, sessionFresh: true, goalFresh: true });
  assert.ok(guidance);
  const quiet: StatusCopy = { tone: "quiet", label: "Nothing needs babysitting", detail: "Nothing needs babysitting." };
  assert.deepEqual(statusWithFirstRunGuidance(quiet, guidance, false), {
    tone: "quiet",
    label: "No goal attached",
    detail: "Tell PEX what done means for this worker.",
  });

  const connect = firstRunGuidance({ sessionFresh: true, goalFresh: true });
  assert.ok(connect);
  assert.deepEqual(statusWithFirstRunGuidance(quiet, connect, false), {
    tone: "quiet",
    label: "No worker connected",
    detail: "Connect your existing work below to get started.",
  });

  const paused: StatusCopy = { tone: "quiet", label: "PEX", detail: "Supervision is paused. PEX will not intervene until it is resumed." };
  assert.deepEqual(statusWithFirstRunGuidance(paused, guidance, true), paused);

  for (const tone of ["work", "watch", "need", "offline"] as const) {
    const operational: StatusCopy = { tone, label: "PEX", detail: "Current operational state" };
    assert.deepEqual(statusWithFirstRunGuidance(operational, guidance, false), operational);
  }
});

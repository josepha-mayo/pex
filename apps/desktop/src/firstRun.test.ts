import assert from "node:assert/strict";
import test from "node:test";

import { firstRunGuidance, statusWithFirstRunGuidance, supervisorAvailability } from "./firstRun.ts";
import type { Goal, SessionRow, StatusCopy, SupervisorInfo } from "./types.ts";
import { supervisorHonestyCopy } from "./viewModel.ts";

const worker: SessionRow = {
  id: "codex:thread-1",
  harness_type: "codex",
  status: "idle",
  capabilities: { observe_messages: true, support_label: "deep" },
};

const goal: Goal = { id: "goal-1", title: "Ship", objective: "Ship the release" };

test("discovery cannot promise supervision without an explicit observation capability", () => {
  for (const capabilities of [undefined, {}, { support_label: "deep" },
    { send_message: true }, { observe_messages: "true" },
    { observe_messages: false, observe_session_status: false }]) {
    const current = { ...worker, status: "discovered", capabilities };
    for (const attached of [false, true]) {
      const guidance = firstRunGuidance({
        current: { ...current, goal_id: attached ? goal.id : undefined },
        attachedGoal: attached ? goal : null, sessionFresh: true, goalFresh: true,
      });
      assert.equal(guidance?.state, "connect_worker");
      assert.equal(guidance?.cta?.intent, "connect");
    }
  }
  for (const capabilities of [
    { observe_session_status: true, support_label: "basic" },
    { observe_tool_calls: true, support_label: "observe_only", send_message: false },
  ]) {
    const guidance = firstRunGuidance({
      current: { ...worker, status: "discovered", capabilities },
      sessionFresh: true, goalFresh: true,
    });
    assert.equal(guidance?.state, "set_goal");
  }
});

test("first-run guidance does not infer readiness from stale session or goal state", () => {
  for (const [sessionFresh, goalFresh] of [[false, true], [true, false]]) {
    const guidance = firstRunGuidance({ current: worker, attachedGoal: null, sessionFresh, goalFresh });
    assert.deepEqual(guidance?.cta, null);
    assert.equal(guidance?.state, "unavailable");
  }
});

test("first-run guidance stops claiming an active connection attempt after the bridge fails", () => {
  const guidance = firstRunGuidance({
    current: worker,
    attachedGoal: null,
    sessionFresh: false,
    goalFresh: false,
    bridgeError: "Bridge offline",
  });
  assert.deepEqual(guidance, {
    state: "unavailable",
    title: "Local bridge unavailable",
    detail: "Restart PEX or retry the local bridge before relying on worker state.",
    cta: null,
  });
});

test("first-run guidance distinguishes no usable worker from an attachable unbound worker", () => {
  const noWorker = firstRunGuidance({ sessionFresh: true, goalFresh: true });
  assert.deepEqual(noWorker?.cta, { intent: "connect", label: "How to connect a worker" });
  const petWindowNoWorker = firstRunGuidance({ sessionFresh: true, goalFresh: false });
  assert.equal(petWindowNoWorker?.title, "Connect a worker");

  const desktopOnly = firstRunGuidance({
    current: { ...worker, id: "codex:desktop", metadata: { source: "desktop" } },
    sessionFresh: true,
    goalFresh: true,
  });
  assert.equal(desktopOnly?.cta?.intent, "connect");
  assert.equal(desktopOnly?.title, "Connect a supported session");
  assert.equal(desktopOnly?.detail.includes("Codex session record"), true);
  assert.equal(desktopOnly?.detail.includes("create a worker in your project folder"), true);
  assert.equal(desktopOnly?.detail.includes("observe an existing Codex CLI thread"), true);
  assert.equal(desktopOnly?.detail.includes("does not control Codex Desktop tasks"), true);
  assert.deepEqual(desktopOnly?.cta, { intent: "connect", label: "Open Connections" });

  const detachedOpenCode = firstRunGuidance({
    current: { ...worker, id: "opencode:session-1", harness_type: "opencode", status: "detached" },
    sessionFresh: true,
    goalFresh: true,
  });
  assert.equal(detachedOpenCode?.detail.includes("OpenCode session record"), true);
  assert.equal(detachedOpenCode?.detail.includes("running OpenCode server session"), true);
  assert.equal(detachedOpenCode?.detail.includes("Codex Desktop"), false);

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

test("supervisor startup guidance distinguishes loading, timeout, failure and disabled", () => {
  for (const [activation_status, expected] of [
    ["loading", /loading.*saved supervisor/i],
    ["timed_out", /timed out.*Save supervisor.*retry/i],
    ["failed", /could not.*loaded.*Save supervisor/i],
    ["disabled", /disabled.*launch configuration/i],
  ] as const) {
    const supervisor: SupervisorInfo = { model_loaded: false, activation_status };
    const availability = supervisorAvailability({ supervisor, supervisorFresh: true });
    assert.equal(availability.state, "deterministic_only");
    assert.match(availability.copy, expected);
    assert.match(supervisorHonestyCopy(supervisor), expected);
    assert.doesNotMatch(availability.copy, /will automatically retry|connected successfully/i);
    assert.doesNotMatch(
      supervisorAvailability({ supervisor, supervisorFresh: false }).copy, expected,
    );
  }
});

test("Home explains a fresh zero review limit even when the model is configured", () => {
  for (const model_loaded of [true, false]) {
    const supervisor: SupervisorInfo = { model_loaded, max_dispatches_per_session: 0 };
    const availability = supervisorAvailability({ supervisor, supervisorFresh: true });
    assert.equal(availability.state, "paused");
    assert.match(availability.copy, /reviews are paused.*deterministic checks.*settings.*review limit/i);
    assert.doesNotMatch(availability.copy, /supervisor is configured/i);
    const stale = supervisorAvailability({ supervisor, supervisorFresh: false });
    assert.equal(stale.state, "unavailable");
    assert.doesNotMatch(stale.copy, /reviews are paused/i);
  }
  for (const max_dispatches_per_session of [undefined, null, 3]) {
    const availability = supervisorAvailability({
      supervisor: { model_loaded: true, max_dispatches_per_session }, supervisorFresh: true,
    });
    assert.equal(availability.state, "configured_unverified");
  }
});

test("successful configuration clears stale startup recovery copy without claiming inference", () => {
  const supervisor: SupervisorInfo = { model_loaded: true, activation_status: "timed_out" };
  const availability = supervisorAvailability({ supervisor, supervisorFresh: true });
  assert.equal(availability.state, "configured_unverified");
  assert.doesNotMatch(availability.copy, /timed out|retry/i);
  assert.doesNotMatch(supervisorHonestyCopy(supervisor), /timed out|retry/i);
  assert.match(supervisorHonestyCopy(supervisor), /does not verify connection or inference/i);
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
    label: "Connect a worker",
    detail: "Connect a running OpenCode session or create an isolated Codex connection.",
  });

  const paused: StatusCopy = { tone: "quiet", label: "PEX", detail: "Supervision is paused. PEX will not intervene until it is resumed." };
  assert.deepEqual(statusWithFirstRunGuidance(paused, guidance, true), paused);

  for (const tone of ["work", "watch", "need", "offline"] as const) {
    const operational: StatusCopy = { tone, label: "PEX", detail: "Current operational state" };
    assert.deepEqual(statusWithFirstRunGuidance(operational, guidance, false), operational);
  }
});

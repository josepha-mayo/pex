import assert from "node:assert/strict";
import test from "node:test";

import {
  isLiveWorkerSession,
  isReplaySession,
  parseReplaySessionId,
  parseTrajectoriesResponse,
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
  ],
};

test("the replay control only appears for an honestly labeled fixture list", () => {
  const fixtures = parseTrajectoriesResponse(listed);
  assert.equal(fixtures?.length, 3);
  assert.equal(fixtures?.[1]?.id, "tampered_acceptance_eval");
  assert.equal(fixtures?.[2]?.capturedFromLive, "opencode:ses_x");
  assert.equal(fixtures?.[0]?.capturedFromLive, undefined);
  assert.equal(fixtures?.[2]?.summary, "What this arc proves.");
  assert.equal(fixtures?.[0]?.summary, undefined);

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

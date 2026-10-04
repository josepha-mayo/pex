import assert from "node:assert/strict";
import test from "node:test";

import {
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
  ],
};

test("the replay control only appears for an honestly labeled fixture list", () => {
  const fixtures = parseTrajectoriesResponse(listed);
  assert.equal(fixtures?.length, 2);
  assert.equal(fixtures?.[1]?.id, "tampered_acceptance_eval");

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

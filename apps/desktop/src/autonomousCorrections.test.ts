import assert from "node:assert/strict";
import test from "node:test";
import { correctionUpdate, parseCorrectionStatus } from "./autonomousCorrections.ts";

function fixture() {
  return {
    enabled: false, effective_enabled: false, connected: true, reason: "explicit_grant_required", delivery_proven: false,
    scope: {
      schema: "pex.autonomous-correction-grant.v1", session_id: "codex:fixture", thread_id: "fixture",
      goal_id: "goal", project_id: "project", control_revision: 3, goal_intent_revision: 2,
      goal_intent_hash: "a".repeat(64), project_binding: "identity:fixture", workspace_sha256: "b".repeat(64),
      subscription_authorization_id: "authorization", connection_generation: 1,
      root_session_id: "root-fixture", subscription_selection_id: "selection-fixture", endpoint_identity: "endpoint-fixture",
      allowed_intervention_types: ["CONTINUE_SESSION", "INJECT_CONTEXT", "REQUEST_VERIFICATION", "SEND_NUDGE"],
    },
  };
}

test("request binds displayed scope and contains no actor or generic worker instruction", () => {
  const status = parseCorrectionStatus(fixture(), "codex:fixture");
  const body = correctionUpdate(status, true, "fixture-key");
  assert.equal(body.expected_control_revision, 3);
  assert.equal(body.expected_goal_id, "goal");
  assert.equal(body.expected_subscription_authorization_id, "authorization");
  assert.equal(body.expected_workspace_sha256, "b".repeat(64));
  assert.equal(body.enabled, true);
  assert.equal("principal_id" in body, false);
  assert.equal("text" in body, false);
});

for (const [key, value] of Object.entries({
  session_id: "another-session", control_revision: true, connection_generation: 0,
  goal_intent_revision: Number.MAX_SAFE_INTEGER + 1, goal_intent_hash: "bad",
  workspace_sha256: null, subscription_authorization_id: "", goal_id: "bad\nidentity",
  allowed_intervention_types: ["SEND_NUDGE", "START_AGENT"],
  root_session_id: null, subscription_selection_id: "", endpoint_identity: "bad\nendpoint",
})) {
  test(`malformed or expanded ${key} is refused`, () => {
    const raw = fixture();
    Object.assign(raw.scope, { [key]: value });
    assert.throws(() => parseCorrectionStatus(raw, "codex:fixture"));
  });
}

test("scope absence is not empty permission", () => {
  const raw = { ...fixture(), scope: null };
  const status = parseCorrectionStatus(raw, "codex:fixture");
  assert.throws(() => correctionUpdate(status, true, "fixture-key"));
  assert.throws(() => parseCorrectionStatus({ ...raw, enabled: true }, "codex:fixture"));
});

test("disconnected grant cannot be enabled or advertised effective", () => {
  const raw = { ...fixture(), enabled: true, connected: false };
  const status = parseCorrectionStatus(raw, "codex:fixture");
  assert.throws(() => correctionUpdate(status, true, "fixture-key"));
  assert.equal(correctionUpdate(status, false, "fixture-disable").enabled, false);
  assert.throws(() => parseCorrectionStatus({ ...raw, effective_enabled: true }, "codex:fixture"));
});

test("permission does not prove delivery", () => {
  assert.throws(() => parseCorrectionStatus({ ...fixture(), delivery_proven: true }, "codex:fixture"));
});

test("canonical revision-zero goal can be explicitly authorized", () => {
  const raw = fixture();
  raw.scope.goal_intent_revision = 0;
  const status = parseCorrectionStatus(raw, "codex:fixture");
  assert.equal(correctionUpdate(status, true, "fixture-key").expected_goal_intent_revision, 0);
});

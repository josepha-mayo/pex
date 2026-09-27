import assert from "node:assert/strict";
import { test } from "node:test";
import { BridgeRequestError } from "./decisionContract.ts";
import { advanceTaskAttemptOutcome, readOperatorTaskReceipt, sendOperatorTask } from "./operatorTask.ts";
import type { SharedRequest } from "./sharedConnection.ts";

const binding = { sessionId: "codex:worker-1", goalId: "goal-1", projectId: "project-1" };
const key = "task-attempt-0001";
const receipt = {
  effect_id: "effect-1", action_kind: "session_message", idempotency_key: key,
  source_session_id: binding.sessionId, target_session_id: binding.sessionId,
  goal_id: binding.goalId, project_id: binding.projectId, state: "delivered",
  result: { status: "delivered" },
};

test("one task attempt sends exact binding and accepts a matching durable receipt", async () => {
  const calls: [string, RequestInit | undefined][] = [];
  const request: SharedRequest = async (path, init) => {
    calls.push([path, init]);
    return { ok: true, status: "delivered", receipt };
  };
  const result = await sendOperatorTask(request, binding, "Review the parser.", key, new AbortController().signal);
  assert.equal(result, "effect-1");
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/v1/sessions/codex%3Aworker-1/message");
  assert.deepEqual(JSON.parse(String(calls[0][1]?.body)), {
    idempotency_key: key, text: "Review the parser.",
  });
});

test("receipt for another worker or goal never confirms delivery", async () => {
  for (const changed of [{ source_session_id: "codex:other" }, { goal_id: "other-goal" }, { state: "dispatching" }]) {
    const request: SharedRequest = async () => ({ ok: true, status: "delivered", receipt: { ...receipt, ...changed } });
    await assert.rejects(sendOperatorTask(request, binding, "Review the parser.", key, new AbortController().signal), /not confirmed/);
  }
});

test("blank task never reaches the bridge", async () => {
  const request: SharedRequest = async () => { throw new Error("called"); };
  await assert.rejects(sendOperatorTask(request, binding, "   ", key, new AbortController().signal), /Enter a task/);
});

test("receipt lookup is read-only and bound to the original worker", async () => {
  const paths: string[] = [];
  const request: SharedRequest = async (path, init) => {
    paths.push(path);
    assert.equal(init, undefined);
    return { ok: true, status: "delivered", receipt };
  };
  assert.deepEqual(await readOperatorTaskReceipt(request, binding, key), {
    status: "delivered", effectId: "effect-1",
  });
  assert.deepEqual(paths, ["/v1/sessions/codex%3Aworker-1/messages/task-attempt-0001/receipt"]);
});

test("unknown receipt stays absent, while a mismatched receipt fails closed", async () => {
  const missing: SharedRequest = async () => { throw new BridgeRequestError("missing", { status: 404, code: "operator_message_receipt_not_found" }); };
  assert.equal(await readOperatorTaskReceipt(missing, binding, key), null);
  const olderBridge: SharedRequest = async () => { throw new BridgeRequestError("route missing", { status: 404 }); };
  await assert.rejects(readOperatorTaskReceipt(olderBridge, binding, key), /route missing/);
  const wrong: SharedRequest = async () => ({ ok: true, status: "delivered", receipt: { ...receipt, goal_id: "other" } });
  await assert.rejects(readOperatorTaskReceipt(wrong, binding, key), /not confirmed/);
});

test("late GET failure and POST failure cannot downgrade a delivered task", () => {
  const delivered = { kind: "delivered", idempotencyKey: key, message: "receipt confirmed" } as const;
  const late404 = { kind: "uncertain", idempotencyKey: key, message: "not found" } as const;
  assert.equal(advanceTaskAttemptOutcome(delivered, late404), delivered);
  assert.equal(advanceTaskAttemptOutcome(delivered, { ...late404, kind: "in_progress" }), delivered);
  assert.equal(advanceTaskAttemptOutcome(delivered, { ...late404, idempotencyKey: "different-attempt" }), delivered);
});

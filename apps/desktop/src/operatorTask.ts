import type { SharedRequest } from "./sharedConnection.ts";
import { BridgeRequestError, isRecord } from "./decisionContract.ts";

export type TaskBinding = { sessionId: string; goalId: string; projectId: string };
export type TaskReceiptStatus = "delivered" | "reserved" | "dispatching" | "delivery_uncertain" | "failed" | "skipped";
export type TaskAttemptOutcome = {
  kind: "delivered" | "uncertain" | "in_progress";
  message: string;
  idempotencyKey: string;
};

/** Delayed HTTP failures cannot downgrade confirmed delivery or replace a newer attempt. */
export function advanceTaskAttemptOutcome(
  current: TaskAttemptOutcome | null, incoming: TaskAttemptOutcome,
): TaskAttemptOutcome {
  if (current && current.idempotencyKey !== incoming.idempotencyKey) return current;
  if (current?.kind === "delivered" && incoming.kind !== "delivered") return current;
  return incoming;
}

function taskReceipt(
  response: unknown, binding: TaskBinding, idempotencyKey: string,
): { status: TaskReceiptStatus; effectId: string } {
  if (!isRecord(response) || response.ok !== true || !isRecord(response.receipt)) {
    throw new Error("Task receipt was not confirmed for this worker and goal.");
  }
  const receipt = response.receipt;
  const status = response.status;
  if (!(["delivered", "reserved", "dispatching", "delivery_uncertain", "failed", "skipped"] as unknown[]).includes(status)
    || receipt.state !== status || receipt.action_kind !== "session_message"
    || receipt.idempotency_key !== idempotencyKey
    || receipt.source_session_id !== binding.sessionId
    || receipt.target_session_id !== binding.sessionId
    || receipt.goal_id !== binding.goalId
    || receipt.project_id !== binding.projectId
    || typeof receipt.effect_id !== "string" || !receipt.effect_id) {
    throw new Error("Task receipt was not confirmed for this worker and goal.");
  }
  if (status === "delivered" && (!isRecord(receipt.result) || receipt.result.status !== "delivered")) {
    throw new Error("Task delivery receipt was malformed.");
  }
  return { status: status as TaskReceiptStatus, effectId: receipt.effect_id };
}

/** A single explicit operator action; the caller owns the key and never retries automatically. */
export async function sendOperatorTask(
  request: SharedRequest,
  binding: TaskBinding,
  text: string,
  idempotencyKey: string,
  signal: AbortSignal,
): Promise<string> {
  if (!text.trim() || text.length > 65_536 || text.includes("\0")) {
    throw new Error("Enter a task of at most 65,536 characters.");
  }
  const response = await request(`/v1/sessions/${encodeURIComponent(binding.sessionId)}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idempotency_key: idempotencyKey, text }),
    signal,
  });
  const receipt = taskReceipt(response, binding, idempotencyKey);
  if (!isRecord(response) || response.ok !== true || receipt.status !== "delivered") {
    throw new Error("Task delivery was not confirmed for this worker and goal. Inspect the worker before sending again.");
  }
  return receipt.effectId;
}

/** Read-only reconciliation: never dispatches a worker message. */
export async function readOperatorTaskReceipt(
  request: SharedRequest, binding: TaskBinding, idempotencyKey: string,
): Promise<{ status: TaskReceiptStatus; effectId: string } | null> {
  try {
    const response = await request(
      `/v1/sessions/${encodeURIComponent(binding.sessionId)}/messages/${encodeURIComponent(idempotencyKey)}/receipt`,
    );
    return taskReceipt(response, binding, idempotencyKey);
  } catch (error) {
    if (error instanceof BridgeRequestError && error.status === 404
      && error.code === "operator_message_receipt_not_found") return null;
    throw error;
  }
}

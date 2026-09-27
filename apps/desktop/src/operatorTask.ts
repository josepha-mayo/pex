import type { SharedRequest } from "./sharedConnection.ts";
import { isRecord } from "./decisionContract.ts";

/** A single explicit operator action; the caller owns the key and never retries automatically. */
export async function sendOperatorTask(
  request: SharedRequest,
  binding: { sessionId: string; goalId: string; projectId: string },
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
  if (!isRecord(response) || !isRecord(response.receipt)) {
    throw new Error("Task delivery was not confirmed. Inspect the worker before sending again.");
  }
  const receipt = response.receipt;
  if (response.ok !== true || response.status !== "delivered"
    || receipt.state !== "delivered" || receipt.action_kind !== "session_message"
    || receipt.idempotency_key !== idempotencyKey
    || receipt.source_session_id !== binding.sessionId
    || receipt.target_session_id !== binding.sessionId
    || receipt.goal_id !== binding.goalId
    || receipt.project_id !== binding.projectId
    || !isRecord(receipt.result) || receipt.result.status !== "delivered"
    || typeof receipt.effect_id !== "string" || !receipt.effect_id) {
    throw new Error("Task delivery was not confirmed for this worker and goal. Inspect the worker before sending again.");
  }
  return receipt.effect_id;
}

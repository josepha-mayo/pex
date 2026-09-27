import type { SharedRequest } from "./sharedConnection.ts";
import { BridgeRequestError } from "./decisionContract.ts";

export function codexConnectionFailure(error: unknown): string {
  if (error instanceof BridgeRequestError) {
    if (error.status === 401 || error.status === 403) {
      return "PEX could not authorize this connection. Restart PEX to refresh its local bridge connection.";
    }
    if (error.status === 400 || error.status === 404) {
      return "Codex CLI was not found. Install Codex CLI, then retry this isolated connection.";
    }
    if (error.status === 409) {
      return "A Codex connection is already active. Inspect the worker list before changing connections.";
    }
    if (error.status === 502) {
      return "PEX could not verify the Codex App Server handshake. No worker turn was started.";
    }
  }
  return "Connection was not confirmed. Check the worker list before retrying; a lost response may leave an isolated connection active.";
}

export function codexCreationFailure(error: unknown): { message: string; uncertain: boolean } {
  if (error instanceof BridgeRequestError) {
    if ([401, 403].includes(error.status)) return {
      uncertain: false,
      message: "Worker creation requires the authenticated PEX desktop app. Open or restart PEX to refresh its local bridge connection.",
    };
    if (error.status === 404) return {
      uncertain: false, message: "This bridge does not support worker creation. Update or restart PEX.",
    };
    if ([400, 409, 422].includes(error.status)) return {
      uncertain: false,
      message: "Worker was not created. Connect isolated Codex and choose an existing absolute project folder.",
    };
  }
  return {
    uncertain: true,
    message: "Worker creation was not confirmed. Inspect Home before retrying; an empty worker may exist. No model turn was requested.",
  };
}

/** One authenticated attach. This starts an isolated App Server, never a model turn. */
export async function connectIsolatedCodex(request: SharedRequest, signal: AbortSignal): Promise<string> {
  const result = await request("/v1/adapters/codex/attach", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    signal,
  });
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("Codex connection response was not confirmed.");
  }
  const receipt = result as Record<string, unknown>;
  if (receipt.ok !== true || receipt.name !== "codex" || receipt.kind !== "stdio"
    || receipt.isolated !== true || receipt.existing_worker !== false
    || typeof receipt.support !== "string") {
    throw new Error("Codex connection response was not confirmed.");
  }
  return receipt.support;
}

/** Creates an empty local worker. Sending its first task is a separate action. */
export async function createCodexWorker(
  request: SharedRequest, workspace: string, signal: AbortSignal,
): Promise<{ id: string; cwd: string }> {
  const folder = workspace.trim();
  if (!folder || folder.includes("\0")) throw new Error("Choose a local project folder.");
  const result = await request("/v1/adapters/codex/threads", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace: folder }), signal,
  });
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("Worker creation was not confirmed.");
  }
  const receipt = result as Record<string, unknown>;
  const session = receipt.session as Record<string, unknown> | undefined;
  const metadata = session?.metadata as Record<string, unknown> | undefined;
  if (receipt.ok !== true || receipt.model_turn_started !== false
    || receipt.requested_workspace !== folder || !session || Array.isArray(session)
    || session.harness_type !== "codex" || session.status !== "idle"
    || typeof session.vendor_session_id !== "string" || !session.vendor_session_id
    || session.id !== `codex:${session.vendor_session_id}`
    || typeof session.cwd !== "string" || !session.cwd || metadata?.isolated !== true
    || metadata?.source !== "pex_ui") throw new Error("Worker creation was not confirmed.");
  return { id: session.id as string, cwd: session.cwd };
}

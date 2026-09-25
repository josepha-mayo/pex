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

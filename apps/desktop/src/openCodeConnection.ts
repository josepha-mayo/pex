import type { SharedRequest } from "./sharedConnection.ts";
import { BridgeRequestError } from "./decisionContract.ts";

/** Explain verified failures without reflecting arbitrary server diagnostics. */
export function openCodeConnectionFailure(error: unknown): string {
  if (error instanceof BridgeRequestError) {
    if (error.status === 401 || error.status === 403) {
      return "PEX could not authorize this connection request. Restart PEX to refresh its local bridge connection; do not paste your Zen key into the server address.";
    }
    if (error.status === 409) {
      return "The bridge rejected the connection because an active connection conflicts with this request. Inspect the worker list before changing connections. No new worker was started.";
    }
    if (error.status === 502) {
      return "The OpenCode health check did not pass. Check the local server and address, then retry. PEX discarded this connection attempt; it did not start a worker.";
    }
  }
  return "Connection was not confirmed. Check that your local OpenCode server is running and inspect the worker list before retrying. A lost response does not mean the connection was rolled back.";
}

export function openCodeOrigin(value: string): string | null {
  if (!value.trim() || value.length > 2048 || /[\s\\]/.test(value.trim())) return null;
  try {
    const url = new URL(value.trim());
    if (url.protocol !== "http:" || url.username || url.password || url.search || url.hash
      || url.pathname !== "/"
      || !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) return null;
    return url.origin;
  } catch { return null; }
}

/** One authenticated local-bridge request. Never send the operator key to OpenCode. */
export async function connectOpenCode(request: SharedRequest, value: string, signal: AbortSignal) {
  const url = openCodeOrigin(value);
  if (!url) throw new Error("Enter a local HTTP origin, such as http://127.0.0.1:4096.");
  const result = await request("/v1/adapters/opencode/attach", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }), signal,
  });
  if (!result || typeof result !== "object" || Array.isArray(result)
    || (result as Record<string, unknown>).ok !== true
    || (result as Record<string, unknown>).name !== "opencode") {
    throw new Error("Connection response was not confirmed. Check Inspector before retrying.");
  }
}

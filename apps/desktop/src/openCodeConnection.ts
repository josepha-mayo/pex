import type { SharedRequest } from "./sharedConnection.ts";
import { BridgeRequestError } from "./decisionContract.ts";

export const OPENCODE_ADDRESS_GUIDANCE = "Enter a local HTTP server address, such as http://127.0.0.1:4096, without a path, password or API key.";

class OpenCodeInputError extends Error {
  constructor(field: "address" | "credentials") {
    super(field === "address" ? OPENCODE_ADDRESS_GUIDANCE
      : "Check the OpenCode server username and password. No connection request was sent.");
  }
}

/** Explain verified failures without reflecting arbitrary server diagnostics. */
export function openCodeConnectionFailure(error: unknown): string {
  if (error instanceof OpenCodeInputError) return error.message;
  if (error instanceof BridgeRequestError) {
    if (error.status === 401 || error.status === 403) {
      return "PEX could not authorize this connection request. Restart PEX to refresh its local bridge connection; do not paste your Zen key into the server address.";
    }
    if (error.status === 409) {
      return "The bridge rejected the connection because an active connection conflicts with this request. Inspect the worker list before changing connections. No new worker was started.";
    }
    if (error.status === 502) {
      return "PEX could not verify OpenCode session access. Check the local server, address and server password, then retry. PEX discarded this connection attempt; it did not start a worker.";
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
export async function connectOpenCode(
  request: SharedRequest, value: string, signal: AbortSignal,
  credentials?: { username: string; password: string },
) {
  const url = openCodeOrigin(value);
  if (!url) throw new OpenCodeInputError("address");
  const auth = credentials?.password ? {
    username: credentials.username.trim() || "opencode", password: credentials.password,
  } : undefined;
  if (auth && (auth.username.length > 256 || /[^\x21-\x7e]/u.test(auth.username)
    || auth.password.length > 4096 || /[\r\n\0]/u.test(auth.password))) {
    throw new OpenCodeInputError("credentials");
  }
  const result = await request("/v1/adapters/opencode/attach", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, ...auth }), signal,
  });
  if (!result || typeof result !== "object" || Array.isArray(result)
    || (result as Record<string, unknown>).ok !== true
    || (result as Record<string, unknown>).name !== "opencode") {
    throw new Error("Connection response was not confirmed. Check Inspector before retrying.");
  }
}

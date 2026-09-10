import type { SharedRequest } from "./sharedConnection.ts";

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

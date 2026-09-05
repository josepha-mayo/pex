import { bridgeRequestError } from "./decisionContract.ts";

/** One authenticated attempt; a lost response never implies rollback or retries. */
export function createOperatorRequest({
  baseUrl,
  readToken,
  send = fetch,
}: {
  baseUrl: string;
  readToken: () => Promise<string | null>;
  send?: typeof fetch;
}): (path: string, init?: RequestInit) => Promise<unknown> {
  const origin = new URL(baseUrl).origin;
  return async (path, init) => {
    // The bearer belongs only to this bridge, never a supplied URL/redirect.
    const target = new URL(path, baseUrl);
    if (!path.startsWith("/v1/") || target.origin !== origin) {
      throw new Error("Invalid local operator route.");
    }
    const token = await readToken();
    const headers = new Headers(init?.headers);
    headers.delete("Authorization");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await send(target.href, {
      ...init, headers, redirect: "error", cache: "no-store",
    });
    if (!response.ok) {
      let payload: unknown = null;
      try { payload = await response.json(); } catch { /* Preserve HTTP status. */ }
      throw bridgeRequestError(response.status, response.statusText, payload);
    }
    return response.json();
  };
}

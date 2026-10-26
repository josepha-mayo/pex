/** Single-origin owner authentication only. No bridge/operator/provider authority. */
export type OwnerView = {
  phase: "checking" | "signed-out" | "signing-in" | "signed-in" | "locked" | "unavailable";
  message: string;
  expiresAt?: number;
};
type AuthReply = { authenticated: true; principal_id: "web-owner"; csrf_token: string; expires_in_seconds: number };
const TOKEN = /^[A-Za-z0-9_-]{43}$/;

export function createOwnerClient({ origin, send = fetch, changed, now = Date.now }: {
  origin: string; send?: typeof fetch; changed: (view: OwnerView) => void; now?: () => number;
}) {
  const base = new URL(origin);
  if (base.protocol !== "https:" || base.origin !== origin) throw new Error("HTTPS owner origin required");
  let generation = 0;
  let active: AbortController | null = null;
  let csrf: string | null = null;
  let view: OwnerView = { phase: "checking", message: "Checking your session…" };
  let disposed = false;
  const emit = (next: OwnerView) => { view = next; if (!disposed) changed({ ...next }); };
  const reset = () => { generation++; active?.abort(); active = null; csrf = null; return generation; };
  const current = (id: number) => !disposed && generation === id;
  async function request(path: string, method: string, body: string | undefined, token?: string) {
    const controller = new AbortController(); active = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const headers: Record<string, string> = {};
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (token) headers["X-PEX-Owner-CSRF"] = token;
      const response = await send(new URL(path, base).href, {
        method, headers, body, credentials: "same-origin", redirect: "error", cache: "no-store", signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 503) throw new Error("unconfigured");
        if (response.status === 429) throw new Error("limited");
        if (response.status === 401 || response.status === 403) throw new Error("denied");
        throw new Error("unavailable");
      }
      const reader = response.body?.getReader();
      if (!reader) throw new Error("invalid");
      let size = 0; const chunks: Uint8Array[] = [];
      try {
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          size += part.value.byteLength;
          if (size > 8192) { await reader.cancel(); throw new Error("invalid"); }
          chunks.push(part.value);
        }
      } finally { reader.releaseLock(); }
      const bytes = new Uint8Array(size); let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)) as unknown;
    } finally { clearTimeout(timeout); if (active === controller) active = null; }
  }
  function admit(value: unknown, id: number) {
    if (!current(id)) return;
    const data = value as Partial<AuthReply> | null;
    if (!data || data.authenticated !== true || data.principal_id !== "web-owner" ||
      typeof data.csrf_token !== "string" || !TOKEN.test(data.csrf_token) ||
      !Number.isInteger(data.expires_in_seconds) || data.expires_in_seconds! < 1 || data.expires_in_seconds! > 3600) {
      throw new Error("invalid");
    }
    csrf = data.csrf_token;
    emit({ phase: "signed-in", message: "Owner session verified.", expiresAt: now() + data.expires_in_seconds! * 1000 });
  }
  function failed(error: unknown, id: number) {
    if (!current(id)) return;
    csrf = null;
    const reason = error instanceof Error ? error.message : "unavailable";
    emit(reason === "unconfigured" ? { phase: "unavailable", message: "Owner access is not configured on this server. No agent or provider access has been enabled." }
      : reason === "denied" ? { phase: "signed-out", message: "Sign in again. Your session or owner secret was not accepted." }
      : reason === "limited" ? { phase: "signed-out", message: "Too many attempts. Wait a minute before trying again." }
      : { phase: "unavailable", message: "The owner service could not be verified. No action was retried." });
  }
  return {
    state: () => ({ ...view }),
    async check() {
      if (disposed) return;
      const id = reset(); emit({ phase: "checking", message: "Checking your session…" });
      try { admit(await request("/owner/auth/session", "GET", undefined), id); } catch (error) { failed(error, id); }
    },
    async login(secret: string) {
      if (disposed || view.phase === "signing-in" || view.phase === "checking" || view.phase === "signed-in") return;
      const id = reset();
      if (!TOKEN.test(secret)) { emit({ phase: "signed-out", message: "Enter the separately provisioned owner secret, not a provider API key." }); return; }
      emit({ phase: "signing-in", message: "Verifying owner access…" });
      try { admit(await request("/owner/auth/login", "POST", JSON.stringify({ owner_secret: secret })), id); }
      catch (error) { failed(error, id); }
    },
    async logout() {
      if (disposed || view.phase !== "signed-in" || !csrf) return;
      const token = csrf; const id = reset();
      emit({ phase: "locked", message: "This page is locked. Revoking the server session…" });
      try {
        const reply = await request("/owner/auth/logout", "POST", undefined, token) as { authenticated?: unknown };
        if (!reply || reply.authenticated !== false) throw new Error("invalid");
        if (current(id)) emit({ phase: "signed-out", message: "Signed out. Your server session was revoked." });
      } catch {
        if (current(id)) emit({ phase: "locked", message: "This page is locked, but server sign-out could not be confirmed. Close this page or check the session before trying again." });
      }
    },
    lock() { reset(); emit({ phase: "locked", message: "Session hidden. Verify again to continue." }); },
    dispose() { disposed = true; reset(); },
  };
}

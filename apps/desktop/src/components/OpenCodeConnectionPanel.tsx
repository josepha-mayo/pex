import { useEffect, useRef, useState } from "react";
import { connectOpenCode, openCodeOrigin } from "../openCodeConnection";
import type { SharedRequest } from "../sharedConnection";

export function OpenCodeConnectionPanel({ request }: { request: SharedRequest }) {
  const [url, setUrl] = useState("http://127.0.0.1:4096");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => {
    pending.current?.abort();
    pending.current = null;
  }, []);

  async function connect() {
    if (pending.current || !openCodeOrigin(url)) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setNotice("");
    const timer = setTimeout(() => controller.abort(), 12_000);
    try {
      await connectOpenCode(request, url, controller.signal);
      if (pending.current === controller) {
        setNotice("OpenCode connected. Return Home, select your worker, and set its persistent goal. This did not start a worker turn.");
      }
    } catch {
      if (pending.current === controller) {
        setNotice("Connection was not confirmed. Check that your local OpenCode server is running and inspect the worker list before retrying. A lost response does not mean the connection was rolled back.");
      }
    } finally {
      clearTimeout(timer);
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
      }
    }
  }

  return <section className="settings-card settings-wide">
    <p className="eyebrow">OpenCode</p>
    <h2>Connect your local OpenCode server</h2>
    <p className="settings-note">
      Start OpenCode with its HTTP server, then enter the local address below.
      PEX connects to existing sessions; it does not restart OpenCode or start a task.
      Your Zen key belongs in Supervisor settings, not this address.
    </p>
    <label>OpenCode server address
      <input type="url" value={url} maxLength={2048} disabled={busy}
        onChange={(event) => setUrl(event.target.value)} autoComplete="off"
        spellCheck={false} placeholder="http://127.0.0.1:4096" />
    </label>
    <p className="settings-note">
      This quick connection supports an unauthenticated loopback server only.
      Password-protected servers require the authenticated bridge API setup.
    </p>
    <button type="button" className="solid" disabled={busy || !openCodeOrigin(url)}
      onClick={() => void connect()}>{busy ? "Connecting…" : "Connect OpenCode"}</button>
    {notice ? <p role="status" aria-live="polite">{notice}</p> : null}
  </section>;
}

import { useEffect, useRef, useState } from "react";
import { connectOpenCode, openCodeConnectionFailure, openCodeOrigin } from "../openCodeConnection";
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
        setNotice("OpenCode server connected. If no worker appears, create or resume a session in the OpenCode terminal attached to this server. Then return Home, select your worker, and set its persistent goal. PEX did not start a worker turn.");
      }
    } catch (error) {
      if (pending.current === controller) {
        setNotice(openCodeConnectionFailure(error));
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
    <ol className="settings-note">
      <li>In your project terminal, run <code>opencode serve --port 4096</code>.</li>
      <li>In another terminal, run <code>opencode attach http://127.0.0.1:4096</code>.
        Create or resume your worker session there. Use the same server address below if you changed the port.</li>
      <li>Connect PEX, then return Home to select that worker and set its goal.</li>
    </ol>
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

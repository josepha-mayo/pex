import { useEffect, useRef, useState } from "react";
import { connectOpenCode, openCodeConnectionFailure, openCodeOrigin } from "../openCodeConnection";
import type { SharedRequest } from "../sharedConnection";

export function OpenCodeConnectionPanel({ request, onChanged }: {
  request: SharedRequest;
  onChanged?: () => void;
}) {
  const [url, setUrl] = useState("http://127.0.0.1:4096");
  const [username, setUsername] = useState("opencode");
  const [password, setPassword] = useState("");
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
      await connectOpenCode(request, url, controller.signal, { username, password });
      if (pending.current === controller) {
        setNotice("OpenCode server connected. If no worker appears, create or resume a session in the OpenCode terminal attached to this server. Then return Home, select your worker, and set its persistent goal. PEX did not start a worker turn.");
        onChanged?.();
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
        setPassword("");
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
    <details className="settings-advanced">
      <summary>Server password (optional)</summary>
      <p className="settings-note">Use your OpenCode server credentials, separate from your model API key.
        The password is held in memory for the connection and cleared from this form after each attempt.</p>
      <label>Server username
        <input value={username} maxLength={256} disabled={busy} autoComplete="off"
          onChange={(event) => setUsername(event.target.value)} spellCheck={false} />
      </label>
      <label>Server password
        <input type="password" value={password} maxLength={4096} disabled={busy} autoComplete="off"
          onChange={(event) => setPassword(event.target.value)} />
      </label>
    </details>
    <button type="button" className="solid" disabled={busy || !openCodeOrigin(url)}
      onClick={() => void connect()}>{busy ? "Connecting…" : "Connect OpenCode"}</button>
    {notice ? <p role="status" aria-live="polite">{notice}</p> : null}
  </section>;
}

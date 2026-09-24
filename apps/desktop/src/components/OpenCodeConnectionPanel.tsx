import { useEffect, useRef, useState } from "react";
import { connectOpenCode, openCodeConnectionFailure, openCodeOrigin } from "../openCodeConnection";
import type { SharedRequest } from "../sharedConnection";

export function OpenCodeConnectionPanel({ request, onChanged, available }: {
  request: SharedRequest;
  onChanged?: () => void;
  available: boolean;
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
    if (pending.current || !available || !openCodeOrigin(url)) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setNotice("");
    const timer = setTimeout(() => controller.abort(), 12_000);
    try {
      await connectOpenCode(request, url, controller.signal, { username, password });
      if (pending.current === controller) {
        setNotice("OpenCode server connected. Return Home to select a worker and set its goal. If none appears, create or resume a session in the attached OpenCode terminal. PEX did not start a worker turn.");
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
    <h2>Connect OpenCode</h2>
    <p className="settings-note">Enter the address of an OpenCode server running on this computer.</p>
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
    <button type="button" className="solid" disabled={busy || !available || !openCodeOrigin(url)}
      onClick={() => void connect()}>{busy ? "Connecting…" : "Connect OpenCode"}</button>
    {!available ? <p className="settings-note" role="status">PEX has not confirmed the local bridge. Open the PEX desktop app or retry its bridge before connecting a worker.</p> : null}
    {notice ? <p role="status" aria-live="polite">{notice}</p> : null}
    <details className="settings-advanced">
      <summary>How to start and attach OpenCode</summary>
      <ol className="settings-note">
        <li>In your project terminal, run <code>opencode serve --port 4096</code>.</li>
        <li>Use <code>opencode attach http://127.0.0.1:4096</code> in another terminal, or connect OpenCode Desktop to that same server. Create or resume a session there.</li>
        <li>Connect PEX, then select your worker and goal on Home.</li>
      </ol>
      <p className="settings-note">PEX connects to existing sessions; it does not start a task. Put model keys in Supervisor settings, not the server address.</p>
    </details>
  </section>;
}

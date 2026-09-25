import { useEffect, useRef, useState } from "react";
import { codexConnectionFailure, connectIsolatedCodex } from "../codexConnection";
import type { SharedRequest } from "../sharedConnection";

export function CodexConnectionPanel({ request, onChanged, available }: {
  request: SharedRequest;
  onChanged?: () => void;
  available: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => {
    pending.current?.abort();
    pending.current = null;
  }, []);

  async function connect() {
    if (pending.current || !available) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setNotice("");
    const timer = setTimeout(() => controller.abort(), 30_000);
    try {
      const support = await connectIsolatedCodex(request, controller.signal);
      if (pending.current === controller) {
        setNotice(`Codex App Server connected (${support}). Return Home to select an available CLI thread. No model turn was started.`);
        onChanged?.();
      }
    } catch (error) {
      if (pending.current === controller) setNotice(codexConnectionFailure(error));
    } finally {
      clearTimeout(timer);
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
      }
    }
  }

  return <section className="settings-card settings-wide">
    <p className="eyebrow">Codex CLI</p>
    <h2>Connect Codex CLI</h2>
    <p className="settings-note">
      PEX starts a separate local Codex App Server and verifies its handshake. This can supervise
      sessions in that isolated connection; it does not take control of your open Codex desktop task
      or start a model turn. The desktop-thread observer is below.
    </p>
    <button type="button" className="solid" disabled={busy || !available} onClick={() => void connect()}>
      {busy ? "Connecting…" : "Connect isolated Codex"}
    </button>
    {!available ? <p className="settings-note" role="status">PEX must confirm its local bridge before connecting Codex.</p> : null}
    {notice ? <p role="status" aria-live="polite">{notice}</p> : null}
  </section>;
}

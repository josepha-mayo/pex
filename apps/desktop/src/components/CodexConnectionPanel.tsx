import { useEffect, useRef, useState } from "react";
import { codexConnectionFailure, codexCreationFailure, connectIsolatedCodex, createCodexWorker } from "../codexConnection";
import type { SharedRequest } from "../sharedConnection";

export function CodexConnectionPanel({ request, onChanged, onReturnHome, available }: {
  request: SharedRequest;
  onChanged?: () => void;
  onReturnHome?: (sessionId?: string) => void;
  available: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [workspace, setWorkspace] = useState("");
  const [createdId, setCreatedId] = useState<string>();
  const [creating, setCreating] = useState(false);
  const [creationUncertain, setCreationUncertain] = useState(false);
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
    setConfirmed(false);
    const timer = setTimeout(() => controller.abort(), 30_000);
    try {
      const support = await connectIsolatedCodex(request, controller.signal);
      if (pending.current === controller) {
        setConfirmed(true);
        setNotice(`Codex App Server connected (${support}). Choose a project folder below to create an idle worker. No model turn was started.`);
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

  async function createWorker() {
    if (pending.current || !available || !workspace.trim() || creationUncertain || createdId) return;
    const controller = new AbortController();
    pending.current = controller;
    setCreating(true);
    setNotice("");
    const timer = setTimeout(() => controller.abort(), 40_000);
    try {
      const worker = await createCodexWorker(request, workspace, controller.signal);
      if (pending.current === controller) {
        setCreatedId(worker.id);
        setNotice(`Worker ready in ${worker.cwd}. Return Home to attach its goal. No task or model turn was started.`);
        onChanged?.();
      }
    } catch (error) {
      if (pending.current === controller) {
        const failure = codexCreationFailure(error);
        setCreationUncertain(failure.uncertain);
        setNotice(failure.message);
        onChanged?.();
      }
    } finally {
      clearTimeout(timer);
      if (pending.current === controller) { pending.current = null; setCreating(false); }
    }
  }

  return <section className="settings-card">
    <p className="eyebrow">Codex CLI</p>
    <h2>Connect Codex CLI</h2>
    <p className="settings-note">
      PEX starts a separate local Codex App Server and verifies its handshake. This can supervise
      sessions in that isolated connection; it does not take control of your open Codex desktop task
      or start a model turn. The desktop-thread observer is below.
    </p>
    <button type="button" className={confirmed || createdId ? "ghost" : "solid"}
      disabled={busy || creating || !available} onClick={() => void connect()}>
      {busy ? "Connecting…" : "Connect isolated Codex"}
    </button>
    <label className="field">
      Project folder
      <input value={workspace} onChange={(event) => setWorkspace(event.target.value)}
        placeholder="Absolute path to your local project" autoComplete="off" spellCheck={false} maxLength={4096}
        disabled={busy || creating || Boolean(createdId) || creationUncertain} />
    </label>
    <p className="settings-note">Create an empty worker in this folder, then attach a goal on Home. Creating it does not run a task or make a model call.</p>
    <button type="button" className={confirmed && !createdId ? "solid" : "ghost"}
      disabled={!available || busy || creating || !workspace.trim() || Boolean(createdId) || creationUncertain}
      onClick={() => void createWorker()}>{creating ? "Creating worker…" : "Create Codex worker"}</button>
    {!available ? <p className="settings-note" role="status">PEX must confirm its local bridge before connecting Codex.</p> : null}
    {notice ? <p role="status" aria-live="polite">{notice}</p> : null}
    {(confirmed || createdId || creationUncertain) && available && onReturnHome ? <button type="button" className={createdId || creationUncertain ? "solid" : "ghost"}
      onClick={() => onReturnHome(createdId)}>Return Home</button> : null}
  </section>;
}

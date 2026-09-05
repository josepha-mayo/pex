import { useCallback, useEffect, useId, useRef, useState } from "react";
import { correctionUpdate, parseCorrectionStatus, type CorrectionStatus } from "../autonomousCorrections";
import type { SharedRequest } from "../sharedConnection";

export function AutonomousCorrectionsPanel({ sessionId, request }: { sessionId: string; request: SharedRequest }) {
  const heading = useId();
  const [status, setStatus] = useState<CorrectionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const epoch = useRef(0);
  const pending = useRef(false);
  const path = `/v1/sessions/${encodeURIComponent(sessionId)}/autonomous-corrections`;

  const reload = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    const captured = epoch.current;
    setBusy(true);
    setStatus(null);
    setError(null);
    try {
      const next = parseCorrectionStatus(await request(path), sessionId);
      if (epoch.current === captured) setStatus(next);
    } catch {
      if (epoch.current === captured) setError("Correction permission could not be checked. Reload before changing it.");
    } finally {
      if (epoch.current === captured) { pending.current = false; setBusy(false); }
    }
  }, [path, request, sessionId]);

  useEffect(() => {
    epoch.current += 1;
    pending.current = false;
    void reload();
    return () => { epoch.current += 1; };
  }, [reload]);

  async function update(enabled: boolean) {
    if (pending.current || !status?.scope) return;
    pending.current = true;
    const captured = epoch.current;
    setBusy(true);
    setError(null);
    try {
      const body = correctionUpdate(status, enabled, crypto.randomUUID());
      await request(path, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (epoch.current !== captured) return;
      const canonical = parseCorrectionStatus(await request(path), sessionId);
      if (epoch.current === captured) setStatus(canonical);
    } catch {
      if (epoch.current === captured) {
        setStatus(null);
        setError("The change could not be confirmed. It was not retried. Reload permission status before another action.");
      }
    } finally {
      if (epoch.current === captured) { pending.current = false; setBusy(false); }
    }
  }

  return (
    <section aria-labelledby={heading}>
      <h3 id={heading}>Autonomous corrections</h3>
      <p className="settings-note">Give PEX standing permission to send grounded corrections and continue this existing thread for the displayed goal. This does not authorize approvals, new workers, settings changes or actions outside your local policy.</p>
      <p role="status" aria-live="polite">{busy ? "Checking correction permission…" : status ? `At last check: ${status.effective_enabled ? "enabled" : "disabled"}.` : "Permission not yet verified."}</p>
      {error ? <p role="alert">{error}</p> : null}
      {status?.scope ? (
        <dl>
          <dt>Selected thread</dt><dd><code>{status.scope.thread_id}</code></dd>
          <dt>Attached goal</dt><dd><code>{status.scope.goal_id}</code> · intent revision {status.scope.goal_intent_revision}</dd>
          <dt>Project</dt><dd><code>{status.scope.project_id}</code></dd>
          <dt>Workspace receipt hash</dt><dd><code>{status.scope.workspace_sha256}</code></dd>
          <dt>Connection incarnation</dt><dd>{status.scope.connection_generation} · <code>{status.scope.subscription_authorization_id}</code></dd>
        </dl>
      ) : !busy && status ? <p>Attach an active goal to this connected thread, then reload permission status.</p> : null}
      <button type="button" className="ghost" disabled={busy} onClick={() => void reload()}>Reload correction permission</button>
      {status?.enabled ? (
        <button type="button" className="ghost" disabled={busy || !status.scope} onClick={() => void update(false)}>Disable autonomous corrections</button>
      ) : (
        <button type="button" className="solid" disabled={busy || !status?.scope || !status.connected} onClick={() => void update(true)}>Enable autonomous corrections</button>
      )}
      <p className="settings-note">Pause, detach, reconnect, workspace changes or goal changes invalidate this permission. Resuming alone does not restore it. An enabled permission is not proof that a correction has been delivered.</p>
    </section>
  );
}

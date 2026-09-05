import { useEffect, useId, useMemo, useSyncExternalStore } from "react";
import {
  canConfirmConnection, canInspectConnection, createSharedConnectionController, validOrigin,
  type SharedRequest, type WorkspaceReview,
} from "../sharedConnection";

function WorkspaceReceipt({ receipt }: { receipt: WorkspaceReview }) {
  return (
    <details>
      <summary>Workspace identity receipt</summary>
      <dl>
        <dt>Local origin</dt><dd>{receipt.origin_choice.origin.namespace} / {receipt.origin_choice.origin.host}</dd>
        <dt>Origin revision</dt><dd>{receipt.origin_choice.revision}</dd>
        <dt>Origin choice ID</dt><dd><code>{receipt.origin_choice.choice_id}</code></dd>
        <dt>Measured folder</dt><dd><code>{receipt.directory.cwd}</code></dd>
        <dt>PEX project binding</dt><dd><code>{receipt.project_binding}</code></dd>
        <dt>Directory measurement</dt>
        <dd><code>{receipt.directory.platform} · {receipt.directory.physical.provider} · {receipt.directory.physical.volume_id} / {receipt.directory.physical.object_id}</code></dd>
      </dl>
      <p className="settings-note">This is a sampled directory identity and your explicit origin choice, not machine attestation or a filesystem lock.</p>
    </details>
  );
}

export function SharedConnectionPanel({ request, onChanged }: {
  request: SharedRequest;
  onChanged?: () => void;
}) {
  const controller = useMemo(() => createSharedConnectionController(request), [request]);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const headingId = useId();
  const origin = state.status?.origin;
  const connection = state.status?.connection;
  const selection = state.inspection;
  const blocked = !!state.busy || state.reloadRequired || !state.status;
  const saveBlocked = blocked || !!connection || !origin || origin.status === "unavailable"
    || !validOrigin(state.originDraft) || !state.confirmOrigin
    || (origin.status === "reconfirmation_required" && !state.allowStorageRebind);

  useEffect(() => {
    controller.activate();
    void controller.reload();
    return () => controller.deactivate();
  }, [controller]);

  useEffect(() => {
    if (!selection) return;
    const timer = setTimeout(() => controller.expireInspection(), Math.max(0, Math.ceil(selection.expiresAt - performance.now())) + 1);
    return () => clearTimeout(timer);
  }, [controller, selection]);

  async function changed(operation: Promise<boolean>, refresh = false) {
    if (!(await operation) || !controller.isActive()) return;
    // A known success may reconcile once with GET; an uncertain mutation never retries.
    if (refresh && !(await controller.reload())) return;
    if (controller.isActive()) onChanged?.();
  }

  return (
    <section className="settings-card settings-wide" aria-labelledby={headingId}>
      <p className="eyebrow">Existing worker connection</p>
      <h2 id={headingId}>Observe your existing Codex thread</h2>
      <p className="settings-note">
        Keep working in Codex. This connection observes selected lifecycle events only. It cannot send messages,
        continue work, answer approvals or change worker settings. No new worker or turn is started.
      </p>
      <div role="status" aria-live="polite">
        {state.busy ? <p>{state.busy === "reload" ? "Loading connection status…" : `${state.busy === "origin" ? "Saving origin" : state.busy === "inspect" ? "Inspecting existing thread" : state.busy === "confirm" ? "Connecting observer" : "Detaching observer"}…`}</p> : null}
        {state.notice ? <p>{state.notice}</p> : null}
      </div>
      {state.error ? <p role="alert">{state.error}</p> : null}
      {state.reloadRequired && !state.busy ? <p className="settings-note">Reload canonical status before another action. Reload does not repeat a save, inspect, subscription or detach.</p> : null}
      <button type="button" className="ghost" disabled={!!state.busy} onClick={() => void controller.reload()}>Reload connection status</button>

      {connection ? (
        <div role="group" aria-label="Codex connection at last refresh">
          <h3>{state.reloadRequired ? "Last known connection" : "Connection at last refresh"}: {connection.state === "observing" ? "Observing only" : connection.state === "disconnected" ? "Disconnected" : "Ownership changed"}</h3>
          <dl>
            <dt>Thread</dt><dd><code>{connection.thread_id}</code></dd>
            <dt>PEX session</dt><dd><code>{connection.session_id}</code></dd>
            <dt>PEX project</dt><dd><code>{connection.project_id}</code></dd>
            <dt>Working folder</dt><dd><code>{connection.cwd}</code></dd>
          </dl>
          <p className="settings-note">Coverage is limited to selected lifecycle notifications. Raw-stream completeness is not established; missed events may be unknown. A connected observer is not proof of autonomous supervision or successful worker delivery.</p>
          {typeof connection.observation_coverage?.reason === "string" ? <p>Coverage note: {connection.observation_coverage.reason}</p> : null}
          {connection.workspace_binding ? <WorkspaceReceipt receipt={connection.workspace_binding} /> : null}
          <button type="button" className="ghost" disabled={blocked || !connection.can_detach} onClick={() => void changed(controller.detach(), true)}>Detach PEX observer — leave worker running</button>
          {!connection.can_detach ? <p className="settings-note">This bridge no longer owns a detachable connection. Reload to reconcile ownership; do not reconnect blindly.</p> : null}
        </div>
      ) : state.status ? <p>No shared Codex observer connection is currently recorded by this bridge.</p> : null}

      <h3>1. Confirm this installation’s local origin</h3>
      <p className="settings-note">Choose the exact namespace and host label used by this machine’s registered project locators. PEX does not guess a hostname or register, merge or relabel projects here.</p>
      {origin?.choice ? (
        <div>
          <p>Saved origin: <code>{origin.choice.origin.namespace} / {origin.choice.origin.host}</code> · revision {origin.choice.revision}</p>
          <button type="button" className="ghost" disabled={!!state.busy} onClick={() => controller.useSavedOrigin()}>Use saved origin in form</button>
        </div>
      ) : null}
      {origin?.status === "unconfigured" ? <p>No origin choice has been saved yet.</p> : null}
      {origin?.status === "unavailable" ? <p role="alert">The saved origin cannot be verified. This is not first-run setup; existing data will not be overwritten. Check the local bridge configuration and reload.</p> : null}
      {origin?.status === "reconfirmation_required" ? <p role="alert">The saved origin belongs to a different installation directory. Review the saved choice and explicitly confirm rebinding it here.</p> : null}
      {connection ? <p className="settings-note">Detach the current observer before saving any origin change.</p> : null}
      <form onSubmit={(event) => { event.preventDefault(); void changed(controller.saveOrigin()); }}>
        <fieldset disabled={!!state.busy || !!connection || origin?.status === "unavailable"}>
          <legend>Local origin choice</legend>
          <div className="form-grid two-column">
            <label>Origin namespace<input value={state.originDraft.namespace} maxLength={256} autoComplete="off" spellCheck={false} onChange={(event) => controller.editOrigin("namespace", event.target.value)} placeholder="e.g. machine" /></label>
            <label>Origin host label<input value={state.originDraft.host} maxLength={512} autoComplete="off" spellCheck={false} onChange={(event) => controller.editOrigin("host", event.target.value)} placeholder="Exact operator-selected label" /></label>
          </div>
          <label className="checkbox-label"><input type="checkbox" checked={state.confirmOrigin} onChange={(event) => controller.setOriginConsent(event.target.checked)} />I confirm these exact labels identify this installation’s local workspace origin.</label>
          {origin?.status === "reconfirmation_required" ? <label className="checkbox-label"><input type="checkbox" checked={state.allowStorageRebind} onChange={(event) => controller.setRebindConsent(event.target.checked)} />I authorize rebinding this saved choice to the current installation directory.</label> : null}
          <p className="settings-note">Saving uses the displayed revision and exact saved choice ID. It invalidates all pending inspections.</p>
          <button type="submit" className="solid" disabled={saveBlocked}>Save explicit local origin</button>
        </fieldset>
      </form>

      <h3>2. Inspect the existing thread</h3>
      <p className="settings-note">Use an already-running, compatible local Codex App Server endpoint. This flow does not launch a replacement worker or discover endpoint details for you.</p>
      <form onSubmit={(event) => { event.preventDefault(); void controller.inspect(); }}>
        <fieldset disabled={!!state.busy || !!connection}>
          <legend>Exact connection target</legend>
          <div className="form-grid two-column">
            <label>Existing socket path<input value={state.draft.socket_path} maxLength={4096} autoComplete="off" spellCheck={false} onChange={(event) => controller.editDraft("socket_path", event.target.value)} /></label>
            <label>Existing thread ID<input value={state.draft.thread_id} maxLength={512} autoComplete="off" spellCheck={false} onChange={(event) => controller.editDraft("thread_id", event.target.value)} /></label>
            <label>PEX project ID<input value={state.draft.project_id} maxLength={512} autoComplete="off" spellCheck={false} onChange={(event) => controller.editDraft("project_id", event.target.value)} /></label>
            <label>Exact working folder<input value={state.draft.cwd} maxLength={4096} autoComplete="off" spellCheck={false} onChange={(event) => controller.editDraft("cwd", event.target.value)} /></label>
          </div>
          <p className="settings-note">Use an existing registered PEX project ID whose local locator matches this origin and folder. For a genuinely unregistered workspace, use its exact absolute folder path as the project ID.</p>
          <button type="submit" className="solid" disabled={!canInspectConnection(state)}>Inspect existing thread</button>
        </fieldset>
      </form>
      {state.status?.pending.length ? <p className="settings-note">{state.status.pending.length} pending inspection(s) known to this panel. Pending IDs alone cannot restore a reviewed selection. They expire within 60 seconds. At four pending inspections, wait for expiry and reload before inspecting again.</p> : null}

      {selection ? (
        <div role="group" aria-label="Review inspected Codex target">
          <h3>3. Review and explicitly connect</h3>
          <p>Not subscribed yet. This review expires within 60 seconds of inspection; changing any target field invalidates it.</p>
          <dl>
            <dt>Socket supplied</dt><dd><code>{selection.socket_path}</code></dd>
            <dt>Thread</dt><dd><code>{selection.thread_id}</code></dd>
            <dt>Root session</dt><dd><code>{selection.root_session_id}</code></dd>
            <dt>PEX session</dt><dd><code>{selection.session_id}</code></dd>
            <dt>PEX project</dt><dd><code>{selection.project_id}</code></dd>
            <dt>Vendor project</dt><dd>{selection.vendor_project_id ?? "Not supplied by Codex"}</dd>
            <dt>Requested folder</dt><dd><code>{state.draft.cwd}</code></dd>
            <dt>Codex working folder</dt><dd><code>{selection.cwd}</code></dd>
            <dt>Model</dt><dd>{selection.model ?? "Unknown"} · {selection.model_provider}</dd>
          </dl>
          <WorkspaceReceipt receipt={selection.workspace_binding} />
          <p className="settings-note">Clicking below authorizes the protocol’s thread subscription/resume step for this exact reviewed selection only. It does not start a turn, send a prompt or enable worker control.</p>
          <button type="button" className="solid" disabled={!canConfirmConnection(state)} onClick={() => void changed(controller.confirm(), true)}>Confirm this exact thread — connect observer</button>
        </div>
      ) : null}
    </section>
  );
}

/** Browser-only UI fixture. Not a worker, backend integration or release demo.
 * Open /tests/connection-qa.html through Vite. No fetch, native API or credential.
 * This file is not an input to the normal production build.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SharedConnectionPanel } from "../src/components/SharedConnectionPanel";
import "../src/styles.css";

const physical = { provider: "pex-os-stat-windows-v1", volume_id: "12", object_id: "34" };
const inspectionId = "1234567890ab4def81234567890abcde";
const selectionId = "a".repeat(64);
let revision = 0;
let origin: any = { status: "unconfigured", choice: null };
let connection: any = null;
let selection: any = null;
let expiresAt = 0;
const fixture = {
  calls: [] as { path: string; method: string; body: unknown }[],
  loseNextMutationResponse: false,
  rejectStatus: false,
  disconnect() { if (connection) connection.state = "disconnected"; },
};
Object.assign(window, { connectionFixture: fixture });

function check(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(`Fixture rejected request: ${message}`);
}
function checkPair(body: any) {
  check(body.inspection_id === inspectionId && body.selection_id === selectionId, "exact pair required");
}
async function request(path: string, init?: RequestInit): Promise<unknown> {
  const method = init?.method ?? "GET";
  const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
  fixture.calls.push({ path, method, body });
  let result: unknown;
  if (path === "/v1/adapters/codex/shared/status" && method === "GET") {
    if (fixture.rejectStatus) throw new Error("Fixture: operator status unavailable");
    result = { origin, connection, pending: selection && !connection ? [{
      inspection_id: inspectionId, selection_id: selectionId, session_id: selection.session_id,
      expires_in_seconds: Math.max(0, (expiresAt - performance.now()) / 1000),
      can_confirm: expiresAt > performance.now(),
    }] : [], worker_delivery_enabled: false };
  } else if (path === "/v1/local-workspace-origin" && method === "PATCH") {
    check(!connection, "detach first");
    check(body.confirm_local_origin === true && body.allow_storage_rebind === false, "explicit origin consent");
    check(body.expected_revision === (origin.choice?.revision ?? null), "current revision");
    check(body.expected_choice_id === (origin.choice?.choice_id ?? null), "current choice ID");
    check(body.origin.namespace && body.origin.host, "explicit namespace and host");
    origin = { status: "configured", choice: {
      schema: "pex.local-origin-choice.v1", revision: ++revision,
      choice_id: revision.toString(16).padStart(12, "0") + "4def81234567890abcde",
      origin: body.origin, storage_physical: physical,
    } };
    selection = null;
    result = { ...origin, invalidated_selections: 0 };
  } else if (path === "/v1/adapters/codex/shared/inspect" && method === "POST") {
    check(origin.status === "configured" && !connection, "configured and detached");
    check(body.socket_path && body.thread_id && body.project_id && body.cwd, "complete target");
    expiresAt = performance.now() + 60_000;
    selection = {
      inspection_id: inspectionId, selection_id: selectionId,
      session_id: `codex:${body.thread_id}`, thread_id: body.thread_id,
      root_session_id: "fixture-root", project_id: body.project_id,
      vendor_project_id: "vendor-project-not-pex-project", cwd: body.cwd,
      model: "fixture-model", model_provider: "fixture-provider", expires_in_seconds: 60,
      subscribed: false,
      workspace_binding: {
        schema_version: "pex.local-workspace-binding.v1", project_id: body.project_id,
        project_binding: `legacy:${body.project_id}`, origin_choice: origin.choice,
        directory: { cwd: body.cwd, platform: "windows", physical }, locator: null,
      },
      note: "Fixture inspection only. No worker exists.",
    };
    result = selection;
  } else if (path === "/v1/adapters/codex/shared/confirm" && method === "POST") {
    checkPair(body);
    check(selection && expiresAt > performance.now() && body.allow_resume === true, "fresh explicit subscription consent");
    connection = { ...selection, state: "observing", can_detach: true,
      observation_coverage: { history_complete: false }, worker_delivery_enabled: false };
    result = { ok: true, kind: "shared", support: "observe_only", session_id: selection.session_id,
      subscription: {
        schema: "pex.codex-existing-thread-subscription.v1", authorization_id: inspectionId,
        selection_id: selectionId, endpoint_identity: "fixture-endpoint", connection_generation: 1,
        pex_session_id: selection.session_id, thread_id: selection.thread_id,
        root_session_id: selection.root_session_id, project_id: selection.project_id,
        vendor_project_id: selection.vendor_project_id, cwd: selection.cwd, history_mode: "includeTurns",
        history_identity_digest: "b".repeat(64), history_record_count: 1,
        reconciliation_live_watermark: 0, observation_only: true, delivery_proven: false,
      },
      worker_delivery_enabled: false, workspace_binding: selection.workspace_binding };
    selection = null;
  } else if (path === "/v1/adapters/codex/shared/detach" && method === "POST") {
    checkPair(body);
    check(connection, "active attachment");
    connection = null;
    result = { ok: true, detached: true, worker_stopped: false, replayed: false };
  } else {
    throw new Error(`Fixture route not implemented: ${method} ${path}`);
  }
  if (method !== "GET" && fixture.loseNextMutationResponse) {
    fixture.loseNextMutationResponse = false;
    throw new Error("Fixture: operation happened but its response was lost. Reload status.");
  }
  return structuredClone(result);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <main className="main-shell settings-shell">
      <header className="surface-heading"><h1>TEST FIXTURE — no worker connected</h1></header>
      <p>Real connection component, fake in-memory API. This is UI verification only, not live PEX supervision.</p>
      <div className="settings-grid"><SharedConnectionPanel request={request} /></div>
    </main>
  </StrictMode>,
);

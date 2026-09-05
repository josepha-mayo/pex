/** Explicit operator connection flow. No worker control or mutation retry. */
export type SharedRequest = (path: string, init?: RequestInit) => Promise<unknown>;
type JsonObject = Record<string, unknown>;
export type OriginChoice = {
  schema: "pex.local-origin-choice.v1";
  revision: number;
  choice_id: string;
  origin: { namespace: string; host: string };
};
export type OriginStatus = {
  status: "unconfigured" | "configured" | "reconfirmation_required" | "unavailable";
  choice: OriginChoice | null;
};
export type WorkspaceReview = {
  project_id: string;
  project_binding: string;
  origin_choice: OriginChoice;
  directory: { cwd: string; platform: string; physical: { provider: string; volume_id: string; object_id: string } };
};
export type SelectionPair = { inspection_id: string; selection_id: string };
export type Connection = SelectionPair & {
  state: "observing" | "disconnected" | "ownership_changed";
  can_detach: boolean;
  session_id: string;
  thread_id: string;
  project_id: string;
  cwd: string;
  workspace_binding: WorkspaceReview | null;
  observation_coverage: JsonObject | null;
};
export type SharedStatus = {
  origin: OriginStatus;
  connection: Connection | null;
  pending: (SelectionPair & { session_id: string; expires_in_seconds: number; can_confirm: boolean })[];
};
export type ConnectionDraft = { socket_path: string; thread_id: string; project_id: string; cwd: string };
export type Inspection = SelectionPair & {
  session_id: string;
  thread_id: string;
  root_session_id: string;
  project_id: string;
  vendor_project_id: string | null;
  cwd: string;
  model: string | null;
  model_provider: string;
  workspace_binding: WorkspaceReview;
  workspaceReceiptJson: string;
  expiresAt: number;
  socket_path: string;
};
export type SharedConnectionState = {
  status: SharedStatus | null;
  originDraft: { namespace: string; host: string };
  confirmOrigin: boolean;
  allowStorageRebind: boolean;
  draft: ConnectionDraft;
  inspection: Inspection | null;
  busy: "reload" | "origin" | "inspect" | "confirm" | "detach" | null;
  reloadRequired: boolean;
  error: string | null;
  notice: string | null;
};

function object(value: unknown): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("Malformed bridge response.");
  return value as JsonObject;
}
function string(value: unknown, max = 4096): string {
  if (typeof value !== "string" || !value.length || value.length > max || value.includes("\0")) throw new Error("Malformed bridge response.");
  return value;
}
function bool(value: unknown): boolean {
  if (typeof value !== "boolean") throw new Error("Malformed bridge response.");
  return value;
}
function seconds(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 60) throw new Error("Malformed selection lifetime.");
  return value;
}
function pair(value: JsonObject): SelectionPair {
  if (typeof value.inspection_id !== "string" || !/^[a-f0-9]{32}$/.test(value.inspection_id)
    || typeof value.selection_id !== "string" || !/^[a-f0-9]{64}$/.test(value.selection_id)) throw new Error("Malformed selection identity.");
  return { inspection_id: value.inspection_id, selection_id: value.selection_id };
}
function originChoice(value: unknown): OriginChoice {
  const item = object(value);
  const origin = object(item.origin);
  if (item.schema !== "pex.local-origin-choice.v1" || !Number.isSafeInteger(item.revision) || (item.revision as number) < 1
    || typeof item.choice_id !== "string" || !/^[a-f0-9]{32}$/.test(item.choice_id)) throw new Error("Unsupported local-origin revision or identity.");
  const namespace = string(origin.namespace, 256);
  const host = string(origin.host, 512);
  if (!validOrigin({ namespace, host })) throw new Error("Malformed local origin.");
  return { schema: item.schema, revision: item.revision as number, choice_id: item.choice_id, origin: { namespace, host } };
}
function originStatus(value: unknown): OriginStatus {
  const item = object(value);
  if (item.status === "unconfigured" || item.status === "unavailable") {
    if (item.choice !== null) throw new Error("Malformed local-origin state.");
    return { status: item.status, choice: null };
  }
  if (item.status !== "configured" && item.status !== "reconfirmation_required") throw new Error("Unknown local-origin state.");
  return { status: item.status, choice: originChoice(item.choice) };
}
function workspace(value: unknown): WorkspaceReview {
  const item = object(value);
  const directory = object(item.directory);
  const physical = object(directory.physical);
  if (item.schema_version !== "pex.local-workspace-binding.v1") throw new Error("Unsupported workspace receipt.");
  return {
    project_id: string(item.project_id), project_binding: string(item.project_binding), origin_choice: originChoice(item.origin_choice),
    directory: { cwd: string(directory.cwd), platform: string(directory.platform), physical: {
      provider: string(physical.provider), volume_id: string(physical.volume_id), object_id: string(physical.object_id),
    } },
  };
}
function observeOnly(item: JsonObject): void {
  if (item.worker_delivery_enabled !== false) throw new Error("Unsupported worker-control response. Reload required.");
}
export function parseSharedStatus(value: unknown): SharedStatus {
  const item = object(value);
  observeOnly(item);
  let connection: Connection | null = null;
  if (item.connection !== null) {
    const current = object(item.connection);
    observeOnly(current);
    if (current.state !== "observing" && current.state !== "disconnected" && current.state !== "ownership_changed") throw new Error("Unknown connection state.");
    connection = { ...pair(current), state: current.state, can_detach: bool(current.can_detach),
      session_id: string(current.session_id), thread_id: string(current.thread_id), project_id: string(current.project_id), cwd: string(current.cwd),
      workspace_binding: current.workspace_binding === null ? null : workspace(current.workspace_binding),
      observation_coverage: current.observation_coverage === null ? null : { ...object(current.observation_coverage) },
    };
  }
  if (!Array.isArray(item.pending) || item.pending.length > 4) throw new Error("Malformed pending selections.");
  return { origin: originStatus(item.origin), connection, pending: item.pending.map((raw) => {
    const entry = object(raw);
    return { ...pair(entry), session_id: string(entry.session_id), expires_in_seconds: seconds(entry.expires_in_seconds), can_confirm: bool(entry.can_confirm) };
  }) };
}
export function validOrigin(origin: { namespace: string; host: string }): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(origin.namespace)
    && origin.host.length > 0 && origin.host.length <= 512 && origin.host.trim() === origin.host && !origin.host.includes("\0");
}
export function validConnectionDraft(draft: ConnectionDraft): boolean {
  return Object.entries(draft).every(([key, value]) => value.trim().length > 0 && !value.includes("\0")
    && value.length <= (key === "thread_id" || key === "project_id" ? 512 : 4096));
}
function sameOrigin(left: OriginChoice, right: OriginChoice): boolean {
  return left.revision === right.revision && left.choice_id === right.choice_id
    && left.origin.namespace === right.origin.namespace && left.origin.host === right.origin.host;
}
function canonicalJson(value: unknown): string {
  function sorted(item: unknown): unknown {
    if (Array.isArray(item)) return item.map(sorted);
    if (item !== null && typeof item === "object") {
      return Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right)).map(([key, entry]) => [key, sorted(entry)]));
    }
    return item;
  }
  return JSON.stringify(sorted(value));
}
function requireConfirmation(value: unknown, selected: Inspection): void {
  const receipt = object(value);
  const subscription = object(receipt.subscription);
  observeOnly(receipt);
  if (receipt.ok !== true || receipt.kind !== "shared" || receipt.support !== "observe_only" || receipt.session_id !== selected.session_id
    || subscription.schema !== "pex.codex-existing-thread-subscription.v1" || subscription.observation_only !== true || subscription.delivery_proven !== false
    || subscription.authorization_id !== selected.inspection_id || subscription.selection_id !== selected.selection_id
    || subscription.pex_session_id !== selected.session_id || subscription.thread_id !== selected.thread_id
    || subscription.root_session_id !== selected.root_session_id || subscription.project_id !== selected.project_id
    || subscription.vendor_project_id !== selected.vendor_project_id || subscription.cwd !== selected.cwd || subscription.history_mode !== "includeTurns"
    || canonicalJson(receipt.workspace_binding) !== selected.workspaceReceiptJson) throw new Error("Connection receipt differs from the exact reviewed selection.");
  string(subscription.endpoint_identity);
  if (typeof subscription.history_identity_digest !== "string" || !/^[a-f0-9]{64}$/.test(subscription.history_identity_digest)) throw new Error("Malformed subscription history identity.");
  for (const [key, minimum] of [["connection_generation", 1], ["history_record_count", 0], ["reconciliation_live_watermark", 0]] as const) {
    if (!Number.isSafeInteger(subscription[key]) || (subscription[key] as number) < minimum) throw new Error("Unsupported subscription counter.");
  }
}
export function canConfirmConnection(state: SharedConnectionState, now = performance.now()): boolean {
  return !state.busy && !state.reloadRequired && state.status?.origin.status === "configured"
    && !state.status.connection && !!state.inspection && state.inspection.expiresAt > now
    && sameOrigin(state.inspection.workspace_binding.origin_choice, state.status.origin.choice!);
}
export function canInspectConnection(state: SharedConnectionState): boolean {
  return !state.busy && !state.reloadRequired && state.status?.origin.status === "configured"
    && !state.status.connection && state.status.pending.length < 4 && validConnectionDraft(state.draft);
}

export function createSharedConnectionController(request: SharedRequest, options: {
  now?: () => number; timeoutMs?: number;
} = {}) {
  const now = options.now ?? (() => performance.now());
  const timeoutMs = options.timeoutMs ?? 75_000;
  const listeners = new Set<() => void>();
  let state: SharedConnectionState = {
    status: null, originDraft: { namespace: "", host: "" }, confirmOrigin: false, allowStorageRebind: false,
    draft: { socket_path: "", thread_id: "", project_id: "", cwd: "" }, inspection: null,
    busy: null, reloadRequired: false, error: null, notice: null,
  };
  let active = false;
  let generation = 0;
  let draftRevision = 0;
  let abort: AbortController | null = null;
  const update = (patch: Partial<SharedConnectionState>) => {
    state = { ...state, ...patch };
    listeners.forEach((listener) => listener());
  };
  const ready = () => active && !state.busy && !state.reloadRequired && state.status !== null;
  async function attempt(kind: NonNullable<SharedConnectionState["busy"]>, path: string, body?: unknown,
    accept: (value: unknown, started: number) => Partial<SharedConnectionState> = () => ({})) {
    if (!active || state.busy || (kind !== "reload" && !ready())) return false;
    const token = ++generation;
    const started = now();
    const cancellation = new AbortController();
    abort = cancellation;
    update({ busy: kind, error: null, ...(kind === "reload" ? { inspection: null, confirmOrigin: false, allowStorageRebind: false } : {}) });
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const aborted = new Promise<never>((_, reject) => {
        cancellation.signal.addEventListener("abort", () => reject(new Error("Request ended before a confirmed response.")), { once: true });
        timer = setTimeout(() => cancellation.abort(), timeoutMs);
      });
      const value = await Promise.race([request(path, {
        method: kind === "reload" ? "GET" : kind === "origin" ? "PATCH" : "POST", signal: cancellation.signal,
        ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
      }), aborted]);
      if (!active || token !== generation) return false;
      update({ ...accept(value, started), busy: null });
      return true;
    } catch (error) {
      if (active && token === generation) update({ busy: null, inspection: null, reloadRequired: true,
        confirmOrigin: false, allowStorageRebind: false,
        error: `${error instanceof Error ? error.message : "Bridge request failed."} ${kind === "reload"
          ? "Status is unavailable. Check the authenticated bridge, then reload."
          : "The server may have changed state. Reload status before another action; this request will not be retried."}`,
      });
      return false;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      if (abort === cancellation) abort = null;
    }
  }
  return {
    isActive: () => active,
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    activate() { active = true; generation++; update({ busy: null, inspection: null, reloadRequired: true }); },
    deactivate() { active = false; generation++; abort?.abort(); abort = null; },
    editOrigin(field: "namespace" | "host", value: string) {
      draftRevision++;
      update({ originDraft: { ...state.originDraft, [field]: value }, confirmOrigin: false, allowStorageRebind: false, inspection: null });
    },
    useSavedOrigin() {
      if (state.status?.origin.choice) {
        draftRevision++;
        update({ originDraft: { ...state.status.origin.choice.origin }, confirmOrigin: false, allowStorageRebind: false, inspection: null });
      }
    },
    setOriginConsent(value: boolean) { update({ confirmOrigin: value }); },
    setRebindConsent(value: boolean) { update({ allowStorageRebind: value }); },
    editDraft(field: keyof ConnectionDraft, value: string) {
      draftRevision++;
      update({ draft: { ...state.draft, [field]: value }, inspection: null });
    },
    expireInspection() {
      if (state.inspection && state.inspection.expiresAt <= now() && state.busy !== "confirm") {
        update({ inspection: null, notice: "Inspection expired. Inspect again before connecting." });
      }
    },
    reload() {
      return attempt("reload", "/v1/adapters/codex/shared/status", undefined, (value) => ({
        status: parseSharedStatus(value), reloadRequired: false, notice: "Status reloaded. Unsaved fields are unchanged.",
      }));
    },
    saveOrigin() {
      const origin = state.status?.origin;
      if (!ready() || !origin || origin.status === "unavailable" || state.status?.connection
        || !validOrigin(state.originDraft) || !state.confirmOrigin
        || (origin.status === "reconfirmation_required" && !state.allowStorageRebind)) return Promise.resolve(false);
      const selected = { ...state.originDraft };
      const previous = origin.choice;
      const revision = draftRevision;
      update({ inspection: null });
      return attempt("origin", "/v1/local-workspace-origin", {
        origin: selected, expected_revision: previous?.revision ?? null, expected_choice_id: previous?.choice_id ?? null,
        confirm_local_origin: true, allow_storage_rebind: origin.status === "reconfirmation_required" && state.allowStorageRebind,
      }, (value) => {
        const saved = originStatus(value);
        if (saved.status !== "configured" || !saved.choice || saved.choice.origin.namespace !== selected.namespace
          || saved.choice.origin.host !== selected.host || saved.choice.revision !== (previous?.revision ?? 0) + 1
          || saved.choice.choice_id === previous?.choice_id) throw new Error("Origin receipt does not match this save.");
        return { status: { ...state.status!, origin: saved, pending: [] }, confirmOrigin: false, allowStorageRebind: false,
          notice: revision === draftRevision ? "Local origin saved. Inspect your existing Codex thread next." : "Origin saved for the submitted values; your newer draft remains unsaved." };
      });
    },
    inspect() {
      if (!ready() || !canInspectConnection(state)) return Promise.resolve(false);
      const draft = { ...state.draft };
      const revision = draftRevision;
      const origin = state.status!.origin.choice!;
      update({ inspection: null });
      return attempt("inspect", "/v1/adapters/codex/shared/inspect", draft, (value, started) => {
        const item = object(value);
        const receipt = workspace(item.workspace_binding);
        const selection: Inspection = { ...pair(item), session_id: string(item.session_id), thread_id: string(item.thread_id),
          root_session_id: string(item.root_session_id), project_id: string(item.project_id), vendor_project_id: item.vendor_project_id === null ? null : string(item.vendor_project_id),
          cwd: string(item.cwd), model: item.model === null ? null : string(item.model), model_provider: string(item.model_provider), workspace_binding: receipt,
          workspaceReceiptJson: canonicalJson(item.workspace_binding),
          expiresAt: started + seconds(item.expires_in_seconds) * 1000, socket_path: draft.socket_path };
        if (item.subscribed !== false || selection.thread_id !== draft.thread_id || selection.project_id !== draft.project_id
          || receipt.project_id !== selection.project_id || !sameOrigin(receipt.origin_choice, origin)) throw new Error("Inspection identity differs from the selected thread, project or origin.");
        // CWD may be a canonical spelling/alias; show both for explicit human review.
        const status = { ...state.status!, pending: [...state.status!.pending, {
          inspection_id: selection.inspection_id, selection_id: selection.selection_id, session_id: selection.session_id,
          expires_in_seconds: seconds(item.expires_in_seconds), can_confirm: true,
        }] };
        return revision === draftRevision && selection.expiresAt > now()
          ? { status, inspection: selection, notice: "Inspection only. Review the exact thread and workspace before connecting." }
          : { status, inspection: null, notice: "Selection changed or expired while inspecting. Inspect again; no subscription was requested." };
      });
    },
    confirm() {
      if (!active || !canConfirmConnection(state, now())) return Promise.resolve(false);
      const selected = state.inspection!;
      return attempt("confirm", "/v1/adapters/codex/shared/confirm", {
        inspection_id: selected.inspection_id, selection_id: selected.selection_id, allow_resume: true,
      }, (value) => {
        requireConfirmation(value, selected);
        return { inspection: null, reloadRequired: true, notice: "Observer subscription confirmed. Reload status to view or detach the current connection." };
      });
    },
    detach() {
      const connection = state.status?.connection;
      if (!ready() || !connection?.can_detach) return Promise.resolve(false);
      return attempt("detach", "/v1/adapters/codex/shared/detach", {
        inspection_id: connection.inspection_id, selection_id: connection.selection_id,
      }, (value) => {
        const receipt = object(value);
        if (receipt.ok !== true || receipt.detached !== true || receipt.worker_stopped !== false || typeof receipt.replayed !== "boolean") throw new Error("Unexpected detach receipt.");
        return { inspection: null, reloadRequired: true, notice: "PEX observer detached; the worker was not stopped. Reload to reconcile current status." };
      });
    },
  };
}

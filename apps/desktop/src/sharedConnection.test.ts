import assert from "node:assert/strict";
import test from "node:test";
import {
  canConfirmConnection, canInspectConnection, createSharedConnectionController, parseSharedStatus,
  validOrigin, type SharedRequest,
} from "./sharedConnection.ts";

const origin = { namespace: "machine", host: "Explicit-Fixture-Host" };
const choice = { schema: "pex.local-origin-choice.v1", revision: 7, choice_id: "11111111111141118111111111111111", origin,
  storage_physical: { provider: "pex-os-stat-windows-v1", volume_id: "123", object_id: "456" } };
const binding = { schema_version: "pex.local-workspace-binding.v1", project_id: "project-fixture", project_binding: "identity:immutable-fixture",
  origin_choice: choice, directory: { cwd: "C:\\fixture\\workspace", platform: "windows", physical: choice.storage_physical }, locator: null };
const selected = { inspection_id: "a".repeat(32), selection_id: "b".repeat(64), session_id: "codex:thread-fixture", thread_id: "thread-fixture",
  root_session_id: "root-fixture", project_id: "project-fixture", vendor_project_id: null,
  cwd: "C:\\fixture\\workspace", model: null, model_provider: "fixture-provider", expires_in_seconds: 60, subscribed: false, workspace_binding: binding };
const connection = { ...selected, state: "observing", can_detach: true, worker_delivery_enabled: false,
  observation_coverage: { schema: "pex.codex-observation-coverage.v1", raw_stream_complete: false, unobserved_event_count: null } };
const canonical = { origin: { status: "configured", choice }, connection: null, pending: [], worker_delivery_enabled: false };
const subscription = { schema: "pex.codex-existing-thread-subscription.v1", authorization_id: selected.inspection_id, selection_id: selected.selection_id,
  endpoint_identity: "fixture-endpoint-identity", connection_generation: 1, pex_session_id: selected.session_id, thread_id: selected.thread_id,
  root_session_id: selected.root_session_id, project_id: selected.project_id, vendor_project_id: null, cwd: selected.cwd, history_mode: "includeTurns",
  history_identity_digest: "e".repeat(64), history_record_count: 0, reconciliation_live_watermark: 0, observation_only: true, delivery_proven: false };
const confirmed = { ok: true, kind: "shared", support: "observe_only", session_id: selected.session_id, subscription, workspace_binding: binding, worker_delivery_enabled: false };
const detached = { ok: true, detached: true, worker_stopped: false, replayed: false };
function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness(initial: unknown = canonical, options: { now?: () => number; timeoutMs?: number } = {}) {
  const calls: { path: string; init?: RequestInit }[] = [];
  let status = initial;
  let response: unknown = selected;
  let handler: SharedRequest | null = null;
  const controller = createSharedConnectionController(async (path, init) => {
    calls.push({ path, init });
    if (handler) return handler(path, init);
    return path.endsWith("/status") ? status : response;
  }, options);
  controller.activate();
  return { controller, calls, setStatus(value: unknown) { status = value; }, setResponse(value: unknown) { response = value; }, setHandler(value: SharedRequest | null) { handler = value; } };
}
function fill(controller: ReturnType<typeof createSharedConnectionController>) {
  controller.editDraft("socket_path", "C:\\fixture\\existing.sock");
  controller.editDraft("thread_id", selected.thread_id);
  controller.editDraft("project_id", selected.project_id);
  controller.editDraft("cwd", selected.cwd);
}
function body(call: { init?: RequestInit }) { return JSON.parse(String(call.init?.body)); }

test("canonical reload is one GET and cannot confirm pending IDs without a full inspection", async () => {
  const h = harness({ ...canonical, pending: [{ ...selected, can_confirm: true }] });
  assert.equal(await h.controller.reload(), true);
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].init?.method, "GET");
  assert.equal(h.calls[0].init?.body, undefined);
  assert.equal(h.controller.getSnapshot().inspection, null);
  assert.equal(await h.controller.confirm(), false);
  assert.equal(h.calls.length, 1);
});

test("valid nullable vendor project/model inspect sends no resume; explicit confirm sends only the exact pair", async () => {
  const h = harness();
  await h.controller.reload(); fill(h.controller);
  assert.equal(await h.controller.inspect(), true);
  assert.equal(h.controller.getSnapshot().inspection?.model, null);
  assert.equal(h.controller.getSnapshot().inspection?.vendor_project_id, null);
  assert.deepEqual(body(h.calls[1]), h.controller.getSnapshot().draft);
  assert.equal("allow_resume" in body(h.calls[1]), false);
  assert.equal(canConfirmConnection(h.controller.getSnapshot()), true);
  h.setResponse(confirmed);
  assert.equal(await h.controller.confirm(), true);
  assert.deepEqual(body(h.calls[2]), { inspection_id: selected.inspection_id, selection_id: selected.selection_id, allow_resume: true });
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
  assert.equal(await h.controller.confirm(), false);
  assert.equal(h.calls.length, 3);
});

test("canonical folder alias is shown separately instead of rejected or overwriting the typed path", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller);
  h.controller.editDraft("cwd", "C:\\fixture\\alias");
  assert.equal(await h.controller.inspect(), true);
  assert.equal(h.controller.getSnapshot().draft.cwd, "C:\\fixture\\alias");
  assert.equal(h.controller.getSnapshot().inspection?.cwd, selected.cwd);
});

test("first origin save requires explicit labels and consent and sends both null CAS fields", async () => {
  const h = harness({ ...canonical, origin: { status: "unconfigured", choice: null } });
  await h.controller.reload();
  h.controller.setOriginConsent(true);
  assert.equal(await h.controller.saveOrigin(), false);
  h.controller.editOrigin("namespace", origin.namespace); h.controller.editOrigin("host", origin.host);
  assert.equal(h.controller.getSnapshot().confirmOrigin, false);
  assert.equal(await h.controller.saveOrigin(), false);
  h.controller.setOriginConsent(true);
  h.setResponse({ status: "configured", choice: { ...choice, revision: 1 }, invalidated_selections: 0 });
  assert.equal(await h.controller.saveOrigin(), true);
  assert.deepEqual(body(h.calls[1]), { origin, expected_revision: null, expected_choice_id: null, confirm_local_origin: true, allow_storage_rebind: false });
  assert.equal(h.controller.getSnapshot().confirmOrigin, false);
});

test("configured save uses exact revision/choice, invalidates inspections and resets consent", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
  h.controller.useSavedOrigin(); h.controller.setOriginConsent(true);
  h.setResponse({ status: "configured", choice: { ...choice, revision: 8, choice_id: "22222222222242228222222222222222" }, invalidated_selections: 1 });
  assert.equal(await h.controller.saveOrigin(), true);
  assert.deepEqual(body(h.calls[2]), { origin, expected_revision: 7, expected_choice_id: choice.choice_id, confirm_local_origin: true, allow_storage_rebind: false });
  assert.equal(h.controller.getSnapshot().inspection, null);
  assert.deepEqual(h.controller.getSnapshot().status?.pending, []);
});

test("storage rebinding requires separate fresh explicit consent", async () => {
  const h = harness({ ...canonical, origin: { status: "reconfirmation_required", choice } });
  await h.controller.reload(); h.controller.useSavedOrigin(); h.controller.setOriginConsent(true);
  assert.equal(await h.controller.saveOrigin(), false);
  h.controller.setRebindConsent(true);
  h.setResponse({ status: "configured", choice: { ...choice, revision: 8, choice_id: "22222222222242228222222222222222" } });
  assert.equal(await h.controller.saveOrigin(), true);
  assert.equal(body(h.calls[1]).allow_storage_rebind, true);
});

test("unavailable origin is not first-run and cannot be overwritten", async () => {
  const h = harness({ ...canonical, origin: { status: "unavailable", choice: null } });
  await h.controller.reload(); h.controller.editOrigin("namespace", origin.namespace); h.controller.editOrigin("host", origin.host); h.controller.setOriginConsent(true);
  fill(h.controller);
  assert.equal(await h.controller.saveOrigin(), false);
  assert.equal(await h.controller.inspect(), false);
  assert.equal(h.calls.length, 1);
});

test("reload preserves unsaved origin and target drafts but revokes consent and selection", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
  h.controller.editOrigin("host", "unsaved-host"); h.controller.setOriginConsent(true);
  const before = h.controller.getSnapshot();
  await h.controller.reload();
  assert.deepEqual(h.controller.getSnapshot().originDraft, before.originDraft);
  assert.deepEqual(h.controller.getSnapshot().draft, before.draft);
  assert.equal(h.controller.getSnapshot().confirmOrigin, false);
  assert.equal(h.controller.getSnapshot().inspection, null);
});

for (const field of ["socket_path", "thread_id", "project_id", "cwd"] as const) {
  test(`${field} edit invalidates exact inspection, including away/back ABA`, async () => {
    const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
    const original = h.controller.getSnapshot().draft[field];
    h.controller.editDraft(field, "different"); h.controller.editDraft(field, original);
    assert.equal(h.controller.getSnapshot().inspection, null);
    assert.equal(await h.controller.confirm(), false);
    assert.equal(h.calls.length, 2);
  });
}

test("editing during in-flight inspection discards late result even when target returns to original", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller);
  const gate = deferred(); h.setHandler(() => gate.promise);
  const inspection = h.controller.inspect();
  h.controller.editDraft("thread_id", "other"); h.controller.editDraft("thread_id", selected.thread_id);
  gate.resolve(selected); await inspection;
  assert.equal(h.controller.getSnapshot().inspection, null);
  assert.equal(h.controller.getSnapshot().status?.pending.length, 1);
});

test("expiry uses elapsed monotonic time including response delay, and blocks direct click without timer", async () => {
  let now = 100;
  const h = harness(canonical, { now: () => now }); await h.controller.reload(); fill(h.controller);
  await h.controller.inspect();
  now += 60_000;
  assert.equal(canConfirmConnection(h.controller.getSnapshot(), now), false);
  assert.equal(await h.controller.confirm(), false);
  h.controller.expireInspection(); assert.equal(h.controller.getSnapshot().inspection, null);
  const gate = deferred(); h.setHandler(() => gate.promise);
  const pending = h.controller.inspect(); now += 60_000; gate.resolve(selected); await pending;
  assert.equal(h.controller.getSnapshot().inspection, null);
});

for (const kind of ["origin", "inspect", "confirm", "detach"] as const) {
  test(`${kind} double invocation is synchronously blocked before the first response`, async () => {
    const h = harness(kind === "detach" ? { ...canonical, connection } : canonical);
    await h.controller.reload(); fill(h.controller);
    if (kind === "confirm") await h.controller.inspect();
    if (kind === "origin") { h.controller.useSavedOrigin(); h.controller.setOriginConsent(true); }
    const gate = deferred(); h.setHandler(() => gate.promise);
    const operation = () => kind === "origin" ? h.controller.saveOrigin() : h.controller[kind]();
    const count = h.calls.length;
    const first = operation(); assert.equal(await operation(), false); assert.equal(h.calls.length, count + 1);
    gate.reject(new Error("isolated fixture lost response")); await first;
    assert.equal(h.controller.getSnapshot().reloadRequired, true);
    assert.equal(await operation(), false); assert.equal(h.calls.length, count + 1);
  });
}

test("lost confirm response recovers current exact detach IDs only from canonical reload", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
  h.setHandler(async () => { throw new Error("response lost after possible commit"); });
  assert.equal(await h.controller.confirm(), false);
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
  h.setHandler(null); h.setStatus({ ...canonical, connection: { ...connection, inspection_id: "c".repeat(32), selection_id: "d".repeat(64), state: "disconnected" } });
  await h.controller.reload(); h.setResponse(detached);
  assert.equal(await h.controller.detach(), true);
  assert.deepEqual(body(h.calls.at(-1)!), { inspection_id: "c".repeat(32), selection_id: "d".repeat(64) });
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
});

test("detach remains available when origin is unavailable; origin save and inspect do not", async () => {
  const h = harness({ ...canonical, origin: { status: "unavailable", choice: null }, connection });
  await h.controller.reload(); fill(h.controller); h.setResponse(detached);
  assert.equal(await h.controller.inspect(), false);
  assert.equal(await h.controller.saveOrigin(), false);
  assert.equal(await h.controller.detach(), true);
});

test("ownership-changed receipt cannot detach or be silently replaced", async () => {
  const h = harness({ ...canonical, connection: { ...connection, state: "ownership_changed", can_detach: false } });
  await h.controller.reload(); fill(h.controller);
  assert.equal(await h.controller.detach(), false); assert.equal(await h.controller.inspect(), false); assert.equal(h.calls.length, 1);
});

test("hung mutation times out, aborts its request, ignores late success and requires reload", async () => {
  const h = harness(canonical, { timeoutMs: 10 }); await h.controller.reload(); fill(h.controller);
  const gate = deferred(); h.setHandler(() => gate.promise);
  assert.equal(await h.controller.inspect(), false);
  assert.equal(h.calls.at(-1)!.init?.signal?.aborted, true);
  assert.equal(h.controller.getSnapshot().busy, null);
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
  gate.resolve(selected); await Promise.resolve();
  assert.equal(h.controller.getSnapshot().inspection, null);
});

test("unmount aborts owned wait; StrictMode reactivation reload cannot adopt previous response", async () => {
  const h = harness();
  const old = deferred(); h.setHandler(() => old.promise);
  const first = h.controller.reload(); h.controller.deactivate();
  assert.equal(h.calls[0].init?.signal?.aborted, true);
  h.controller.activate(); h.setHandler(null); h.setStatus({ ...canonical, connection });
  const second = h.controller.reload();
  old.resolve(canonical); await first; await second;
  assert.equal(h.controller.getSnapshot().status?.connection?.thread_id, selected.thread_id);
  assert.equal(h.controller.getSnapshot().busy, null);
});

test("four known pending inspections cap further connector creation until canonical reload", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller);
  for (let index = 0; index < 4; index++) {
    h.setResponse({ ...selected, inspection_id: String(index + 1).repeat(32) });
    assert.equal(await h.controller.inspect(), true);
    h.controller.editDraft("cwd", selected.cwd);
  }
  assert.equal(canInspectConnection(h.controller.getSnapshot()), false);
  assert.equal(await h.controller.inspect(), false);
  assert.equal(h.calls.length, 5);
  await h.controller.reload(); assert.equal(canInspectConnection(h.controller.getSnapshot()), true);
});

for (const malformed of [
  { ...canonical, worker_delivery_enabled: true },
  { ...canonical, origin: { status: "configured", choice: { ...choice, revision: Number.MAX_SAFE_INTEGER + 1 } } },
  { ...canonical, origin: { status: "configured", choice: { ...choice, schema: undefined, schema_version: choice.schema } } },
  { ...canonical, origin: { status: "unconfigured", choice } },
  { ...canonical, connection: { ...connection, selection_id: "not-an-id" } },
  { ...canonical, connection: { ...connection, worker_delivery_enabled: true } },
]) {
  test(`malformed/unsupported status fails closed: ${JSON.stringify(malformed).slice(0, 95)}`, async () => {
    assert.throws(() => parseSharedStatus(malformed));
    const h = harness(malformed); assert.equal(await h.controller.reload(), false);
    fill(h.controller); assert.equal(await h.controller.inspect(), false); assert.equal(h.controller.getSnapshot().reloadRequired, true);
  });
}

test("inspect response identity mismatch requires reload and never allows confirm", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller); h.setResponse({ ...selected, thread_id: "different-thread" });
  assert.equal(await h.controller.inspect(), false); assert.equal(await h.controller.confirm(), false);
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
});

test("origin save mismatched receipt cannot turn into a successful configuration", async () => {
  const h = harness(); await h.controller.reload(); h.controller.useSavedOrigin(); h.controller.setOriginConsent(true);
  h.setResponse({ status: "configured", choice });
  assert.equal(await h.controller.saveOrigin(), false);
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
});

test("failed auth/status reload never unlocks mutation and failed retry does not clear recovery", async () => {
  const h = harness(); h.setHandler(async () => { throw new Error("403 operator authentication unavailable"); });
  assert.equal(await h.controller.reload(), false); assert.equal(await h.controller.reload(), false);
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
  assert.match(h.controller.getSnapshot().error!, /authenticated bridge/);
  assert.equal(h.calls.every((call) => call.init?.method === "GET"), true);
});

test("origin input preserves exact case and rejects guessed normalization or whitespace", () => {
  assert.equal(validOrigin(origin), true);
  assert.equal(validOrigin({ ...origin, namespace: "a:b_C.9-" }), true);
  for (const invalid of [{ ...origin, namespace: " machine" }, { ...origin, host: "host " }, { ...origin, host: "" }, { ...origin, host: "a\0b" }]) assert.equal(validOrigin(invalid), false);
});

for (const [field, value] of [
  ["authorization_id", "c".repeat(32)], ["selection_id", "d".repeat(64)], ["pex_session_id", "other"],
  ["thread_id", "other"], ["project_id", "other"], ["cwd", "C:\\wrong"], ["root_session_id", "other"],
  ["observation_only", false], ["delivery_proven", true], ["schema", "unsupported"], ["connection_generation", Number.MAX_SAFE_INTEGER + 1],
] as const) {
  test(`confirm receipt cannot claim success with mismatched ${field}`, async () => {
    const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
    h.setResponse({ ...confirmed, subscription: { ...subscription, [field]: value } });
    assert.equal(await h.controller.confirm(), false);
    assert.equal(h.controller.getSnapshot().reloadRequired, true);
    assert.doesNotMatch(h.controller.getSnapshot().notice ?? "", /subscription confirmed/);
  });
}

test("confirm validates full workspace receipt, including locator and storage measurement", async () => {
  for (const workspace_binding of [undefined, { ...binding, locator: { raw: "C:\\different" } }, { ...binding, origin_choice: { ...choice, storage_physical: { ...choice.storage_physical, object_id: "789" } } }]) {
    const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
    h.setResponse({ ...confirmed, workspace_binding });
    assert.equal(await h.controller.confirm(), false);
    assert.equal(h.controller.getSnapshot().reloadRequired, true);
  }
});

test("equivalent reordered workspace JSON remains valid in the confirm receipt", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
  h.setResponse({ ...confirmed, workspace_binding: Object.fromEntries(Object.entries(binding).reverse()) });
  assert.equal(await h.controller.confirm(), true);
});

test("known successful confirm followed by unavailable status stays reload-required without mutation retry", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
  h.setResponse(confirmed); assert.equal(await h.controller.confirm(), true);
  h.setHandler(async () => { throw new Error("canonical read unavailable"); });
  assert.equal(await h.controller.reload(), false);
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
  assert.equal(h.controller.getSnapshot().inspection, null);
  assert.equal(h.calls.filter((call) => call.path.endsWith("/confirm")).length, 1);
  assert.match(h.controller.getSnapshot().notice!, /subscription confirmed/);
});

test("missing subscription receipt cannot announce successful confirmation", async () => {
  const h = harness(); await h.controller.reload(); fill(h.controller); await h.controller.inspect();
  h.setResponse({ ...confirmed, subscription: undefined });
  assert.equal(await h.controller.confirm(), false);
  assert.equal(h.controller.getSnapshot().reloadRequired, true);
});

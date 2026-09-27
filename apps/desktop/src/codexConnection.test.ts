import assert from "node:assert/strict";
import test from "node:test";
import { codexCreationFailure, connectIsolatedCodex, createCodexWorker } from "./codexConnection.ts";
import { BridgeRequestError } from "./decisionContract.ts";

test("Codex connection sends one isolated attach and requires its exact receipt", async () => {
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  const signal = new AbortController().signal;
  const support = await connectIsolatedCodex(async (path, init) => {
    calls.push({ path, init });
    return {
      ok: true, name: "codex", kind: "stdio", isolated: true,
      existing_worker: false, support: "deep",
    };
  }, signal);
  assert.equal(support, "deep");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, "/v1/adapters/codex/attach");
  assert.equal(calls[0].init?.method, "POST");
  assert.equal(calls[0].init?.body, "{}");
  assert.equal(calls[0].init?.signal, signal);
  await assert.rejects(
    connectIsolatedCodex(async () => ({
      ok: true, name: "codex", kind: "desktop", isolated: false,
      existing_worker: true, support: "observe_only",
    }), signal),
    /not confirmed/,
  );
});

test("worker creation distinguishes rejected setup from ambiguous delivery", () => {
  for (const status of [400, 401, 403, 404, 409, 422]) {
    const failure = codexCreationFailure(new BridgeRequestError("fixture", { status }));
    assert.equal(failure.uncertain, false);
    assert.doesNotMatch(failure.message, /empty worker may exist/);
    if ([401, 403].includes(status)) assert.match(failure.message, /authenticated PEX desktop/);
    if (status === 404) assert.match(failure.message, /does not support worker creation/);
  }
  for (const error of [new BridgeRequestError("fixture", { status: 502 }), new Error("response lost")]) {
    assert.equal(codexCreationFailure(error).uncertain, true);
    assert.match(codexCreationFailure(error).message, /inspect Home before retrying/i);
  }
});

test("Codex worker creation requires an idle isolated receipt bound to the requested folder", async () => {
  const signal = new AbortController().signal;
  const folder = "C:\\project";
  const receipt = {
    ok: true, model_turn_started: false, requested_workspace: folder,
    session: { id: "codex:new-thread", vendor_session_id: "new-thread", harness_type: "codex",
      status: "idle", cwd: folder, metadata: { isolated: true, source: "pex_ui" } },
  };
  const calls: string[] = [];
  assert.deepEqual(await createCodexWorker(async (path, init) => {
    calls.push(path);
    assert.equal(init?.body, JSON.stringify({ workspace: folder }));
    assert.equal(init?.signal, signal);
    return receipt;
  }, ` ${folder} `, signal), { id: "codex:new-thread", cwd: folder });
  assert.deepEqual(calls, ["/v1/adapters/codex/threads"]);
  for (const response of [null, {}, { ...receipt, model_turn_started: true },
    { ...receipt, requested_workspace: "C:\\other" },
    ...[{ status: "working" }, { id: "codex:other" }, { metadata: { isolated: false } }]
      .map((change) => ({ ...receipt, session: { ...receipt.session, ...change } }))]) {
    await assert.rejects(createCodexWorker(async () => response, folder, signal), /not confirmed/);
  }
  await assert.rejects(createCodexWorker(async () => { throw new Error("must not call"); }, " ", signal), /local project folder/);
});

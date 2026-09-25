import assert from "node:assert/strict";
import test from "node:test";
import { connectIsolatedCodex } from "./codexConnection.ts";

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

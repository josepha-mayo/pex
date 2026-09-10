import assert from "node:assert/strict";
import test from "node:test";
import { connectOpenCode, openCodeOrigin } from "./openCodeConnection.ts";

test("OpenCode setup accepts only explicit loopback HTTP origins", () => {
  for (const value of ["http://127.0.0.1:4096", "http://localhost:4097/", "http://[::1]:4096/"]) {
    assert.equal(openCodeOrigin(value), new URL(value).origin);
  }
  for (const value of ["", "https://remote.example", "http://127.0.0.1.evil.test",
    "http://user:pass@localhost", "http://localhost/path", "http://localhost/?key=x",
    "http://localhost/#x", "http://localhost\\@evil.test", "file:///tmp/server"]) {
    assert.equal(openCodeOrigin(value), null, value);
  }
});

test("OpenCode attach sends one bridge request and validates its acknowledgement", async () => {
  let calls = 0;
  const signal = new AbortController().signal;
  await connectOpenCode(async (path, init) => {
    calls++;
    assert.equal(path, "/v1/adapters/opencode/attach");
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), { url: "http://127.0.0.1:4096" });
    assert.equal(init?.signal, signal);
    assert.equal(new Headers(init?.headers).has("Authorization"), false);
    return { ok: true, name: "opencode" };
  }, "http://127.0.0.1:4096/", signal);
  assert.equal(calls, 1);
});

test("OpenCode setup rejects invalid origins before I/O", async () => {
  await assert.rejects(connectOpenCode(async () => {
    assert.fail("must not send");
  }, "http://remote.example", new AbortController().signal));
});

test("OpenCode failed or ambiguous attach never retries or claims success", async () => {
  for (const result of [null, [], {}, { ok: false, name: "opencode" }, { ok: true, name: "codex" }, "lost"]) {
    let calls = 0;
    await assert.rejects(connectOpenCode(async () => {
      calls++;
      if (result === "lost") throw new Error("lost response");
      return result;
    }, "http://localhost:4096", new AbortController().signal));
    assert.equal(calls, 1);
  }
});

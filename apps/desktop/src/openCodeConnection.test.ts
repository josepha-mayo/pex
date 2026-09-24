import assert from "node:assert/strict";
import test from "node:test";
import { connectOpenCode, openCodeConnectionFailure, openCodeOrigin } from "./openCodeConnection.ts";
import { BridgeRequestError } from "./decisionContract.ts";

test("OpenCode connection failures distinguish rejection from uncertainty without leaking diagnostics", () => {
  for (const status of [401, 403, 409, 502]) {
    const notice = openCodeConnectionFailure(new BridgeRequestError("private diagnostic", { status }));
    assert.doesNotMatch(notice, /private diagnostic/);
    assert.doesNotMatch(notice, /lost response/);
  }
  assert.match(openCodeConnectionFailure(new BridgeRequestError("probe", { status: 502 })), /session access/);
  assert.match(openCodeConnectionFailure(new BridgeRequestError("busy", { status: 409 })), /active connection/);
  assert.match(openCodeConnectionFailure(new DOMException("aborted", "AbortError")), /lost response/);
  assert.match(openCodeConnectionFailure(new Error("network")), /lost response/);
});

test("OpenCode onboarding explains the separate server and worker without starting a task", async () => {
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { createServer } = await import("vite");
  const vite = await createServer({
    root: process.cwd(), server: { middlewareMode: true, hmr: false, ws: false }, appType: "custom",
  });
  try {
    const { OpenCodeConnectionPanel } = await vite.ssrLoadModule("/src/components/OpenCodeConnectionPanel.tsx");
    const html = renderToStaticMarkup(createElement(OpenCodeConnectionPanel, {
      request: async () => assert.fail("render must not connect or start work"),
      available: true,
    }));
    assert.match(html, /opencode serve --port 4096/);
    assert.match(html, /opencode attach http:\/\/127\.0\.0\.1:4096/);
    assert.match(html, /connect OpenCode Desktop to that same server/);
    assert.match(html, /Create or resume a session there/);
    assert.match(html, /it does not start a task/);
    assert.match(html, /Put model keys in Supervisor settings, not the server address/);
    assert.ok(html.indexOf(">Connect OpenCode</button>") < html.indexOf(">How to start and attach OpenCode</summary>"));
    const offline = renderToStaticMarkup(createElement(OpenCodeConnectionPanel, {
      request: async () => assert.fail("offline render must not connect"),
      available: false,
    }));
    assert.match(offline, /disabled=""[^>]*>Connect OpenCode</);
    assert.match(offline, /has not confirmed the local bridge/);
  } finally {
    await vite.close();
  }
});

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

test("OpenCode password is sent only in the authenticated bridge body", async () => {
  const signal = new AbortController().signal;
  await connectOpenCode(async (path, init) => {
    assert.equal(path, "/v1/adapters/opencode/attach");
    assert.deepEqual(JSON.parse(String(init?.body)), {
      url: "http://127.0.0.1:4096", username: "opencode", password: "server-password-canary",
    });
    assert.equal(new Headers(init?.headers).has("Authorization"), false);
    return { ok: true, name: "opencode" };
  }, "http://127.0.0.1:4096", signal, { username: "", password: "server-password-canary" });
});

test("OpenCode malformed server credentials fail before I/O", async () => {
  for (const credentials of [
    { username: "user\nname", password: "secret" },
    { username: "opencode", password: "secret\n" },
    { username: "opencode", password: "x".repeat(4097) },
  ]) {
    await assert.rejects(connectOpenCode(async () => assert.fail("must not send"),
      "http://localhost:4096", new AbortController().signal, credentials));
  }
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

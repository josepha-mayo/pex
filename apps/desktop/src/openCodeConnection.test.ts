import assert from "node:assert/strict";
import test from "node:test";
import { connectOpenCode, openCodeOrigin } from "./openCodeConnection.ts";

test("OpenCode onboarding explains the separate server and worker without starting a task", async () => {
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { createServer } = await import("vite");
  const vite = await createServer({
    root: process.cwd(), server: { middlewareMode: true, hmr: false }, appType: "custom",
  });
  try {
    const { OpenCodeConnectionPanel } = await vite.ssrLoadModule("/src/components/OpenCodeConnectionPanel.tsx");
    const html = renderToStaticMarkup(createElement(OpenCodeConnectionPanel, {
      request: async () => assert.fail("render must not connect or start work"),
    }));
    assert.match(html, /opencode serve --port 4096/);
    assert.match(html, /opencode attach http:\/\/127\.0\.0\.1:4096/);
    assert.match(html, /Create or resume your worker session there/);
    assert.match(html, /does not restart OpenCode or start a task/);
    assert.match(html, /Zen key belongs in Supervisor settings, not this address/);
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

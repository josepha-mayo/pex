import assert from "node:assert/strict";
import test from "node:test";
import { createOperatorRequest } from "./operatorRequest.ts";

const baseUrl = "http://127.0.0.1:7420";

test("operator request authenticates one exact JSON mutation without allowing redirects", async () => {
  let calls = 0;
  const request = createOperatorRequest({ baseUrl, readToken: async () => "fixture-only",
    send: async (url, init) => {
      calls++;
      assert.equal(url, `${baseUrl}/v1/local-workspace-origin`);
      assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer fixture-only");
      assert.equal(new Headers(init?.headers).get("Content-Type"), "application/json");
      assert.equal(init?.method, "PATCH");
      assert.equal(init?.body, '{"confirm_local_origin":true}');
      assert.equal(init?.redirect, "error");
      assert.equal(init?.cache, "no-store");
      return Response.json({ status: "configured" });
    },
  });
  assert.deepEqual(await request("/v1/local-workspace-origin", { method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: "stale-fixture" },
    body: '{"confirm_local_origin":true}', redirect: "follow",
  }), { status: "configured" });
  assert.equal(calls, 1);
});

for (const status of [401, 409, 500]) {
  test(`operator mutation does not retry HTTP ${status}`, async () => {
    let calls = 0;
    let tokenReads = 0;
    const request = createOperatorRequest({ baseUrl,
      readToken: async () => { tokenReads++; return "fixture-only"; },
      send: async () => { calls++; return Response.json({ detail: { code: "fixture_failure", message: "Reload" } }, { status }); },
    });
    await assert.rejects(request("/v1/adapters/codex/shared/confirm", { method: "POST" }),
      (error: any) => error.status === status && error.code === "fixture_failure");
    assert.equal(calls, 1);
    assert.equal(tokenReads, 1);
  });
}

test("lost response and malformed success do not resend", async () => {
  for (const mode of ["lost", "malformed"]) {
    let calls = 0;
    const request = createOperatorRequest({ baseUrl, readToken: async () => "fixture-only",
      send: async () => { calls++; if (mode === "lost") throw new TypeError("response lost"); return new Response("not JSON"); },
    });
    await assert.rejects(request("/v1/adapters/codex/shared/detach", { method: "POST" }));
    assert.equal(calls, 1);
  }
});

test("failed native token acquisition sends nothing", async () => {
  let calls = 0;
  const request = createOperatorRequest({ baseUrl,
    readToken: async () => { throw new Error("native token unavailable"); },
    send: async () => { calls++; return Response.json({}); },
  });
  await assert.rejects(request("/v1/local-workspace-origin"), /native token unavailable/);
  assert.equal(calls, 0);
});

test("foreign URL is refused before reading the credential", async () => {
  let tokenReads = 0;
  const request = createOperatorRequest({ baseUrl,
    readToken: async () => { tokenReads++; return "fixture-only"; },
    send: async () => { throw new Error("must not send"); },
  });
  for (const path of ["https://foreign.invalid/v1/state", "//foreign.invalid/v1/state"]) {
    await assert.rejects(request(path), /Invalid local operator route/);
  }
  assert.equal(tokenReads, 0);
});

test("tokenless browser development does not reuse a caller bearer", async () => {
  const request = createOperatorRequest({ baseUrl, readToken: async () => null,
    send: async (_url, init) => {
      assert.equal(new Headers(init?.headers).has("Authorization"), false);
      return Response.json({ status: "unconfigured" });
    },
  });
  await request("/v1/local-workspace-origin", { headers: { Authorization: "stale-fixture" } });
});

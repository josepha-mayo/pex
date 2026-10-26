import test from "node:test";
import assert from "node:assert/strict";
import { createOwnerClient, type OwnerView } from "./client.ts";

const ORIGIN = "https://owner.example.test";
const SECRET = "S".repeat(43); // Authored fixture only.
const CSRF = "C".repeat(43);
const authenticated = () => new Response(JSON.stringify({ authenticated: true, principal_id: "web-owner", csrf_token: CSRF, expires_in_seconds: 900 }));
const denied = () => new Response("", { status: 401 });
const deferred = <T>() => { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; };

function fixture(responses: Array<Response | Promise<Response> | Error>) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const views: OwnerView[] = [];
  const client = createOwnerClient({ origin: ORIGIN, now: () => 100000, changed: view => views.push(view),
    send: (async (url, init) => {
      calls.push({ url: String(url), init: init! });
      const reply = responses.shift();
      if (reply instanceof Error) throw reply;
      assert.ok(reply, "unexpected duplicate request");
      return await reply;
    }) as typeof fetch });
  return { client, calls, views };
}

test("requires canonical HTTPS owner origin", () => {
  for (const origin of ["http://owner.example.test", ORIGIN + "/", ORIGIN + "/x", ORIGIN + "?x=y"]) {
    assert.throws(() => createOwnerClient({ origin, changed() {} }));
  }
});

test("bootstrap then login then logout uses exact same-origin cookie routes once", async () => {
  const f = fixture([denied(), authenticated(), new Response('{"authenticated":false}')]);
  await f.client.check(); assert.equal(f.client.state().phase, "signed-out");
  await f.client.login(SECRET); assert.equal(f.client.state().phase, "signed-in");
  assert.equal(f.client.state().expiresAt, 999000);
  await f.client.logout(); assert.equal(f.client.state().phase, "signed-out");
  assert.equal(f.calls.length, 3);
  assert.deepEqual(f.calls.map(x => x.url), ["session", "login", "logout"].map(x => ORIGIN + "/owner/auth/" + x));
  for (const { init } of f.calls) {
    assert.equal(init.credentials, "same-origin"); assert.equal(init.redirect, "error"); assert.equal(init.cache, "no-store");
    assert.equal(new Headers(init.headers).has("authorization"), false);
  }
  assert.equal(new Headers(f.calls[2].init.headers).get("x-pex-owner-csrf"), CSRF);
  assert.equal(JSON.stringify(f.views).includes(SECRET), false);
  assert.equal(JSON.stringify(f.views).includes(CSRF), false);
});

test("double login and repeated logout do not duplicate requests", async () => {
  const response = deferred<Response>();
  const f = fixture([denied(), response.promise, new Response('{"authenticated":false}')]);
  await f.client.check(); const first = f.client.login(SECRET); await f.client.login(SECRET);
  assert.equal(f.calls.length, 2); response.resolve(authenticated()); await first;
  const logout = f.client.logout(); await f.client.logout(); await logout; assert.equal(f.calls.length, 3);
});

test("late login after local lock cannot restore authenticated view", async () => {
  const response = deferred<Response>(); const f = fixture([denied(), response.promise]);
  await f.client.check(); const pending = f.client.login(SECRET); f.client.lock();
  assert.equal(f.calls[1].init.signal?.aborted, true);
  response.resolve(authenticated()); await pending;
  assert.equal(f.client.state().phase, "locked"); assert.equal(f.views.some(x => x.phase === "signed-in"), false);
});

test("late status cannot overwrite newer signed-out generation", async () => {
  const response = deferred<Response>(); const f = fixture([response.promise, denied()]);
  const old = f.client.check(); await f.client.check(); response.resolve(authenticated()); await old;
  assert.equal(f.client.state().phase, "signed-out"); assert.equal(f.calls[0].init.signal?.aborted, true);
});

test("logout locks before network and failures remain explicitly uncertain", async () => {
  const response = deferred<Response>(); const f = fixture([authenticated(), response.promise]);
  await f.client.check(); const pending = f.client.logout();
  assert.equal(f.client.state().phase, "locked");
  response.resolve(new Response("", { status: 500 })); await pending;
  assert.match(f.client.state().message, /could not be confirmed/);
  assert.equal(f.calls.length, 2); await f.client.logout(); assert.equal(f.calls.length, 2);
});

test("unconfigured service never becomes a fake operational workspace", async () => {
  const f = fixture([new Response("", { status: 503 })]); await f.client.check();
  assert.equal(f.client.state().phase, "unavailable"); assert.match(f.client.state().message, /not configured/);
});

test("invalid owner secret is never transmitted", async () => {
  const f = fixture([denied()]); await f.client.check(); await f.client.login("not-a-provider-key");
  assert.equal(f.calls.length, 1); assert.equal(f.client.state().phase, "signed-out");
});

test("invalid/oversized response cannot admit an owner", async () => {
  for (const body of ["null", "[]", '{"authenticated":true}',
    JSON.stringify({ authenticated: true, principal_id: "web-owner", csrf_token: CSRF, expires_in_seconds: true }),
    JSON.stringify({ authenticated: true, principal_id: "web-owner", csrf_token: CSRF, expires_in_seconds: 99999 }),
    " ".repeat(8193)]) {
    const f = fixture([new Response(body)]); await f.client.check(); assert.equal(f.client.state().phase, "unavailable");
  }
});

test("network errors and rate limits are not transparently retried", async () => {
  for (const response of [new Error("network"), new Response("", { status: 429 })]) {
    const f = fixture([denied(), response]); await f.client.check(); await f.client.login(SECRET);
    assert.equal(f.calls.length, 2); assert.notEqual(f.client.state().phase, "signed-in");
  }
});

test("dispose aborts and suppresses late view updates", async () => {
  const response = deferred<Response>(); const f = fixture([response.promise]); const pending = f.client.check();
  f.client.dispose(); const count = f.views.length; response.resolve(authenticated()); await pending;
  await f.client.check(); await f.client.login(SECRET); await f.client.logout();
  assert.equal(f.views.length, count); assert.equal(f.calls.length, 1); assert.equal(f.calls[0].init.signal?.aborted, true);
});


test("delayed status conservatively anchors expiry before the request", async () => {
  let clock = 100000; const reply = deferred<Response>(); const views: OwnerView[] = [];
  const client = createOwnerClient({ origin: ORIGIN, now: () => clock, changed: v => views.push(v),
    send: (async () => reply.promise) as typeof fetch });
  const pending = client.check(); clock += 5000; reply.resolve(authenticated()); await pending;
  assert.equal(client.state().phase, "signed-in"); assert.equal(client.state().expiresAt, 999000);
  assert.equal(client.state().expiresAt! - clock, 894000);
});

test("already-expired-on-arrival and backward-clock replies never reveal workspace", async () => {
  for (const arrival of [1000000, 999000, 99000]) {
    let clock = 100000; const reply = deferred<Response>(); const views: OwnerView[] = [];
    const client = createOwnerClient({ origin: ORIGIN, now: () => clock, changed: v => views.push(v),
      send: (async () => reply.promise) as typeof fetch });
    const pending = client.check(); clock = arrival; reply.resolve(authenticated()); await pending;
    assert.equal(client.state().phase, "signed-out"); assert.equal(views.some(v => v.phase === "signed-in"), false);
  }
});

test("login transit delay cannot extend owner display expiry", async () => {
  let clock = 100000; const reply = deferred<Response>(); let calls = 0;
  const client = createOwnerClient({ origin: ORIGIN, now: () => clock, changed() {},
    send: (async () => ++calls === 1 ? denied() : reply.promise) as typeof fetch });
  await client.check(); const pending = client.login(SECRET); clock += 6000; reply.resolve(authenticated()); await pending;
  assert.equal(client.state().expiresAt, 999000);
});

test("trailing newline cannot turn a 44-character value into an owner or CSRF token", async () => {
  const f = fixture([denied()]); await f.client.check(); await f.client.login(SECRET + "\n");
  assert.equal(f.calls.length, 1);
  const g = fixture([new Response(JSON.stringify({ authenticated:true, principal_id:"web-owner", csrf_token:CSRF + "\n", expires_in_seconds:900 }))]);
  await g.client.check(); assert.equal(g.client.state().phase, "unavailable");
});

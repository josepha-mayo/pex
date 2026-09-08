import assert from "node:assert/strict";
import test from "node:test";
import { boundedRead, coalesceBackgroundRead, startSerialPolling } from "./readBudget.ts";

test("a stalled complete read times out and aborts even if its implementation ignores abort", async () => {
  let signal: AbortSignal | undefined;
  await assert.rejects(boundedRead((incoming) => {
    signal = incoming;
    return new Promise(() => {});
  }, undefined, 5), /timed out/);
  assert.equal(signal?.aborted, true);
});

test("read cancellation propagates and already-cancelled reads never start", async () => {
  const parent = new AbortController();
  let signal: AbortSignal | undefined;
  const pending = boundedRead((incoming) => {
    signal = incoming;
    return new Promise(() => {});
  }, parent.signal);
  parent.abort();
  await assert.rejects(pending, /cancelled/);
  assert.equal(signal?.aborted, true);
  await assert.rejects(boundedRead(() => {
    assert.fail("cancelled read must not start");
  }, parent.signal), /cancelled/);
});

test("successful reads keep their value and errors without late timeout side effects", async () => {
  let signal: AbortSignal | undefined;
  assert.equal(await boundedRead(async (incoming) => { signal = incoming; return 42; }), 42);
  assert.equal(signal?.aborted, false);
  const failure = new Error("original read failure");
  await assert.rejects(boundedRead(async () => { throw failure; }), (error) => error === failure);
});

test("polling schedules nothing while a read is pending and never resumes after cleanup", async () => {
  let calls = 0;
  let finish: () => void = () => {};
  let scheduled: (() => void) | undefined;
  const stop = startSerialPolling(() => {
    calls += 1;
    return new Promise<void>((resolve) => { finish = resolve; });
  }, 4000, (callback, delay) => {
    assert.equal(delay, 4000);
    scheduled = callback;
    return () => { scheduled = undefined; };
  });
  assert.equal(calls, 1);
  assert.equal(scheduled, undefined);
  finish();
  await Promise.resolve();
  assert.ok(scheduled);
  const next = scheduled as () => void;
  scheduled = undefined;
  next();
  assert.equal(calls, 2);
  assert.equal(scheduled, undefined);
  stop();
  finish();
  await Promise.resolve();
  assert.equal(scheduled, undefined);
  next();
  assert.equal(calls, 2);
});

test("stopping a goal poll aborts both pending evidence reads and schedules no follow-up", async () => {
  const signals: AbortSignal[] = [];
  let scheduled = 0;
  const stop = startSerialPolling(async (signal) => {
    await Promise.allSettled([0, 1].map(() => boundedRead((incoming) => {
      signals.push(incoming);
      return new Promise(() => {});
    }, signal)));
  }, 4000, () => { scheduled += 1; return () => {}; });
  assert.equal(signals.length, 2);
  stop();
  assert.ok(signals.every((signal) => signal.aborted));
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(scheduled, 0);
});

test("polling retries a rejected read at the normal interval, never in a tight loop", async () => {
  let calls = 0;
  let scheduled: (() => void) | undefined;
  const stop = startSerialPolling(async () => { calls += 1; throw new Error("offline"); },
    4000, (callback) => { scheduled = callback; return () => { scheduled = undefined; }; });
  await Promise.resolve();
  assert.equal(calls, 1);
  assert.ok(scheduled);
  stop();
  assert.equal(scheduled, undefined);
});

test("an event burst shares one background read but the next observation is fresh", async () => {
  let calls = 0;
  let finish: (value: number) => void = () => {};
  const read = coalesceBackgroundRead(() => {
    calls += 1;
    return new Promise<number>((resolve) => { finish = resolve; });
  });
  const burst = Array.from({ length: 100 }, () => read());
  await Promise.resolve();
  assert.equal(calls, 1);
  assert.ok(burst.every((pending) => pending === burst[0]));
  finish(42);
  assert.deepEqual(await Promise.all(burst), Array(100).fill(42));
  const next = read();
  await Promise.resolve();
  assert.equal(calls, 2);
  finish(43);
  assert.equal(await next, 43);
});

test("a failed background read is not cached and explicit reads stay independent", async () => {
  let calls = 0;
  const raw = async () => { calls += 1; throw new Error("offline"); };
  const read = coalesceBackgroundRead(raw);
  await assert.rejects(read(), /offline/);
  await assert.rejects(read(), /offline/);
  await assert.rejects(raw(), /offline/);
  assert.equal(calls, 3);
});

test("app uses serialized background polls and bounds JSON and asset bodies, not mutations", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.ok(!/window\.setInterval/.test(source), "background polls must not use overlapping intervals");
  assert.match(source, /startSerialPolling\(/);
  assert.match(source, /method === "GET"[\s\S]*?boundedRead/);
  assert.match(source, /boundedRead\(async \(signal\) =>[\s\S]*?response\.blob\(\)/);
  assert.match(source, /controller\.abort\(\)/);
});

test("goal evidence polling is bound to goal intent, not every session snapshot", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const start = source.indexOf("const evidenceKey =");
  const end = source.indexOf("const loadDetails =", start);
  assert.ok(start > 0 && end > start);
  const effect = source.slice(start, end);
  assert.ok(!/markCanonical, sessions\]/.test(effect), "worker snapshots must not restart reads");
  assert.ok(/startSerialPolling\(async \(signal\)/.test(effect));
  assert.ok(/completion`, \{ signal \}\)/.test(effect));
  assert.ok(/decisions`, \{ signal \}\)/.test(effect));
  assert.ok(/cancelled = true;\s*stopPolling\(\)/.test(effect));
});

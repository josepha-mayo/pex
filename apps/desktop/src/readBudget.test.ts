import assert from "node:assert/strict";
import test from "node:test";
import {
  boundedRead, boundedReadBatch, boundedSingleFlightRead, coalesceBackgroundRead,
  createBurstRefreshGate,
  startSerialPolling,
} from "./readBudget.ts";

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

test("event-page bursts schedule one trailing refresh and cleanup cancels it", () => {
  let calls = 0;
  let scheduled: (() => void) | undefined;
  let delay = 0;
  const gate = createBurstRefreshGate(() => { calls += 1; }, 250, (callback, ms) => {
    scheduled = callback;
    delay = ms;
    return () => { scheduled = undefined; };
  });
  for (let index = 0; index < 100; index += 1) gate.trigger();
  assert.equal(delay, 250);
  assert.ok(scheduled);
  const first = scheduled as () => void;
  first();
  assert.equal(calls, 1);
  gate.trigger();
  assert.ok(scheduled);
  gate.stop();
  assert.equal(scheduled, undefined);
  first();
  assert.equal(calls, 1);
  gate.trigger();
  assert.equal(scheduled, undefined);
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

test("Inspector polling does not request Deck-only benchmark and discovery scans", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const start = source.indexOf('const includeDeckOnPoll = surface === "deck";');
  const end = source.indexOf('}, [bridgeAvailable, loadDetails, pageVisible, shell, surface]);', start);
  assert.ok(start > 0 && end > start);
  const effect = source.slice(start, end);
  assert.match(effect, /slowDetailsRequested = includeDeckOnPoll;/);
  assert.doesNotMatch(effect, /slowDetailsRequested = true;/);
  assert.match(effect, /await loadDetails\(includeSlowDetails, showLoading, controller.signal\)/);
  assert.match(source, /includeDeck\s*\? bridgeJson<DeckData>\("\/v1\/deck"/);
  assert.match(source, /includeDeck\s*\? bridgeJson<\{ runs\?/);
});

test("goal evidence polling is bound to goal intent, not every session snapshot", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const start = source.indexOf("const evidenceKey =");
  const end = source.indexOf("const loadDetails =", start);
  assert.ok(start > 0 && end > start);
  const effect = source.slice(start, end);
  assert.ok(!/markCanonical, sessions\]/.test(effect), "worker snapshots must not restart reads");
  assert.match(effect, /coalesceBackgroundRead\(async \(\) =>/);
  assert.match(effect, /goalEvidenceRefresh\.current = refreshGoalEvidence/);
  assert.match(effect, /GOAL_EVIDENCE_RECONCILIATION_INTERVAL_MS/);
  assert.ok(/completion`, \{ signal \}\)/.test(effect));
  assert.ok(/decisions`, \{ signal \}\)/.test(effect));
  assert.ok(/cancelled = true;[\s\S]*?controller\.abort\(\);[\s\S]*?stopPolling\(\)/.test(effect));
  assert.match(
    source,
    /message\.topic === "event_page"[\s\S]*?eventDerivedRefresh\.trigger\(\)/,
    "committed event pages should wake attached-goal evidence without waiting for polling",
  );
});

test("filesystem benchmark and harness discovery reads follow the slow detail tick", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const start = source.indexOf("const loadDetails =");
  const end = source.indexOf("const loadProjectIdentityConflicts", start);
  assert.ok(start > 0 && end > start);
  const details = source.slice(start, end);
  assert.match(
    details,
    /includeDeck\s*\?\s*bridgeJson<\{ found\?:[\s\S]*?>\("\/v1\/discover", \{ signal \}\)\s*:\s*Promise\.resolve/u,
    "the eight-second lightweight poll must not launch process discovery every pass",
  );
  assert.match(
    details,
    /includeDeck\s*\?\s*bridgeJson<\{ runs\?: BenchRun\[\]; message\?: string \}>\("\/v1\/bench\/runs", \{ signal \}\)\s*:\s*Promise\.resolve/u,
    "the eight-second lightweight poll must not synchronously reread benchmark artifacts",
  );
});

test("canonical detail reads are event-first with one slow full reconciliation", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /const DETAIL_RECONCILIATION_INTERVAL_MS = 32_000/);
  assert.match(source, /const eventDerivedRefresh = createBurstRefreshGate\([\s\S]*?detailRefresh\.current\?\.\(\)/);
  assert.match(source, /message\.topic === "event_page"[\s\S]*?eventDerivedRefresh\.trigger\(\)/);
  assert.match(source, /const refreshDetails = coalesceBackgroundRead/);
  assert.match(source, /let slowDetailsRequested = false/);
  assert.match(source, /const refreshSlowDetails = \(\) => \{[\s\S]*?slowDetailsRequested = includeDeckOnPoll;\s*return refreshDetails\(\);\s*\}/);
  assert.match(source, /refreshSlowDetails,\s*DETAIL_RECONCILIATION_INTERVAL_MS/);
  assert.doesNotMatch(source, /loadDetails\(ticks % 4 === 0, ticks === 0, signal\)/);
  assert.doesNotMatch(source, /surface, pet\?\.last_action\?\.id\]\)/);
});

test("the newest detail read always releases loading even when it did not start it", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const detailStart = source.indexOf("const loadDetails =");
  const detailEnd = source.indexOf("const loadProjectIdentityConflicts", detailStart);
  const detail = source.slice(detailStart, detailEnd);
  assert.ok(detailStart >= 0 && detailEnd > detailStart);
  assert.match(
    detail,
    /if \(requestSequence !== detailRequestSequence\.current\) return;[\s\S]*setDetailsLoading\(false\)/,
  );
  assert.doesNotMatch(detail, /if \(showLoading\) setDetailsLoading\(false\)/);
});

test("two-pet settings retain slow base reads without hatch polling", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /const BASE_STATE_RECONCILIATION_INTERVAL_MS = 30_000/);
  assert.match(source, /const SETTINGS_ACTIVITY_RECONCILIATION_INTERVAL_MS = 30_000/);
  assert.doesNotMatch(source, /loadHatchJobs|ACTIVE_HATCH_|\/v1\/pets\/hatch/);
  assert.match(source, /loadCursorRejections\(signal\),\s*SETTINGS_ACTIVITY_RECONCILIATION_INTERVAL_MS/);
  const baseStart = source.indexOf("const loadBaseState =");
  const baseEnd = source.indexOf("const loadCursorRejections", baseStart);
  const base = source.slice(baseStart, baseEnd);
  assert.doesNotMatch(base, /\/v1\/pets\/hatch(?:"|\?)/);
  assert.doesNotMatch(base, /\/v1\/hooks\/cursor\/rejections/);
});

test("view-owned background reads propagate cancellation and handoff reads use a bounded batch", async () => {
  // Source wiring only; native/UI lifecycle checks are a separate release gate.
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  for (const call of [
    "refreshPet(controller.signal)",
    "loadBaseState(signal)",
    "loadCursorRejections(signal)",
    "refreshPetGoals(signal)",
    "loadDetails(includeSlowDetails, showLoading, controller.signal)",
    "loadProjectIdentityConflicts({ showLoading, signal: controller.signal })",
    "loadProjectIdentityStatus({ showLoading, signal: controller.signal })",
  ]) assert.ok(source.includes(call), `missing lifetime cancellation: ${call}`);
  assert.match(source, /detailRefresh\.current === refreshDetails[\s\S]*?controller\.abort\(\)/);
  assert.match(source, /identityConflictRefresh\.current === refreshConflicts[\s\S]*?controller\.abort\(\)/);
  assert.match(source, /identityStatusRefresh\.current === refreshStatus[\s\S]*?controller\.abort\(\)/);
  const batchStart = source.indexOf("async function loadHandoffAssimilationStatuses(");
  const batchEnd = source.indexOf("function operationError", batchStart);
  const batch = source.slice(batchStart, batchEnd);
  assert.match(batch, /boundedReadBatch\(/);
  assert.doesNotMatch(batch, /Promise\.allSettled\(/);
  assert.match(batch, /\{ signal: readSignal \}/);
});

test("a read batch caps concurrency at four and retains ordered successes and failures", async () => {
  const items = Array.from({ length: 9 }, (_, index) => index);
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const calls: number[] = [];
  let active = 0;
  let peak = 0;
  const pending = boundedReadBatch(items, async (item) => {
    calls.push(item);
    active += 1;
    peak = Math.max(peak, active);
    try {
      await gate;
      if (item === 5) throw new Error("fixture rejection");
      return item * 2;
    } finally {
      active -= 1;
    }
  });
  assert.deepEqual(calls, [0, 1, 2, 3]);
  release();
  const settled = await pending;
  assert.equal(peak, 4);
  assert.deepEqual(calls, items);
  assert.equal(settled.length, items.length);
  settled.forEach((result, index) => {
    if (index === 5) {
      assert.equal(result.status, "rejected");
      if (result.status === "rejected") assert.match(String(result.reason), /fixture rejection/);
    } else assert.deepEqual(result, { status: "fulfilled", value: index * 2 });
  });
});

test("handoff assimilation is event-first with a slow reconciliation and never blocks core history", async () => {
  // Source contract: rendered/native latency is a separate acceptance check.
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const start = source.indexOf("const loadDetails =");
  const end = source.indexOf("const loadProjectIdentityConflicts =", start);
  const details = source.slice(start, end);
  assert.doesNotMatch(details, /loadHandoffAssimilationStatuses\(/);
  assert.doesNotMatch(details, /await assimilationRequest/);
  assert.match(details, /handoffInterventions\.current = currentInterventions/);
  assert.match(details, /nextHandoffKey !== handoffInterventionKey\.current[\s\S]*?setHandoffAssimilation\(\{\}\)[\s\S]*?handoffAssimilationRefresh\.current\?\.\(\)/);

  assert.match(source, /const HANDOFF_ASSIMILATION_RECONCILIATION_INTERVAL_MS = 30_000/);
  assert.match(source, /const eventDerivedRefresh = createBurstRefreshGate\([\s\S]*?handoffAssimilationRefresh\.current\?\.\(\)/);
  assert.match(source, /setHandoffAssimilation\(\{\}\);\s*const refreshHandoffAssimilation = coalesceBackgroundRead/);
  assert.match(source, /handoffInterventionKey\.current !== requestedKey[\s\S]*?return/);
  assert.match(source, /startSerialPolling\([\s\S]*?refreshHandoffAssimilation,[\s\S]*?HANDOFF_ASSIMILATION_RECONCILIATION_INTERVAL_MS/);
});

test("a batch deadline aborts active reads and leaves queued and late results unavailable", async () => {
  const signals: AbortSignal[] = [];
  const finish: ((value: string) => void)[] = [];
  const settled = await boundedReadBatch(Array.from({ length: 200 }, (_, index) => index),
    (_item, signal) => {
      signals.push(signal);
      return new Promise<string>((resolve) => { finish.push(resolve); });
    }, undefined, 5);
  assert.equal(signals.length, 4);
  assert.ok(signals.every((signal) => signal.aborted));
  assert.equal(settled.length, 200);
  for (const result of settled) {
    assert.equal(result.status, "rejected");
    if (result.status === "rejected") assert.match(String(result.reason), /timed out/);
  }
  finish.forEach((resolve) => resolve("late stale status"));
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(signals.length, 4, "late completion must not release queued reads");
  assert.ok(settled.every((result) => result.status === "rejected"));
});

test("caller cancellation keeps completed observations and cancels the rest of the batch", async () => {
  const controller = new AbortController();
  const pending = boundedReadBatch([0, 1, 2, 3, 4, 5], async (item) => {
    if (item === 0) return "observed";
    return new Promise<string>(() => {});
  }, controller.signal);
  await Promise.resolve();
  await Promise.resolve();
  controller.abort();
  const settled = await pending;
  assert.deepEqual(settled[0], { status: "fulfilled", value: "observed" });
  assert.ok(settled.slice(1).every((result) => result.status === "rejected"));
});

test("empty and already-cancelled batches perform no read", async () => {
  const controller = new AbortController();
  controller.abort();
  const never = async () => { assert.fail("must not issue a read"); };
  assert.deepEqual(await boundedReadBatch([], never), []);
  const cancelled = await boundedReadBatch([1, 2], never, controller.signal);
  assert.equal(cancelled.length, 2);
  assert.ok(cancelled.every((result) => result.status === "rejected"));
});

test("a timed-out native read cannot multiply calls or later publish its old result", async () => {
  let calls = 0;
  let release: (value: string) => void = () => {};
  const read = boundedSingleFlightRead(() => {
    calls += 1;
    return calls === 1
      ? new Promise<string>((resolve) => { release = resolve; })
      : Promise.resolve("fresh status");
  }, 5);
  await assert.rejects(read(), /timed out/);
  for (let index = 0; index < 20; index += 1) {
    await assert.rejects(read(), /still pending/);
  }
  assert.equal(calls, 1);
  release("stale ready status");
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(await read(), "fresh status");
  assert.equal(calls, 2);
});

test("native reads share a pending call but do not cache completed observations", async () => {
  let calls = 0;
  let release: (value: number) => void = () => {};
  const read = boundedSingleFlightRead(() => {
    calls += 1;
    return new Promise<number>((resolve) => { release = resolve; });
  });
  const first = read();
  const second = read();
  await Promise.resolve();
  assert.equal(calls, 1);
  release(1);
  assert.deepEqual(await Promise.all([first, second]), [1, 1]);
  const fresh = read();
  await Promise.resolve();
  assert.equal(calls, 2);
  release(2);
  assert.equal(await fresh, 2);
});

test("cancelled native reads reject stale results without duplicating uncancellable work", async () => {
  const caller = new AbortController();
  let calls = 0;
  let reject: (error: Error) => void = () => {};
  const read = boundedSingleFlightRead(() => {
    calls += 1;
    return calls === 1
      ? new Promise<string>((_resolve, fail) => { reject = fail; })
      : Promise.resolve("fresh");
  });
  const pending = read(caller.signal);
  await Promise.resolve();
  caller.abort();
  await assert.rejects(pending, /cancelled/);
  await assert.rejects(read(), /still pending/);
  assert.equal(calls, 1);
  reject(new Error("late native rejection"));
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(await read(), "fresh");
  await assert.rejects(read(caller.signal), /cancelled/);
  assert.equal(calls, 2);
});

test("cancelling one native reader also retires the observation shared with another", async () => {
  const caller = new AbortController();
  let calls = 0;
  let release: (value: string) => void = () => {};
  const read = boundedSingleFlightRead(() => {
    calls += 1;
    return calls === 1
      ? new Promise<string>((resolve) => { release = resolve; })
      : Promise.resolve("fresh");
  });
  const first = read(caller.signal);
  const second = read();
  await Promise.resolve();
  caller.abort();
  await assert.rejects(first, /cancelled/);
  release("retired ready status");
  await assert.rejects(second, /superseded/);
  assert.equal(calls, 1);
  assert.equal(await read(), "fresh");
  assert.equal(calls, 2);
});

test("native read cancellation before scheduled entry avoids starting the operation", async () => {
  const caller = new AbortController();
  let calls = 0;
  const read = boundedSingleFlightRead(async () => { calls += 1; return "fresh"; });
  const pending = read(caller.signal);
  caller.abort();
  await assert.rejects(pending, /cancelled/);
  assert.equal(calls, 0);
  assert.equal(await read(), "fresh");
  assert.equal(calls, 1);
});

test("synchronous native read failures release the slot for a later observation", async () => {
  let calls = 0;
  const read = boundedSingleFlightRead(() => {
    calls += 1;
    if (calls === 1) throw new Error("native bridge unavailable");
    return Promise.resolve("fresh");
  });
  await assert.rejects(read(), /native bridge unavailable/);
  assert.equal(await read(), "fresh");
  assert.equal(calls, 2);
});

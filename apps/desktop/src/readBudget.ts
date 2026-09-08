/** Bound the complete read, including authentication and response-body parsing. */
export async function boundedRead<T>(
  read: (signal: AbortSignal) => Promise<T>,
  parentSignal?: AbortSignal | null,
  timeoutMs = 15_000,
): Promise<T> {
  if (parentSignal?.aborted) throw new Error("Local state read cancelled.");
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancel: () => void = () => {};
  const deadline = new Promise<never>((_resolve, reject) => {
    cancel = () => {
      reject(new Error("Local state read cancelled."));
      controller.abort();
    };
    timer = setTimeout(() => {
      reject(new Error("Local state read timed out. The bridge may be busy or unavailable."));
      controller.abort();
    }, timeoutMs);
    parentSignal?.addEventListener("abort", cancel, { once: true });
  });
  try {
    return await Promise.race([read(controller.signal), deadline]);
  } finally {
    clearTimeout(timer);
    parentSignal?.removeEventListener("abort", cancel);
  }
}

/** Bound read fanout and the whole batch, preserving unavailable entries and order. */
export async function boundedReadBatch<Input, Output>(
  items: readonly Input[],
  read: (item: Input, signal: AbortSignal) => Promise<Output>,
  parentSignal?: AbortSignal | null,
  timeoutMs = 15_000,
): Promise<PromiseSettledResult<Output>[]> {
  const results: (PromiseSettledResult<Output> | undefined)[] = new Array(items.length);
  let cursor = 0;
  let stopped = false;
  let failure: unknown = new Error("Local state was not read.");
  try {
    await boundedRead(async (signal) => {
      await Promise.all(Array.from({ length: Math.min(4, items.length) }, async () => {
        while (!stopped && !signal.aborted) {
          const index = cursor++;
          if (index >= items.length) return;
          try {
            const value = await read(items[index], signal);
            if (!stopped && !signal.aborted) results[index] = { status: "fulfilled", value };
          } catch (reason) {
            if (!stopped && !signal.aborted) results[index] = { status: "rejected", reason };
          }
        }
      }));
    }, parentSignal, timeoutMs);
  } catch (error) {
    failure = error;
  } finally {
    stopped = true;
  }
  // Copy rather than returning the working array: late uncooperative reads must
  // not mutate a published result or release another queued request.
  return Array.from(results, (result) => result ?? { status: "rejected", reason: failure });
}

type Schedule = (callback: () => void, delayMs: number) => () => void;
const scheduleTimer: Schedule = (callback, delayMs) => {
  const timer = setTimeout(callback, delayMs);
  return () => clearTimeout(timer);
};

/** Bound a non-cancellable read without multiplying its underlying native work. */
export function boundedSingleFlightRead<T>(
  read: () => Promise<T>,
  timeoutMs = 5_000,
): (parentSignal?: AbortSignal) => Promise<T> {
  type Pending = { promise: Promise<T>; invalidated: boolean };
  let active: Pending | null = null;
  return (parentSignal) => boundedRead(async (signal) => {
    if (active?.invalidated) throw new Error("Prior local state read is still pending.");
    if (!active) {
      const pending: Pending = {
        invalidated: false,
        promise: Promise.resolve().then(() => {
          if (pending.invalidated) throw new Error("Local state read cancelled before start.");
          return read();
        }),
      };
      active = pending;
      const release = () => { if (active === pending) active = null; };
      // Reap success and rejection even after all callers have stopped waiting.
      void pending.promise.then(release, release);
    }
    const pending = active;
    const invalidate = () => { pending.invalidated = true; };
    signal.addEventListener("abort", invalidate, { once: true });
    try {
      const value = await pending.promise;
      if (pending.invalidated) throw new Error("Local state read was superseded.");
      return value;
    } finally {
      signal.removeEventListener("abort", invalidate);
    }
  }, parentSignal, timeoutMs);
}

/** Share a pending background read, without caching a completed observation. */
export function coalesceBackgroundRead<T>(read: () => Promise<T>): () => Promise<T> {
  let active: Promise<T> | null = null;
  return () => {
    if (!active) {
      const pending = Promise.resolve().then(read).finally(() => {
        if (active === pending) active = null;
      });
      active = pending;
    }
    return active;
  };
}

/** A slow refresh never accumulates interval-triggered copies of itself. */
export function startSerialPolling(
  refresh: (signal: AbortSignal) => Promise<unknown>,
  intervalMs: number,
  schedule: Schedule = scheduleTimer,
): () => void {
  let stopped = false;
  const controller = new AbortController();
  let cancelTimer: (() => void) | undefined;
  const run = async () => {
    if (stopped) return;
    try {
      await refresh(controller.signal);
    } catch {
      // Refresh owns its canonical failure state; polling must survive failure.
    } finally {
      if (!stopped) cancelTimer = schedule(() => void run(), intervalMs);
    }
  };
  void run();
  return () => {
    stopped = true;
    controller.abort();
    cancelTimer?.();
  };
}

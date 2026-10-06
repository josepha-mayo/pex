import { useEffect, useRef, useState } from "react";
import type { SharedRequest } from "../sharedConnection";
import { advanceTaskAttemptOutcome, readOperatorTaskReceipt, sendOperatorTask,
  type TaskAttemptOutcome, type TaskBinding } from "../operatorTask";

type Outcome = TaskAttemptOutcome;
const outcomes = new Map<string, Outcome>();
const listeners = new Map<string, Set<(value: Outcome | null) => void>>();

function storageKey(bindingKey: string) {
  return `pex.operator-task-attempt.v1.${encodeURIComponent(bindingKey)}`;
}

function storedOutcome(bindingKey: string): Outcome | null {
  try {
    const raw = window.sessionStorage.getItem(storageKey(bindingKey));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const item = value as Record<string, unknown>;
    if (typeof item.idempotencyKey !== "string"
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(item.idempotencyKey)
      || !["delivered", "uncertain", "in_progress"].includes(String(item.kind))) return null;
    return {
      kind: item.kind as Outcome["kind"],
      idempotencyKey: item.idempotencyKey,
      message: "Checking the previous task receipt…",
    };
  } catch { return null; }
}

function setBindingOutcome(key: string, value: Outcome | null) {
  if (value) {
    const current = outcomes.get(key) || null;
    value = advanceTaskAttemptOutcome(current, value);
    outcomes.set(key, value);
  }
  else outcomes.delete(key);
  try {
    if (value) window.sessionStorage.setItem(storageKey(key), JSON.stringify({
      idempotencyKey: value.idempotencyKey, kind: value.kind,
    }));
    else window.sessionStorage.removeItem(storageKey(key));
  } catch { /* In-memory state still prevents duplicate clicks in this app instance. */ }
  for (const listener of listeners.get(key) || []) listener(value);
}

export function OperatorTaskComposer({ request, binding, available, initialDraft, onDelivered, onInspect }: {
  request: SharedRequest;
  binding: TaskBinding;
  available: boolean;
  initialDraft?: { nonce: number; text: string };
  onDelivered: () => void;
  onInspect: () => void;
}) {
  const bindingKey = `${binding.sessionId}\0${binding.goalId}\0${binding.projectId}`;
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(() => outcomes.get(bindingKey) || storedOutcome(bindingKey));
  const pending = useRef<AbortController | null>(null);
  const checkingRef = useRef(false);
  const appliedDraftNonce = useRef(0);

  useEffect(() => {
    // A prefilled draft (e.g. a recorded ruling forwarded from Decisions) only
    // fills an untouched, unblocked composer — never overwrites an in-flight
    // attempt or an existing receipt state.
    if (
      initialDraft
      && initialDraft.nonce !== appliedDraftNonce.current
      && !outcome
      && !pending.current
    ) {
      appliedDraftNonce.current = initialDraft.nonce;
      setText(initialDraft.text);
    }
  }, [initialDraft, outcome]);

  async function checkReceipt(idempotencyKey: string) {
    if (checkingRef.current) return;
    checkingRef.current = true;
    setChecking(true);
    try {
      const receipt = await readOperatorTaskReceipt(request, binding, idempotencyKey);
      if (outcomes.get(bindingKey)?.idempotencyKey !== idempotencyKey) return;
      if (receipt?.status === "delivered") {
        setBindingOutcome(bindingKey, {
          kind: "delivered", idempotencyKey,
          message: `Task delivered to this worker. Receipt ${receipt.effectId}.`,
        });
        try { onDelivered(); } catch { /* The durable receipt stays authoritative. */ }
      } else if (receipt?.status === "reserved" || receipt?.status === "dispatching") {
        setBindingOutcome(bindingKey, {
          kind: "in_progress", idempotencyKey,
          message: receipt.status === "reserved"
            ? "The bridge reserved this task, but delivery has not started or been confirmed. It may be stranded after a restart; inspect the worker before a new task."
            : "The bridge started dispatching this task, but delivery is not confirmed. Check the receipt and inspect the worker before a new task.",
        });
      } else {
        setBindingOutcome(bindingKey, {
          kind: "uncertain", idempotencyKey,
          message: receipt
            ? `The bridge recorded ${receipt.status}. Inspect the worker before a new task.`
            : "No durable receipt was found yet. The original request may still arrive; inspect the worker before a new task.",
        });
      }
    } catch {
      if (outcomes.get(bindingKey)?.idempotencyKey === idempotencyKey) {
        setBindingOutcome(bindingKey, {
          kind: "uncertain", idempotencyKey,
          message: "The previous task receipt could not be checked. Inspect the worker before a new task.",
        });
      }
    } finally {
      checkingRef.current = false;
      setChecking(false);
    }
  }

  useEffect(() => {
    const listener = (value: Outcome | null) => setOutcome(value);
    const subscribers = listeners.get(bindingKey) || new Set();
    subscribers.add(listener);
    listeners.set(bindingKey, subscribers);
    const saved = outcomes.get(bindingKey) || storedOutcome(bindingKey);
    if (saved && !outcomes.has(bindingKey)) outcomes.set(bindingKey, saved);
    setOutcome(saved || null);
    if (saved) void checkReceipt(saved.idempotencyKey);
    return () => {
      subscribers.delete(listener);
      if (!subscribers.size) listeners.delete(bindingKey);
      pending.current?.abort();
    };
  }, [bindingKey]);

  async function submit() {
    if (!available || busy || pending.current || outcome || !text.trim()) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    const idempotencyKey = crypto.randomUUID();
    setBindingOutcome(bindingKey, { kind: "in_progress", idempotencyKey, message: "Task delivery is in progress. Wait for its receipt before sending again." });
    const timer = setTimeout(() => controller.abort(), 60_000);
    try {
      const effectId = await sendOperatorTask(request, binding, text, idempotencyKey, controller.signal);
      const delivered = { kind: "delivered", idempotencyKey, message: `Task delivered to this worker. Receipt ${effectId}.` } as const;
      setBindingOutcome(bindingKey, delivered);
      setText("");
      try { onDelivered(); } catch { /* The delivery receipt remains authoritative. */ }
    } catch {
      const uncertain = { kind: "uncertain", idempotencyKey, message: "Delivery could not be confirmed. Check the durable receipt and inspect this worker before another task; PEX will not retry automatically." } as const;
      if (outcomes.get(bindingKey)?.idempotencyKey === idempotencyKey) {
        setBindingOutcome(bindingKey, uncertain);
      }
    } finally {
      clearTimeout(timer);
      if (pending.current === controller) pending.current = null;
      setBusy(false);
    }
  }

  return <details className="workspace-task">
    <summary>Send a task to this worker</summary>
    <p>This starts a worker model turn and may use your provider allowance. The attached goal stays in force.</p>
    {!outcome ? <>
      <label htmlFor="operator-task-draft">Task for this worker</label>
      <textarea id="operator-task-draft" value={text} onChange={(event) => setText(event.target.value)}
        placeholder="Describe the next concrete piece of work…" rows={4} maxLength={65_536}
        disabled={!available || busy} />
      <button type="button" className="solid" disabled={!available || busy || !text.trim()}
        onClick={() => void submit()}>{busy ? "Sending…" : "Send task"}</button>
    </> : <>
      <p role="status" aria-live="polite">{outcome.message}</p>
      {outcome.kind !== "delivered" ? <button type="button" className="ghost"
        disabled={checking || busy} onClick={() => void checkReceipt(outcome.idempotencyKey)}>
        {checking ? "Checking receipt…" : "Check delivery receipt"}
      </button> : null}
      {outcome.kind === "delivered" ? <button type="button" className="ghost"
        onClick={() => { setBindingOutcome(bindingKey, null); setText(""); }}>
        Write another task
      </button> : null}
      {outcome.kind !== "delivered" ? <div className="workspace-task-recovery">
        <button type="button" className="ghost" onClick={onInspect}>Inspect worker activity</button>
        <button type="button" className="text-button" disabled={checking || busy} onClick={() => {
          setBindingOutcome(bindingKey, null);
          setText("");
        }}>I checked the worker; write a new task</button>
        <small>A new task is a new delivery attempt. If the first task arrived, it may run twice.</small>
      </div> : null}
    </>}
  </details>;
}

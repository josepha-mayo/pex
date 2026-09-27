import { useEffect, useRef, useState } from "react";
import type { SharedRequest } from "../sharedConnection";
import { sendOperatorTask } from "../operatorTask";

type Binding = { sessionId: string; goalId: string; projectId: string };
type Outcome = { kind: "delivered" | "uncertain" | "in_progress"; message: string };
const outcomes = new Map<string, Outcome>();
const listeners = new Map<string, Set<(value: Outcome | null) => void>>();

function setBindingOutcome(key: string, value: Outcome | null) {
  if (value) outcomes.set(key, value);
  else outcomes.delete(key);
  for (const listener of listeners.get(key) || []) listener(value);
}

export function OperatorTaskComposer({ request, binding, available, onDelivered, onInspect }: {
  request: SharedRequest;
  binding: Binding;
  available: boolean;
  onDelivered: () => void;
  onInspect: () => void;
}) {
  const bindingKey = `${binding.sessionId}\0${binding.goalId}`;
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(() => outcomes.get(bindingKey) || null);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    const listener = (value: Outcome | null) => setOutcome(value);
    const subscribers = listeners.get(bindingKey) || new Set();
    subscribers.add(listener);
    listeners.set(bindingKey, subscribers);
    setOutcome(outcomes.get(bindingKey) || null);
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
    setBindingOutcome(bindingKey, { kind: "in_progress", message: "Task delivery is in progress. Wait for its receipt before sending again." });
    const timer = setTimeout(() => controller.abort(), 60_000);
    try {
      const effectId = await sendOperatorTask(request, binding, text, idempotencyKey, controller.signal);
      const delivered = { kind: "delivered", message: `Task delivered to this worker. Receipt ${effectId}.` } as const;
      setBindingOutcome(bindingKey, delivered);
      setText("");
      try { onDelivered(); } catch { /* The delivery receipt remains authoritative. */ }
    } catch {
      const uncertain = { kind: "uncertain", message: "Delivery could not be confirmed. Inspect this worker and its latest activity before sending another task; PEX will not retry automatically." } as const;
      setBindingOutcome(bindingKey, uncertain);
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
      {outcome.kind === "delivered" ? <button type="button" className="ghost"
        onClick={() => { setBindingOutcome(bindingKey, null); setText(""); }}>
        Write another task
      </button> : null}
      {outcome.kind === "uncertain" ? <div className="workspace-task-recovery">
        <button type="button" className="ghost" onClick={onInspect}>Inspect worker activity</button>
        <button type="button" className="text-button" onClick={() => {
          setBindingOutcome(bindingKey, null);
          setText("");
        }}>I checked the worker; write a new task</button>
        <small>A new task is a new delivery attempt. If the first task arrived, it may run twice.</small>
      </div> : null}
    </>}
  </details>;
}

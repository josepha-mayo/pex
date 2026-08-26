import { FormEvent, KeyboardEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { CodexSprite, lookIndex, type PetMood } from "./pets/atlas";

const BRIDGE = "http://127.0.0.1:7420";
const TAURI = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

type SessionRow = {
  id: string;
  harness_type: string;
  status: string;
  goal_id?: string | null;
  supervision_paused?: boolean;
  last_message?: string | null;
  label?: string;
  activity?: string;
};

type LastAction = {
  id: string;
  session_id: string;
  action: string;
  diagnosis?: string;
  evidence?: string[];
  result?: string;
  reversible?: boolean;
  confidence?: number;
};

type PetSnapshot = {
  headline: string;
  working: number;
  drifting: number;
  blocked?: number;
  needs_you: number;
  last_message?: string | null;
  last_source?: string | null;
  last_action?: LastAction | null;
  mood?: PetMood;
  appearance?: {
    id: string;
    display_name: string;
    spritesheet_url?: string;
    scale?: number;
    source?: string;
  };
  settings?: { custom_name?: string; scale?: number };
  sessions: SessionRow[];
};

type Goal = { id: string; title: string; objective: string };

async function invoke(name: string, args?: Record<string, unknown>) {
  if (!TAURI) return;
  const { invoke: call } = await import("@tauri-apps/api/core");
  await call(name, args);
}

export function App() {
  const [pet, setPet] = useState<PetSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [ask, setAsk] = useState("");
  const [answer, setAnswer] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [asking, setAsking] = useState(false);
  const [hover, setHover] = useState(false);
  const [dragDir, setDragDir] = useState<-1 | 0 | 1>(0);
  const [look, setLook] = useState<number | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [scale, setScale] = useState(1);
  const [nickname, setNickname] = useState("");
  const [importDir, setImportDir] = useState("");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const petBox = useRef<HTMLButtonElement>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const apply = (data: PetSnapshot) => {
      setPet(data);
      setError(null);
    };
    const tick = async () => {
      try {
        const res = await fetch(`${BRIDGE}/v1/pet`);
        if (!res.ok) throw new Error("offline");
        const data = (await res.json()) as PetSnapshot;
        if (!cancelled) apply(data);
      } catch {
        if (!cancelled) setError("Bridge offline");
      }
    };
    void tick();
    const poll = window.setInterval(() => void tick(), 4000);
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = BRIDGE.replace(/^https?:\/\//, "");
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(`${proto}://${host}/v1/events`);
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as { topic?: string; payload?: PetSnapshot };
          if (msg.topic === "pet" && msg.payload && !cancelled) apply(msg.payload);
        } catch {
          /* ignore malformed frames */
        }
      };
    } catch {
      socket = null;
    }
    return () => {
      cancelled = true;
      window.clearInterval(poll);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (!settingsOpen) return;
    void fetch(`${BRIDGE}/v1/goals`)
      .then((r) => r.json())
      .then((rows) => setGoals(Array.isArray(rows) ? rows : []))
      .catch(() => undefined);
  }, [settingsOpen, pet?.sessions.length]);

  useEffect(() => {
    setScale(pet?.settings?.scale ?? pet?.appearance?.scale ?? 1);
    setNickname(pet?.settings?.custom_name ?? "");
  }, [pet?.settings?.custom_name, pet?.settings?.scale, pet?.appearance?.scale]);

  const sessions = pet?.sessions ?? [];
  const current = sessions.find((row) => row.id === selectedId) ?? sessions[0];
  const mood: PetMood = pet?.mood ?? "idle";
  const sheet = pet?.appearance?.spritesheet_url ? `${BRIDGE}${pet.appearance.spritesheet_url}` : "";
  const name = pet?.settings?.custom_name?.trim() || pet?.appearance?.display_name || "Pex";
  const reduced =
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const last = pet?.last_action;
  const tone = error ? "need" : pet?.needs_you ? "need" : pet?.working ? "work" : "";

  const status = useMemo(() => {
    if (error) return { label: "Bridge offline", detail: "Start the bridge with pex-bridge --no-auth." };
    if (pet?.needs_you) return { label: pet.headline || "Needs you", detail: pet.last_message || "A real decision is waiting." };
    if (pet?.working) return { label: pet.headline || `${pet.working} working`, detail: pet.last_message || "Workers are moving." };
    return { label: pet?.headline || "Quiet", detail: pet?.last_message || "Nothing needs babysitting." };
  }, [error, pet]);

  function focusSession(session?: SessionRow) {
    const row = session ?? current;
    if (!row) return;
    void invoke("focus_harness", { harness: row.harness_type });
    void fetch(`${BRIDGE}/v1/sessions/${encodeURIComponent(row.id)}/focus`, { method: "POST" }).catch(
      () => undefined,
    );
  }

  function onPetPointerMove(event: PointerEvent<HTMLButtonElement>) {
    const box = petBox.current?.getBoundingClientRect();
    if (!box) return;
    setLook(lookIndex(event.clientX - (box.left + box.width / 2), event.clientY - (box.top + box.height / 2)));
  }

  function onStagePointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    dragStart.current = { x: event.clientX, y: event.clientY };
    dragged.current = false;
  }

  function onStagePointerMove(event: PointerEvent<HTMLButtonElement>) {
    onPetPointerMove(event);
    const start = dragStart.current;
    if (!start || event.buttons !== 1) return;
    const dx = event.clientX - start.x;
    if (Math.abs(dx) > 6) {
      dragged.current = true;
      setDragDir(dx > 0 ? 1 : -1);
    }
  }

  function onStagePointerUp() {
    const wasDrag = dragged.current;
    dragStart.current = null;
    dragged.current = false;
    setDragDir(0);
    if (!wasDrag) focusSession();
  }

  async function sendToHarness(event?: FormEvent) {
    event?.preventDefault();
    if (!current || !prompt.trim() || sending) return;
    setSending(true);
    setNote(null);
    try {
      const res = await fetch(`${BRIDGE}/v1/sessions/${encodeURIComponent(current.id)}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: prompt }),
      });
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean };
      if (!res.ok || data.ok === false) {
        setNote("The harness did not accept that prompt.");
        return;
      }
      setPrompt("");
      setNote(`Sent to ${titleCase(current.harness_type)}.`);
      focusSession(current);
    } catch {
      setNote("Could not reach the bridge.");
    } finally {
      setSending(false);
    }
  }

  function onPromptKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      void sendToHarness();
    }
  }

  async function askPex(event: FormEvent) {
    event.preventDefault();
    if (!ask.trim() || asking) return;
    setAsking(true);
    try {
      const res = await fetch(`${BRIDGE}/v1/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: ask }),
      });
      const data = await res.json();
      setAnswer(data.answer || "");
    } catch {
      setAnswer("PEX could not reach local state.");
    } finally {
      setAsking(false);
    }
  }

  async function saveAppearance() {
    await fetch(`${BRIDGE}/v1/pets/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ custom_name: nickname, scale }),
    });
  }

  async function importPet() {
    if (!importDir.trim()) return;
    await fetch(`${BRIDGE}/v1/pets/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory: importDir.trim() }),
    });
  }

  async function pauseOrResume(session: SessionRow) {
    const path = session.supervision_paused ? "resume-supervision" : "pause-supervision";
    await fetch(`${BRIDGE}/v1/sessions/${encodeURIComponent(session.id)}/${path}`, { method: "POST" });
  }

  async function undoLast() {
    if (!last?.id || last.reversible === false) return;
    await fetch(`${BRIDGE}/v1/interventions/${encodeURIComponent(last.id)}/undo`, { method: "POST" });
  }

  const canUndo = Boolean(last?.id && last.reversible !== false && last.action && last.action !== "NOOP");

  return (
    <main className="companion">
      <header className="mast">
        <span className="wordmark">PEX</span>
        <span className="mast-status" data-tone={tone}>
          {status.label}
        </span>
      </header>

      <section className="hero">
        <button
          ref={petBox}
          type="button"
          className="pet-hit"
          aria-label={`${name}. Click to open the selected harness.`}
          onPointerEnter={() => setHover(true)}
          onPointerLeave={() => {
            setHover(false);
            setLook(null);
            setDragDir(0);
            dragStart.current = null;
          }}
          onPointerDown={onStagePointerDown}
          onPointerMove={onStagePointerMove}
          onPointerUp={onStagePointerUp}
        >
          <CodexSprite
            src={sheet}
            mood={mood}
            hover={hover}
            dragDir={dragDir}
            look={look}
            scale={scale}
            reducedMotion={reduced}
          />
        </button>
        <div className="hero-copy">
          <h1>{name}</h1>
          <p>{status.detail}</p>
        </div>
        <p className="hint">Hover jumps · click opens the harness · drag runs · looks at the pointer</p>
      </section>

      {last && last.action !== "NOOP" ? (
        <section className="inspect" aria-label="Last PEX action">
          <h2>What PEX did</h2>
          <p>
            {last.action.replaceAll("_", " ")}
            {last.confidence != null ? ` · ${Math.round(last.confidence * 100)}%` : ""}
          </p>
          {last.diagnosis ? <p className="why">{last.diagnosis}</p> : null}
          {evidenceOpen && last.evidence?.length ? (
            <ul className="evidence">
              {last.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          <div className="inspect-actions">
            <button type="button" className="ghost" onClick={() => setEvidenceOpen((open) => !open)}>
              {evidenceOpen ? "Hide evidence" : "Show evidence"}
            </button>
            {canUndo ? (
              <button type="button" className="ghost" onClick={() => void undoLast()}>
                Undo
              </button>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="sessions" aria-label="Harnesses">
        {sessions.length ? (
          sessions.map((session) => (
            <div className={`session ${session.id === current?.id ? "current" : ""}`} key={session.id}>
              <button type="button" className="session-main" onClick={() => setSelectedId(session.id)}>
                <strong>{session.label || titleCase(session.harness_type)}</strong>
                <small>
                  {titleCase(session.harness_type)} · {session.activity || humanize(session.status)}
                </small>
              </button>
              <button type="button" className="ghost" onClick={() => focusSession(session)}>
                Open
              </button>
              <button type="button" className="ghost" onClick={() => void pauseOrResume(session)}>
                {session.supervision_paused ? "Resume" : "Pause"}
              </button>
            </div>
          ))
        ) : (
          <p className="empty">Start Cursor or Codex normally. PEX attaches above them, then you can prompt from here.</p>
        )}
      </section>

      <form className="dock" onSubmit={sendToHarness}>
        <label htmlFor="harness-prompt">
          Prompt {current ? titleCase(current.harness_type) : "a harness"}
        </label>
        <div className="compose-row">
          <textarea
            id="harness-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={onPromptKey}
            placeholder={
              current
                ? `Continue ${titleCase(current.harness_type)}… Ctrl+Enter to send`
                : "No live session yet"
            }
            disabled={!current}
          />
          <div className="compose-actions">
            <button type="submit" className="solid" disabled={!current || sending}>
              {sending ? "Sending" : "Send"}
            </button>
          </div>
        </div>
        {note ? <p className={`note ${note.startsWith("Sent") ? "ok" : ""}`}>{note}</p> : null}
      </form>

      <form className="ask" onSubmit={askPex}>
        <label htmlFor="pex-ask">Ask PEX without interrupting the worker</label>
        <div className="row">
          <input
            id="pex-ask"
            value={ask}
            onChange={(event) => setAsk(event.target.value)}
            placeholder="What needs me?"
          />
          <button type="submit" className="ghost" disabled={asking}>
            {asking ? "Checking" : "Ask"}
          </button>
        </div>
        {answer ? <output>{answer}</output> : null}
      </form>

      <details className="settings" open={settingsOpen} onToggle={(event) => setSettingsOpen(event.currentTarget.open)}>
        <summary>Settings</summary>
        <label>
          Nickname
          <input value={nickname} onChange={(event) => setNickname(event.target.value)} />
        </label>
        <label>
          Pet scale · {scale.toFixed(2)}
          <input
            type="range"
            min={0.8}
            max={1.4}
            step={0.05}
            value={scale}
            onChange={(event) => setScale(Number(event.target.value))}
          />
        </label>
        <button type="button" className="solid" onClick={() => void saveAppearance()}>
          Save appearance
        </button>
        <label>
          Codex v2 pet folder
          <input
            value={importDir}
            placeholder="Folder with pet.json and spritesheet.webp"
            onChange={(event) => setImportDir(event.target.value)}
          />
        </label>
        <button type="button" className="ghost" onClick={() => void importPet()}>
          Import hatch-pet
        </button>
        {goals.length ? (
          <ul className="goals">
            {goals.map((goal) => (
              <li key={goal.id}>
                <strong>{goal.title}</strong>
                <small>{goal.objective}</small>
              </li>
            ))}
          </ul>
        ) : null}
      </details>
    </main>
  );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replaceAll(":", " · ").trim().toLowerCase();
}

function titleCase(value: string): string {
  return humanize(value).replace(/\b\w/g, (letter) => letter.toUpperCase());
}

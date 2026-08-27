import { FormEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { CodexSprite, lookIndex, type PetMood } from "./pets/atlas";
import { releasePetOverlay, startPetDrag } from "./releasePet";

const BRIDGE = "http://127.0.0.1:7420";
const TAURI = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const HOP_DWELL_MS = 800;
const HOP_PLAY_MS = 2460;

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
    atlas_ready?: boolean;
    species?: string;
  };
  settings?: { custom_name?: string; scale?: number };
  sessions: SessionRow[];
};

type Goal = { id: string; title: string; objective: string };

type CatalogPet = {
  id: string;
  display_name: string;
  description: string;
  species?: string;
  atlas_ready?: boolean;
};

type HatchJobRow = {
  id: string;
  display_name: string;
  status: string;
  step: string;
  jobs_complete: number;
  jobs_total: number;
  error?: string | null;
};

type HatchCap = {
  ok?: boolean;
  has_image_endpoint?: boolean;
  provider?: string;
  reason?: string;
  note?: string;
};

type SupervisorRow = { provider: string; model_id: string; label: string };

type SupervisorInfo = {
  backend?: string | null;
  model_id?: string | null;
  has_api_key?: boolean;
  login_note?: string;
  catalog?: SupervisorRow[];
  note?: string;
  model_loaded?: boolean;
  error?: string;
};

async function invoke(name: string, args?: Record<string, unknown>) {
  if (!TAURI) return;
  const { invoke: call } = await import("@tauri-apps/api/core");
  await call(name, args);
}

export function App() {
  const [pet, setPet] = useState<PetSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ask, setAsk] = useState("");
  const [answer, setAnswer] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [hop, setHop] = useState(false);
  const [dragDir, setDragDir] = useState<-1 | 0 | 1>(0);
  const [look, setLook] = useState<number | null>(null);
  const [shell, setShell] = useState<"home" | "settings" | "pet">(() => {
    const hash = window.location.hash.replace(/^#\/?/, "");
    if (hash === "settings" || hash === "pet") return hash;
    return "home";
  });
  const [goals, setGoals] = useState<Goal[]>([]);
  const [scale, setScale] = useState(1);
  const [nickname, setNickname] = useState("");
  const [importDir, setImportDir] = useState("");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [roster, setRoster] = useState<CatalogPet[]>([]);
  const [hatchCap, setHatchCap] = useState<HatchCap | null>(null);
  const [hatchJobs, setHatchJobs] = useState<HatchJobRow[]>([]);
  const [hatchName, setHatchName] = useState("");
  const [hatchNotes, setHatchNotes] = useState("");
  const [hatchStyle, setHatchStyle] = useState("plush");
  const [hatching, setHatching] = useState(false);
  const [supervisor, setSupervisor] = useState<SupervisorInfo | null>(null);
  const [supervisorProvider, setSupervisorProvider] = useState("");
  const [supervisorModel, setSupervisorModel] = useState("");
  const [savingSupervisor, setSavingSupervisor] = useState(false);
  const petBox = useRef<HTMLButtonElement>(null);
  const askBox = useRef<HTMLInputElement>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);
  const hopDwell = useRef<number | null>(null);
  const hopPlay = useRef<number | null>(null);
  const lookDebounce = useRef<number | null>(null);

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
    void fetch(`${BRIDGE}/v1/goals`)
      .then((r) => r.json())
      .then((rows) => setGoals(Array.isArray(rows) ? rows : []))
      .catch(() => undefined);
    const loadPets = async () => {
      try {
        const [petsRes, hatchRes, capRes] = await Promise.all([
          fetch(`${BRIDGE}/v1/pets`),
          fetch(`${BRIDGE}/v1/pets/hatch`),
          fetch(`${BRIDGE}/v1/pets/hatch/capability`),
        ]);
        if (petsRes.ok) {
          const data = await petsRes.json();
          setRoster((data.catalog || data.starters || []) as CatalogPet[]);
        }
        if (hatchRes.ok) {
          const data = await hatchRes.json();
          setHatchJobs((data.jobs || []) as HatchJobRow[]);
        }
        if (capRes.ok) setHatchCap((await capRes.json()) as HatchCap);
      } catch {
        /* bridge may be mid-restart */
      }
    };
    void loadPets();
    const poll = window.setInterval(() => void loadPets(), 8000);
    return () => window.clearInterval(poll);
  }, [pet?.sessions.length]);

  useEffect(() => {
    if (shell !== "settings") return;
    let cancelled = false;
    void fetch(`${BRIDGE}/v1/supervisor`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: SupervisorInfo | null) => {
        if (cancelled || !data) return;
        setSupervisor(data);
        setSupervisorProvider(data.backend || "");
        setSupervisorModel(data.model_id || "");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [shell]);

  useEffect(() => {
    const fromHash = () => {
      const hash = window.location.hash.replace(/^#\/?/, "");
      if (hash === "settings" || hash === "pet") setShell(hash);
      else setShell("home");
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    if (TAURI) {
      void import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
        if (getCurrentWindow().label === "pet") setShell("pet");
      });
    }
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("pet-shell", shell === "pet");
    document.body.classList.toggle("pet-shell", shell === "pet");
    if (!TAURI || shell !== "pet") return;
    void import("@tauri-apps/api/webview")
      .then(({ getCurrentWebview }) =>
        getCurrentWebview().setBackgroundColor({ red: 0, green: 0, blue: 0, alpha: 0 }),
      )
      .catch(() => undefined);
  }, [shell]);

  useEffect(() => {
    if (!TAURI || !pet?.appearance?.id) return;
    void releasePetOverlay();
  }, [pet?.appearance?.id]);

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

  function clearHopTimers() {
    if (hopDwell.current != null) window.clearTimeout(hopDwell.current);
    if (hopPlay.current != null) window.clearTimeout(hopPlay.current);
    hopDwell.current = null;
    hopPlay.current = null;
  }

  function onPetEnter() {
    clearHopTimers();
    hopDwell.current = window.setTimeout(() => {
      setHop(true);
      hopPlay.current = window.setTimeout(() => setHop(false), HOP_PLAY_MS);
    }, HOP_DWELL_MS);
  }

  function onPetLeave() {
    clearHopTimers();
    setHop(false);
    setLook(null);
    setDragDir(0);
    dragStart.current = null;
  }

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
    const next = lookIndex(event.clientX - (box.left + box.width / 2), event.clientY - (box.top + box.height / 2));
    if (lookDebounce.current != null) window.clearTimeout(lookDebounce.current);
    lookDebounce.current = window.setTimeout(() => setLook(next), 90);
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
      if (shell === "pet") void startPetDrag();
    }
  }

  function onStagePointerUp() {
    const wasDrag = dragged.current;
    dragStart.current = null;
    dragged.current = false;
    setDragDir(0);
    if (!wasDrag) void askPex(undefined, ask.trim() || "what needs me?");
  }

  async function askPex(event?: FormEvent, question?: string) {
    event?.preventDefault();
    const q = (question ?? ask).trim();
    if (!q || asking) return;
    setAsking(true);
    setEvidenceOpen(true);
    try {
      const res = await fetch(`${BRIDGE}/v1/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      setAnswer(data.answer || "");
      if (!ask.trim()) setAsk(q);
    } catch {
      setAnswer("PEX could not reach local state.");
    } finally {
      setAsking(false);
      askBox.current?.focus();
    }
  }

  async function saveAppearance() {
    await fetch(`${BRIDGE}/v1/pets/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ custom_name: nickname, scale }),
    });
  }

  async function saveSupervisor() {
    if (savingSupervisor) return;
    setSavingSupervisor(true);
    try {
      const res = await fetch(`${BRIDGE}/v1/supervisor`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: supervisorProvider.trim() || undefined,
          model_id: supervisorModel.trim() || undefined,
        }),
      });
      const data = (await res.json()) as SupervisorInfo & { detail?: string };
      if (!res.ok) {
        setNote(typeof data.detail === "string" ? data.detail : "Could not save supervisor.");
        return;
      }
      setSupervisor(data);
      setSupervisorProvider(data.backend || supervisorProvider);
      setSupervisorModel(data.model_id || supervisorModel);
      setNote(
        data.model_loaded
          ? `PEX supervisor is ${data.backend || "set"} / ${data.model_id || "default"}.`
          : "Choice saved. Keys stay in .env — PEX will stay on deterministic triage until a key is present.",
      );
    } catch {
      setNote("Could not reach the supervisor endpoint.");
    } finally {
      setSavingSupervisor(false);
    }
  }

  async function selectPet(id: string) {
    await fetch(`${BRIDGE}/v1/pets/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_id: id }),
    });
    try {
      const res = await fetch(`${BRIDGE}/v1/pet`);
      if (res.ok) setPet((await res.json()) as PetSnapshot);
    } catch {
      /* poll will catch up */
    }
    await releasePetOverlay();
    askBox.current?.focus();
  }

  async function hatchOwnPet() {
    if (!hatchName.trim() || hatching) return;
    setHatching(true);
    setNote(null);
    try {
      const res = await fetch(`${BRIDGE}/v1/pets/hatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: hatchName.trim(),
          description: hatchNotes.trim(),
          pet_notes: hatchNotes.trim(),
          style_preset: hatchStyle,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as HatchJobRow & { detail?: string; error?: string };
      if (!res.ok) {
        setNote(typeof data.detail === "string" ? data.detail : "Hatch did not start.");
        return;
      }
      setHatchJobs((rows) => [data, ...rows.filter((row) => row.id !== data.id)]);
      setHatchName("");
      if (data.error) setNote(data.error);
      else setNote(`Hatching ${data.display_name} with the PEX image provider.`);
    } catch {
      setNote("Could not reach the hatch endpoint.");
    } finally {
      setHatching(false);
    }
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

  async function attachGoal(sessionId: string, goalId: string) {
    await fetch(`${BRIDGE}/v1/sessions/${encodeURIComponent(sessionId)}/attach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal_id: goalId }),
    });
  }

  async function undoLast() {
    if (!last?.id || last.reversible === false) return;
    await fetch(`${BRIDGE}/v1/interventions/${encodeURIComponent(last.id)}/undo`, { method: "POST" });
  }

  const canUndo = Boolean(last?.id && last.reversible !== false && last.action && last.action !== "NOOP");
  const petOnDesktop = TAURI && shell !== "pet";

  const sprite = (
    <button
      ref={petBox}
      type="button"
      className="pet-hit"
      aria-label={`${name}. Click to ask PEX.`}
      onPointerEnter={onPetEnter}
      onPointerLeave={onPetLeave}
      onPointerDown={onStagePointerDown}
      onPointerMove={onStagePointerMove}
      onPointerUp={onStagePointerUp}
    >
      <CodexSprite
        src={sheet}
        mood={mood}
        hop={hop}
        dragDir={dragDir}
        look={look}
        scale={shell === "pet" ? Math.max(scale, 1.05) : scale}
        reducedMotion={reduced}
      />
    </button>
  );

  if (shell === "pet") {
    return (
      <main className="pet-desktop">
        {sprite}
        {answer ? <output className="pet-bubble">{answer}</output> : null}
      </main>
    );
  }

  if (shell === "settings") {
    return (
      <main className="companion page-settings">
        <header className="mast">
          <button type="button" className="ghost mast-back" onClick={() => { window.location.hash = ""; }}>
            Back
          </button>
          <span className="wordmark">PEX</span>
          <span className="mast-status">Settings</span>
        </header>
        <div className="settings-page">
          <section className="settings-card">
            <h2>Appearance</h2>
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
          </section>
          <section className="settings-card">
            <h2>PEX supervisor model</h2>
            <p className="hatch-cap">
              {supervisor?.login_note ||
                "This is PEX’s brain, not the worker harness. Keys stay in .env. Paste any model id."}
            </p>
            <label>
              Provider
              <select
                value={supervisorProvider}
                onChange={(event) => {
                  const next = event.target.value;
                  setSupervisorProvider(next);
                  const first = (supervisor?.catalog || []).find((row) => row.provider === next);
                  if (first) setSupervisorModel(first.model_id);
                }}
              >
                <option value="">auto-detect</option>
                {[...new Set((supervisor?.catalog || []).map((row) => row.provider))].map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Catalog
              <select
                value={(supervisor?.catalog || []).some((row) => row.model_id === supervisorModel) ? supervisorModel : ""}
                onChange={(event) => setSupervisorModel(event.target.value)}
              >
                <option value="">paste any model id below</option>
                {(supervisor?.catalog || [])
                  .filter((row) => !supervisorProvider || row.provider === supervisorProvider)
                  .map((row) => (
                    <option key={`${row.provider}:${row.model_id}:${row.label}`} value={row.model_id}>
                      {row.label} · {row.model_id}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Model id
              <input
                value={supervisorModel}
                onChange={(event) => setSupervisorModel(event.target.value)}
                placeholder="gpt-5.6-sol or any vendor id"
              />
            </label>
            <button type="button" className="solid" disabled={savingSupervisor} onClick={() => void saveSupervisor()}>
              {savingSupervisor ? "Saving…" : "Save supervisor"}
            </button>
          </section>
          <section className="settings-card">
            <h2>Hatch your own</h2>
            <p className="hatch-cap">
              {hatchCap?.has_image_endpoint
                ? `Uses ${hatchCap.provider || "your PEX"} image endpoint, same credentials as inspect.`
                : hatchCap?.reason ||
                  "Needs an image model. Text-only Zen chat will fail honestly. Set PEX_HATCH_BASE_URL or OPENAI_API_KEY."}
            </p>
            <label>
              Pet name
              <input value={hatchName} onChange={(event) => setHatchName(event.target.value)} placeholder="Nori" />
            </label>
            <label>
              Look
              <input
                value={hatchNotes}
                onChange={(event) => setHatchNotes(event.target.value)}
                placeholder="Plush fox, ink-navy, cream belly, no laptop"
              />
            </label>
            <label>
              Style
              <select value={hatchStyle} onChange={(event) => setHatchStyle(event.target.value)}>
                <option value="plush">plush</option>
                <option value="clay">clay</option>
                <option value="sticker">sticker</option>
                <option value="flat-vector">flat-vector</option>
                <option value="3d-toy">3d-toy</option>
                <option value="auto">auto</option>
              </select>
            </label>
            <button type="button" className="solid" disabled={!hatchName.trim() || hatching} onClick={() => void hatchOwnPet()}>
              {hatching ? "Starting…" : "Hatch"}
            </button>
            {hatchJobs.length ? (
              <ul className="hatch-jobs">
                {hatchJobs.slice(0, 4).map((job) => (
                  <li key={job.id}>
                    <strong>{job.display_name}</strong>
                    <small>
                      {job.status} · {job.jobs_complete}/{job.jobs_total} · {job.error || job.step}
                    </small>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
          <section className="settings-card">
            <h2>Import</h2>
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
          </section>
          {goals.length ? (
            <section className="settings-card">
              <h2>Goals</h2>
              <ul className="goals">
                {goals.map((goal) => (
                  <li key={goal.id}>
                    <strong>{goal.title}</strong>
                    <small>{goal.objective}</small>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {note ? <p className={`note ${note.startsWith("Hatching") ? "ok" : ""}`}>{note}</p> : null}
        </div>
      </main>
    );
  }

  return (
    <main className="companion">
      <header className="mast">
        <span className="wordmark">PEX</span>
        <span className="mast-status" data-tone={tone}>
          {status.label}
        </span>
        <button type="button" className="ghost mast-settings" onClick={() => { window.location.hash = "settings"; }}>
          Settings
        </button>
      </header>

      <section className={`hero ${petOnDesktop ? "away" : ""}`}>
        {petOnDesktop ? null : sprite}
        <div className="hero-copy">
          {petOnDesktop ? <p className="out-tag">{name} is on the desktop</p> : null}
          <h1>{name}</h1>
          <p>{status.detail}</p>
        </div>
        <p className="hint">
          {petOnDesktop
            ? "Select a pet to send it onto the desktop · click the overlay to ask PEX"
            : "Looks at the pointer · hops after you linger · click asks PEX"}
        </p>
      </section>

      <section className="roster-strip" aria-label="PEX pets">
        {roster.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`roster-pet ${item.id === pet?.appearance?.id ? "current" : ""}`}
            onClick={() => void selectPet(item.id)}
          >
            <CodexSprite
              src={`${BRIDGE}/v1/pets/${item.id}/spritesheet`}
              mood="idle"
              scale={0.48}
              reducedMotion={reduced}
            />
            <strong>{item.display_name}</strong>
            <small>
              {item.species || "mascot"}
              {item.atlas_ready ? "" : " · hatching"}
            </small>
          </button>
        ))}
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

      <section className="sessions" aria-label="Reviewed workers">
        {sessions.length ? (
          sessions.map((session) => (
            <div className={`session ${session.id === current?.id ? "current" : ""}`} key={session.id}>
              <button type="button" className="session-main" onClick={() => setSelectedId(session.id)}>
                <strong>{session.label || titleCase(session.harness_type)}</strong>
                <small>
                  {titleCase(session.harness_type)} · {session.activity || humanize(session.status)}
                  {session.goal_id ? "" : " · no goal"}
                </small>
              </button>
              {goals.length ? (
                <select
                  aria-label={`Attach goal for ${session.label || session.harness_type}`}
                  value={session.goal_id || ""}
                  onChange={(event) => {
                    const goalId = event.target.value;
                    if (goalId) void attachGoal(session.id, goalId);
                  }}
                >
                  <option value="">Goal</option>
                  {goals.map((goal) => (
                    <option key={goal.id} value={goal.id}>
                      {goal.title}
                    </option>
                  ))}
                </select>
              ) : null}
              <button type="button" className="ghost" onClick={() => focusSession(session)}>
                Open
              </button>
              <button type="button" className="ghost" onClick={() => void pauseOrResume(session)}>
                {session.supervision_paused ? "Resume" : "Pause"}
              </button>
            </div>
          ))
        ) : (
          <p className="empty">PEX reviews Cursor and Codex. Start a worker normally; talk only to PEX here.</p>
        )}
      </section>

      <form className="ask dock" onSubmit={(event) => void askPex(event)}>
        <label htmlFor="pex-ask">Ask PEX</label>
        <div className="row">
          <input
            ref={askBox}
            id="pex-ask"
            value={ask}
            onChange={(event) => setAsk(event.target.value)}
            placeholder="What needs me?"
          />
          <button type="submit" className="solid" disabled={asking || !ask.trim()}>
            {asking ? "Checking" : "Ask"}
          </button>
        </div>
        {answer ? <output>{answer}</output> : null}
        {note ? <p className={`note ${note.startsWith("Hatching") ? "ok" : ""}`}>{note}</p> : null}
      </form>
    </main>
  );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replaceAll(":", " · ").trim().toLowerCase();
}

function titleCase(value: string): string {
  return humanize(value).replace(/\b\w/g, (letter) => letter.toUpperCase());
}

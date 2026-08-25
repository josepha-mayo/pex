import { FormEvent, useEffect, useMemo, useState } from "react";
import bramblePet from "./assets/bramble-hedgehog.webp";
import brambleBlocked from "./assets/bramble-hedgehog-blocked.webp";
import brambleNeedsInput from "./assets/bramble-hedgehog-needs-input.webp";
import brambleWorking from "./assets/bramble-hedgehog-working.webp";
import gaugePet from "./assets/gauge-tortoise.webp";
import gaugeBlocked from "./assets/gauge-tortoise-blocked.webp";
import gaugeNeedsInput from "./assets/gauge-tortoise-needs-input.webp";
import gaugeWorking from "./assets/gauge-tortoise-working.webp";
import micaPet from "./assets/mica-moth.webp";
import micaBlocked from "./assets/mica-moth-blocked.webp";
import micaNeedsInput from "./assets/mica-moth-needs-input.webp";
import micaWorking from "./assets/mica-moth-working.webp";
import noriPet from "./assets/nori-axolotl.webp";
import noriBlocked from "./assets/nori-axolotl-blocked.webp";
import noriNeedsInput from "./assets/nori-axolotl-needs-input.webp";
import noriWorking from "./assets/nori-axolotl-working.webp";
import pexIdle from "./assets/pex-watchcat.webp";
import pexBlocked from "./assets/pex-watchcat-blocked.webp";
import pexNeedsInput from "./assets/pex-watchcat-needs-input.webp";
import pexWorking from "./assets/pex-watchcat-working.webp";
import relayPet from "./assets/relay-hummingbird.webp";
import relayBlocked from "./assets/relay-hummingbird-blocked.webp";
import relayNeedsInput from "./assets/relay-hummingbird-needs-input.webp";
import relayWorking from "./assets/relay-hummingbird-working.webp";
import tallyPet from "./assets/tally-armadillo.webp";
import tallyBlocked from "./assets/tally-armadillo-blocked.webp";
import tallyNeedsInput from "./assets/tally-armadillo-needs-input.webp";
import tallyWorking from "./assets/tally-armadillo-working.webp";
import { CodexSprite, type PetMood, type PetShape } from "./pets/atlas";

type Surface = "compact" | "inspector" | "desk";
type Tone = "quiet" | "working" | "watching" | "needs" | "offline";

type LastAction = {
  id: string;
  session_id: string;
  action: string;
  diagnosis: string;
  evidence: string[];
  result: string;
  used_llm?: boolean;
};

type PetSnapshot = {
  headline: string;
  working: number;
  drifting: number;
  needs_you: number;
  paused?: number;
  last_action?: LastAction | null;
  mood?: PetMood;
  appearance?: {
    id: string;
    display_name: string;
    shape: PetShape;
    body: string;
    accent: string;
    spritesheet_url?: string;
    hue_shift?: number;
    scale?: number;
    source?: string;
  };
  settings?: {
    custom_name?: string;
    scale?: number;
  };
  sessions: Array<{
    id: string;
    harness_type: string;
    status: string;
    goal_id?: string | null;
    supervision_paused?: boolean;
  }>;
};

type Starter = {
  id: string;
  display_name: string;
  description: string;
  shape: PetShape;
  body: string;
  accent: string;
  source?: string;
};

type Intervention = {
  id: string;
  session_id: string;
  action_taken: string;
  diagnosis: string;
  result: string;
  reversible?: boolean;
  evidence?: string[];
};

type AdapterRow = {
  name: string;
  capabilities: { support_label: string; notes: string };
};

type Fingerprint = {
  harness: string;
  observed_sessions: number;
  premature_stop_rate: number;
  recommended_overlays: string[];
};

type DiscoverItem = {
  name: string;
  kind?: string;
  base_url?: string;
  bin?: string;
  surface?: string;
};

type Goal = {
  id: string;
  title: string;
  objective: string;
  acceptance_criteria?: string[];
};

type LocalPet = {
  id: string;
  name: string;
  description: string;
  sprites: {
    idle: string;
    working: string;
    needsInput: string;
    blocked: string;
  };
};

const BRIDGE = "http://127.0.0.1:7420";
const LOCAL_PETS: LocalPet[] = [
  {
    id: "pex",
    name: "Pex",
    description: "Keeps watch over every active goal.",
    sprites: {
      idle: pexIdle,
      working: pexWorking,
      needsInput: pexNeedsInput,
      blocked: pexBlocked,
    },
  },
  {
    id: "ledger",
    name: "Tally",
    description: "Remembers constraints and decisions.",
    sprites: {
      idle: tallyPet,
      working: tallyWorking,
      needsInput: tallyNeedsInput,
      blocked: tallyBlocked,
    },
  },
  {
    id: "mesh",
    name: "Relay",
    description: "Carries only the context another agent needs.",
    sprites: {
      idle: relayPet,
      working: relayWorking,
      needsInput: relayNeedsInput,
      blocked: relayBlocked,
    },
  },
  {
    id: "drift",
    name: "Mica",
    description: "Notices quiet drift before it becomes waste.",
    sprites: {
      idle: micaPet,
      working: micaWorking,
      needsInput: micaNeedsInput,
      blocked: micaBlocked,
    },
  },
  {
    id: "quiet",
    name: "Nori",
    description: "Waits calmly for real human judgment.",
    sprites: {
      idle: noriPet,
      working: noriWorking,
      needsInput: noriNeedsInput,
      blocked: noriBlocked,
    },
  },
  {
    id: "ember",
    name: "Bramble",
    description: "Protects risky boundaries and approvals.",
    sprites: {
      idle: bramblePet,
      working: brambleWorking,
      needsInput: brambleNeedsInput,
      blocked: brambleBlocked,
    },
  },
  {
    id: "spark",
    name: "Gauge",
    description: "Checks claims against observable evidence.",
    sprites: {
      idle: gaugePet,
      working: gaugeWorking,
      needsInput: gaugeNeedsInput,
      blocked: gaugeBlocked,
    },
  },
];

export function App() {
  const [pet, setPet] = useState<PetSnapshot | null>(null);
  const [pets, setPets] = useState<Starter[]>([]);
  const [surface, setSurface] = useState<Surface>("compact");
  const [answer, setAnswer] = useState("");
  const [question, setQuestion] = useState("what needs me?");
  const [asking, setAsking] = useState(false);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [adapters, setAdapters] = useState<AdapterRow[]>([]);
  const [fingerprints, setFingerprints] = useState<Fingerprint[]>([]);
  const [contextItems, setContextItems] = useState<Array<{ kind?: string; text?: string; content?: string }>>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fixtures, setFixtures] = useState<Array<{ id: string; title: string; events: number }>>([]);
  const [importDir, setImportDir] = useState("");
  const [customName, setCustomName] = useState("");
  const [scale, setScale] = useState(1);
  const [discovered, setDiscovered] = useState<DiscoverItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    const tick = async () => {
      try {
        const res = await fetch(`${BRIDGE}/v1/pet`);
        if (!res.ok) throw new Error("bridge unavailable");
        const data = (await res.json()) as PetSnapshot;
        if (!cancelled) {
          setPet(data);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("Local bridge is waking up");
      }
    };
    tick();
    try {
      socket = new WebSocket(`${BRIDGE.replace("http", "ws")}/v1/events`);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as { topic?: string; payload?: PetSnapshot };
          if (payload.topic === "pet" && payload.payload) {
            const incoming = payload.payload;
            setPet((prev) => ({
              ...(prev ?? incoming),
              ...incoming,
              appearance: prev?.appearance ?? incoming.appearance,
            }));
          }
          if (payload.topic === "intervention") {
            void tick();
          }
        } catch {
          /* ignore malformed frames */
        }
      };
    } catch {
      /* HTTP poll remains the fallback */
    }
    const id = window.setInterval(tick, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (surface === "compact") return;
    let cancelled = false;
    const loadDetails = async () => {
      try {
        const [catalog, deck, mesh, found, traj, goalRows] = await Promise.all([
          fetch(`${BRIDGE}/v1/pets`).then((r) => r.json()),
          fetch(`${BRIDGE}/v1/deck`).then((r) => r.json()),
          fetch(`${BRIDGE}/v1/context`).then((r) => r.json()),
          fetch(`${BRIDGE}/v1/discover`).then((r) => r.json()),
          fetch(`${BRIDGE}/v1/demo/trajectories`).then((r) => r.json()),
          fetch(`${BRIDGE}/v1/goals`).then((r) => r.json()),
        ]);
        if (cancelled) return;
        setPets(catalog.catalog ?? []);
        setInterventions(deck.interventions ?? []);
        setAdapters(deck.adapters ?? []);
        setFingerprints(deck.fingerprints ?? []);
        setContextItems(mesh ?? []);
        setDiscovered(found.found ?? []);
        setFixtures(traj.fixtures ?? []);
        setGoals(goalRows ?? []);
      } catch {
        /* Compact state already communicates bridge health. */
      }
    };
    void loadDetails();
    return () => {
      cancelled = true;
    };
  }, [surface, pet?.last_action?.id]);

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) return;
    const visualScale = Math.min(1.5, Math.max(0.7, scale));
    const actorWidth = Math.round(Math.max(126, 122 * visualScale + 8));
    const actorHeight = Math.round(Math.max(140, 122 * visualScale + 18));
    const dimensions: Record<Surface, [number, number]> = {
      compact: [Math.max(382, actorWidth + 256), actorHeight + 16],
      inspector: [398, 548],
      desk: [438, 704],
    };
    const [width, height] = dimensions[surface];
    void import("@tauri-apps/api/window").then(({ getCurrentWindow, LogicalSize }) =>
      getCurrentWindow().setSize(new LogicalSize(width, height)),
    );
  }, [scale, surface]);

  const status = useMemo(() => {
    if (error) {
      return {
        tone: "offline" as Tone,
        label: "Bridge offline",
        detail: "Retrying locally",
      };
    }
    if (pet?.needs_you) {
      return {
        tone: "needs" as Tone,
        label: pet.needs_you === 1 ? "Needs you" : `${pet.needs_you} need you`,
        detail: "A real decision is waiting",
      };
    }
    if (pet?.drifting) {
      return {
        tone: "watching" as Tone,
        label: "Correcting drift",
        detail: "PEX is handling it",
      };
    }
    if (pet?.working) {
      return {
        tone: "working" as Tone,
        label: `${pet.working} working`,
        detail: "You can keep working",
      };
    }
    return {
      tone: "quiet" as Tone,
      label: pet ? "All quiet" : "Waking up",
      detail: pet ? "Nothing needs babysitting" : "Connecting to the bridge",
    };
  }, [error, pet]);

  const primarySession = useMemo(() => {
    const sessions = pet?.sessions ?? [];
    return (
      sessions.find((session) => session.status === "needs_decision") ??
      sessions.find((session) => session.status === "drifting") ??
      sessions.find((session) => session.status === "working" || session.status === "verifying") ??
      sessions[0]
    );
  }, [pet]);

  const goalById = useMemo(() => new Map(goals.map((goal) => [goal.id, goal])), [goals]);
  const primaryGoal = primarySession?.goal_id ? goalById.get(primarySession.goal_id) : undefined;
  const mood: PetMood = pet?.mood ?? "idle";
  const look = pet?.appearance;
  const importedSheet =
    look?.source === "imported" && look.spritesheet_url ? `${BRIDGE}${look.spritesheet_url}` : null;
  const activeLocalPet = LOCAL_PETS.find((item) => item.id === look?.id) ?? LOCAL_PETS[0];
  const mascot = mascotForMood(mood, activeLocalPet);
  const nickname = pet?.settings?.custom_name?.trim();
  const activePetName = nickname
    ? nickname
    : look?.source === "imported"
      ? look.display_name
      : activeLocalPet.name;
  const compactPetScale = Math.min(1.5, Math.max(0.7, scale));
  const actorWidth = Math.max(126, 122 * compactPetScale + 8);
  const actorHeight = Math.max(140, 122 * compactPetScale + 18);

  useEffect(() => {
    setScale(pet?.settings?.scale ?? pet?.appearance?.scale ?? 1);
    setCustomName(pet?.settings?.custom_name ?? "");
  }, [pet?.appearance?.id, pet?.appearance?.scale, pet?.settings?.custom_name, pet?.settings?.scale]);

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || asking) return;
    setAsking(true);
    try {
      const res = await fetch(`${BRIDGE}/v1/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      setAnswer(data.answer);
    } catch {
      setAnswer("PEX could not reach its local state. The workers were not interrupted.");
    } finally {
      setAsking(false);
    }
  }

  async function openAgent(sessionId: string) {
    await fetch(`${BRIDGE}/v1/sessions/${sessionId}/focus`, { method: "POST" });
  }

  async function pauseSession(sessionId: string) {
    await fetch(`${BRIDGE}/v1/sessions/${sessionId}/pause-supervision`, { method: "POST" });
  }

  async function resumeSession(sessionId: string) {
    await fetch(`${BRIDGE}/v1/sessions/${sessionId}/resume-supervision`, { method: "POST" });
  }

  async function choosePet(id: string) {
    const response = await fetch(`${BRIDGE}/v1/pets/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_id: id }),
    });
    if (!response.ok) return;
    const snapshot = await fetch(`${BRIDGE}/v1/pet`);
    if (snapshot.ok) setPet((await snapshot.json()) as PetSnapshot);
  }

  async function saveCustom() {
    const response = await fetch(`${BRIDGE}/v1/pets/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ custom_name: customName, scale }),
    });
    if (!response.ok) return;
    const snapshot = await fetch(`${BRIDGE}/v1/pet`);
    if (snapshot.ok) setPet((await snapshot.json()) as PetSnapshot);
  }

  async function importCodex() {
    if (!importDir.trim()) return;
    await fetch(`${BRIDGE}/v1/pets/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory: importDir.trim() }),
    });
  }

  async function undo(id: string) {
    await fetch(`${BRIDGE}/v1/interventions/${id}/undo`, { method: "POST" });
  }

  async function playReplay(id: string) {
    const res = await fetch(`${BRIDGE}/v1/demo/replay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fixture: id }),
    });
    const data = await res.json();
    setAnswer(
      data.replay
        ? `REPLAY (not live control): ${data.inbox?.[0] ?? data.session_id}`
        : "Replay failed.",
    );
  }

  async function attachDiscovered(name: string) {
    await fetch(`${BRIDGE}/v1/discover/attach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  }

  return (
    <main className={`ambient surface-${surface} tone-${status.tone}`}>
      {surface !== "compact" ? (
        <section className={`companion-panel ${surface === "desk" ? "desk" : ""}`} aria-label="PEX details">
          <header className="panel-header">
            <div className="panel-tools">
              <span className="panel-kicker">
                <span className="status-dot" aria-hidden="true" />
                {status.label}
              </span>
              <span className="panel-buttons">
                {surface === "inspector" ? (
                  <button className="text-button" type="button" onClick={() => setSurface("desk")}>
                    Open desk
                  </button>
                ) : (
                  <button className="text-button" type="button" onClick={() => setSurface("inspector")}>
                    Back
                  </button>
                )}
                <button className="text-button muted" type="button" onClick={() => setSurface("compact")}>
                  Close
                </button>
              </span>
            </div>
            <h1>{primaryGoal?.title ?? (primarySession ? `${titleCase(primarySession.harness_type)} is in view` : "Nothing needs you")}</h1>
            <p>{primaryGoal?.objective ?? status.detail}</p>
          </header>

          {surface === "inspector" ? (
            <Inspector
              pet={pet}
              primarySession={primarySession}
              answer={answer}
              question={question}
              asking={asking}
              onQuestion={setQuestion}
              onAsk={ask}
              onOpen={openAgent}
              onPause={pauseSession}
              onResume={resumeSession}
              onUndo={undo}
            />
          ) : (
            <Desk
              pet={pet}
              pets={pets}
              interventions={interventions}
              contextItems={contextItems}
              adapters={adapters}
              discovered={discovered}
              fingerprints={fingerprints}
              fixtures={fixtures}
              importDir={importDir}
              customName={customName}
              scale={scale}
              onImportDir={setImportDir}
              onCustomName={setCustomName}
              onScale={setScale}
              onOpen={openAgent}
              onPause={pauseSession}
              onResume={resumeSession}
              onUndo={undo}
              onAttach={attachDiscovered}
              onChoosePet={choosePet}
              onSaveCustom={saveCustom}
              onImport={importCodex}
              onReplay={playReplay}
            />
          )}
        </section>
      ) : null}

      <div className="compact-row">
        <button
          className={`pet-actor mood-${mood}`}
          type="button"
          onClick={() => setSurface(surface === "compact" ? "inspector" : "compact")}
          style={{ width: `${actorWidth}px`, height: `${actorHeight}px` }}
          aria-label={
            surface === "compact" ? `Open ${activePetName} details` : `Close ${activePetName} details`
          }
        >
          {importedSheet ? (
            <CodexSprite src={importedSheet} mood={mood} scale={compactPetScale * 2} />
          ) : (
            <img
              src={mascot}
              alt=""
              draggable="false"
              style={{
                width: `${122 * compactPetScale}px`,
                height: `${122 * compactPetScale}px`,
              }}
            />
          )}
          <span className="pet-name">{activePetName}</span>
        </button>

        <button
          className="activity-bubble"
          type="button"
          onClick={() => (primarySession ? openAgent(primarySession.id) : setSurface("inspector"))}
          aria-live="polite"
        >
          <span className="status-dot" aria-hidden="true" />
          <span>
            <strong>{status.label}</strong>
            <small>{status.detail}</small>
          </span>
        </button>
      </div>
    </main>
  );
}

type SessionRow = PetSnapshot["sessions"][number];

function Inspector({
  pet,
  primarySession,
  answer,
  question,
  asking,
  onQuestion,
  onAsk,
  onOpen,
  onPause,
  onResume,
  onUndo,
}: {
  pet: PetSnapshot | null;
  primarySession?: SessionRow;
  answer: string;
  question: string;
  asking: boolean;
  onQuestion: (value: string) => void;
  onAsk: (event: FormEvent) => void;
  onOpen: (sessionId: string) => void;
  onPause: (sessionId: string) => void;
  onResume: (sessionId: string) => void;
  onUndo: (interventionId: string) => void;
}) {
  const action = pet?.last_action;
  return (
    <div className="inspector-body">
      {primarySession ? (
        <div className="session-line">
          <span>
            <strong>{titleCase(primarySession.harness_type)}</strong>
            <small>
              {humanize(primarySession.status)}
              {primarySession.supervision_paused ? " · supervision paused" : ""}
            </small>
          </span>
          <span className="session-actions">
            <button className="secondary-button" type="button" onClick={() => onOpen(primarySession.id)}>
              Open agent
            </button>
            {primarySession.supervision_paused ? (
              <button className="text-button" type="button" onClick={() => onResume(primarySession.id)}>
                Resume
              </button>
            ) : (
              <button className="text-button muted" type="button" onClick={() => onPause(primarySession.id)}>
                Pause
              </button>
            )}
          </span>
        </div>
      ) : (
        <div className="empty-note">Start Cursor or Codex normally. PEX will appear when it discovers an active session.</div>
      )}

      {action ? (
        <section className="action-story">
          <h2>What PEX did</h2>
          <strong>{humanize(action.action)}</strong>
          <p>{humanize(action.diagnosis)}</p>
          {action.evidence?.length ? (
            <details className="evidence">
              <summary>Show evidence</summary>
              <ul>
                {action.evidence.slice(0, 4).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          ) : null}
          {action.result ? <small className="result-line">Result: {humanize(action.result)}</small> : null}
          {action.result === "undo_available" ? (
            <button className="text-button" type="button" onClick={() => onUndo(action.id)}>
              Undo
            </button>
          ) : null}
        </section>
      ) : (
        <section className="action-story quiet-story">
          <h2>What PEX did</h2>
          <strong>Stayed quiet</strong>
          <p>No evidence justified an intervention.</p>
        </section>
      )}

      <form className="ask-pex" onSubmit={onAsk}>
        <label htmlFor="pex-question">Ask without interrupting the worker</label>
        <div className="ask-row">
          <input
            id="pex-question"
            value={question}
            onChange={(event) => onQuestion(event.target.value)}
            placeholder="What needs me?"
          />
          <button className="primary-button" type="submit" disabled={asking}>
            {asking ? "Checking" : "Ask"}
          </button>
        </div>
        {answer ? <output>{answer}</output> : null}
      </form>
    </div>
  );
}

function Desk({
  pet,
  pets,
  interventions,
  contextItems,
  adapters,
  discovered,
  fingerprints,
  fixtures,
  importDir,
  customName,
  scale,
  onImportDir,
  onCustomName,
  onScale,
  onOpen,
  onPause,
  onResume,
  onUndo,
  onAttach,
  onChoosePet,
  onSaveCustom,
  onImport,
  onReplay,
}: {
  pet: PetSnapshot | null;
  pets: Starter[];
  interventions: Intervention[];
  contextItems: Array<{ kind?: string; text?: string; content?: string }>;
  adapters: AdapterRow[];
  discovered: DiscoverItem[];
  fingerprints: Fingerprint[];
  fixtures: Array<{ id: string; title: string; events: number }>;
  importDir: string;
  customName: string;
  scale: number;
  onImportDir: (value: string) => void;
  onCustomName: (value: string) => void;
  onScale: (value: number) => void;
  onOpen: (sessionId: string) => void;
  onPause: (sessionId: string) => void;
  onResume: (sessionId: string) => void;
  onUndo: (interventionId: string) => void;
  onAttach: (name: string) => void;
  onChoosePet: (id: string) => void;
  onSaveCustom: () => void;
  onImport: () => void;
  onReplay: (id: string) => void;
}) {
  const importedPets = pets.filter((item) => item.source === "imported");
  return (
    <div className="desk-scroll">
      <details className="desk-section" open>
        <summary>Active work <span>{pet?.sessions.length ?? 0}</span></summary>
        <div className="desk-content">
          {(pet?.sessions ?? []).length ? (
            pet?.sessions.map((session) => (
              <div className="desk-row" key={session.id}>
                <span>
                  <strong>{titleCase(session.harness_type)}</strong>
                  <small>{humanize(session.status)}</small>
                </span>
                <span className="row-actions">
                  <button className="text-button" type="button" onClick={() => onOpen(session.id)}>
                    Open
                  </button>
                  {session.supervision_paused ? (
                    <button className="text-button" type="button" onClick={() => onResume(session.id)}>
                      Resume
                    </button>
                  ) : (
                    <button className="text-button muted" type="button" onClick={() => onPause(session.id)}>
                      Pause
                    </button>
                  )}
                </span>
              </div>
            ))
          ) : (
            <p className="empty-copy">No active sessions discovered.</p>
          )}
        </div>
      </details>

      <details className="desk-section">
        <summary>Interventions <span>{interventions.length}</span></summary>
        <div className="desk-content">
          {interventions.length ? (
            interventions.slice(0, 10).map((item) => (
              <div className="desk-row" key={item.id}>
                <span>
                  <strong>{humanize(item.action_taken)}</strong>
                  <small>{humanize(item.result)}</small>
                </span>
                {item.reversible ? (
                  <button className="text-button" type="button" onClick={() => onUndo(item.id)}>
                    Undo
                  </button>
                ) : null}
              </div>
            ))
          ) : (
            <p className="empty-copy">No interventions yet.</p>
          )}
        </div>
      </details>

      <details className="desk-section">
        <summary>Durable context <span>{contextItems.length}</span></summary>
        <div className="desk-content">
          {contextItems.length ? (
            contextItems.slice(0, 10).map((item, index) => (
              <div className="context-line" key={`${item.kind ?? "fact"}-${index}`}>
                <small>{item.kind ?? "fact"}</small>
                <p>{item.content ?? item.text ?? ""}</p>
              </div>
            ))
          ) : (
            <p className="empty-copy">PEX records project facts only when they become useful.</p>
          )}
        </div>
      </details>

      <details className="desk-section">
        <summary>Harnesses <span>{adapters.length + discovered.length}</span></summary>
        <div className="desk-content">
          {adapters.map((adapter) => (
            <div className="desk-row" key={adapter.name}>
              <span>
                <strong>{titleCase(adapter.name)}</strong>
                <small>{adapter.capabilities.support_label}</small>
              </span>
            </div>
          ))}
          {discovered.map((item) => (
            <div className="desk-row" key={item.name}>
              <span>
                <strong>{titleCase(item.name)}</strong>
                <small>{item.surface || item.bin || item.base_url || "available"}</small>
              </span>
              <button className="text-button" type="button" onClick={() => onAttach(item.name)}>
                Attach
              </button>
            </div>
          ))}
          {fingerprints.map((fingerprint) => (
            <p className="fingerprint" key={fingerprint.harness}>
              {titleCase(fingerprint.harness)} · {fingerprint.observed_sessions} observed ·{" "}
              {Math.round(fingerprint.premature_stop_rate * 100)}% premature-stop history
            </p>
          ))}
        </div>
      </details>

      <details className="desk-section">
        <summary>Pet <span>{LOCAL_PETS.length + importedPets.length} available</span></summary>
        <div className="desk-content pet-settings">
          <div className="pet-grid">
            {LOCAL_PETS.map((item) => (
              <button
                className={`pet-option ${pet?.appearance?.id === item.id ? "selected" : ""}`}
                type="button"
                onClick={() => onChoosePet(item.id)}
                aria-label={item.name}
                aria-pressed={pet?.appearance?.id === item.id}
                key={item.id}
              >
                <img src={item.sprites.idle} alt="" />
                <span><strong>{item.name}</strong><small>{item.description}</small></span>
              </button>
            ))}
          </div>
          {importedPets.map((item) => (
            <button
              className={`pet-option ${pet?.appearance?.id === item.id ? "selected" : ""}`}
              type="button"
              onClick={() => onChoosePet(item.id)}
              aria-label={item.display_name}
              aria-pressed={pet?.appearance?.id === item.id}
              key={item.id}
            >
              <CodexSprite src={`${BRIDGE}/v1/pets/${item.id}/spritesheet`} mood="idle" scale={56 / 54} />
              <span><strong>{item.display_name}</strong><small>{item.description}</small></span>
            </button>
          ))}
          <label>
            Nickname
            <input value={customName} onChange={(event) => onCustomName(event.target.value)} />
          </label>
          <label>
            Pet scale · {scale.toFixed(2)}
            <input
              type="range"
              min={0.7}
              max={1.5}
              step={0.05}
              value={scale}
              onChange={(event) => onScale(Number(event.target.value))}
            />
          </label>
          <button className="secondary-button" type="button" onClick={onSaveCustom}>Save appearance</button>
          <label>
            Codex v2 pet folder
            <input
              value={importDir}
              placeholder="Folder with pet.json and spritesheet.webp"
              onChange={(event) => onImportDir(event.target.value)}
            />
          </label>
          <button className="text-button import-button" type="button" onClick={onImport}>Import pet</button>
        </div>
      </details>

      <details className="desk-section">
        <summary>Benchmark replay <span>{fixtures.length}</span></summary>
        <div className="desk-content">
          <p className="disclosure">Sanitized replay is evidence review, not live harness control.</p>
          {fixtures.map((item) => (
            <div className="desk-row" key={item.id}>
              <span>
                <strong>{item.title}</strong>
                <small>{item.events} recorded events</small>
              </span>
              <button className="text-button" type="button" onClick={() => onReplay(item.id)}>
                Play
              </button>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function mascotForMood(mood: PetMood, pet: LocalPet): string {
  if (mood === "decision") return pet.sprites.needsInput;
  if (mood === "warning" || mood === "degraded") return pet.sprites.blocked;
  if (mood === "working" || mood === "drift" || mood === "handoff") return pet.sprites.working;
  return pet.sprites.idle;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replaceAll(":", " · ").trim().toLowerCase();
}

function titleCase(value: string): string {
  return humanize(value).replace(/\b\w/g, (letter) => letter.toUpperCase());
}

import { useEffect, useState, type FormEvent } from "react";
import type { Goal, LastAction, SessionRow } from "../types";
import { actionExplanation, recordedActionLabel, supervisorInferenceReceipt } from "../viewModel";

type Props = {
  workspace: string;
  sessions: SessionRow[];
  current?: SessionRow;
  goal?: Goal;
  action?: LastAction | null;
  objective: string;
  saving: boolean;
  choosing: boolean;
  available: boolean;
  note?: string | null;
  question: string;
  answer: string;
  asking: boolean;
  onChooseFolder: () => void;
  onWorkspace: (path: string) => void;
  onSession: (id: string) => void;
  onObjective: (text: string) => void;
  onSave: (event: FormEvent) => void;
  onQuestion: (text: string) => void;
  onAsk: (event: FormEvent) => void;
  onDetails: () => void;
  onConnect: () => void;
};

export function ChatHome(p: Props) {
  const [newGoal, setNewGoal] = useState(false);
  useEffect(() => { setNewGoal(false); }, [p.goal?.id, p.workspace]);
  const visibleSessions = p.sessions;
  const composing = !p.goal || newGoal;
  return <section className="chat-home surface-focus-target" data-surface-root="compact" tabIndex={-1}>
    <header className="chat-workspace">
      <button className="chat-folder" onClick={p.onChooseFolder} disabled={p.choosing || p.saving} type="button">
        <span aria-hidden="true">▱</span>
        <span>{p.choosing ? "Choosing folder…" : p.workspace ? p.workspace.split(/[\\/]/).filter(Boolean).pop() : "Choose folder"}</span>
        <span aria-hidden="true">⌄</span>
      </button>
      <button className="ghost" onClick={p.onConnect} type="button">Connections</button>
    </header>
    <div className="chat-thread">
      {p.workspace ? <p className="chat-path" title={p.workspace}>{p.workspace}</p> : null}
      {visibleSessions.length ? <label className="chat-session">All connected sessions
        <select value={p.current?.id || ""} onChange={e=>p.onSession(e.target.value)} disabled={p.saving}>
          <option value="" disabled>Choose a session</option>
          {visibleSessions.map(s=><option key={s.id} value={s.id}>{s.label || s.harness_type} · {s.cwd || "No workspace"}{s.capabilities?.send_message ? "" : " · View only"}</option>)}
        </select>
      </label> : null}
      <article className="chat-message chat-pex">
        <span className="chat-speaker">PEX</span>
        <p>{!p.current ? visibleSessions.length ? "Choose a session above. Its workspace is selected automatically." : "Connect OpenCode to see its sessions here." : !p.available ? "This session is visible, but live supervision is not available yet. Check Connections." : composing ? "What should your agent finish? Tell me the outcome and how to check it." : "I’m watching this goal and checking your agent’s progress."}</p>
      </article>
      {p.goal ? <article className="chat-message chat-you"><span className="chat-speaker">Your goal</span><p>{p.goal.objective}</p></article> : null}
      {p.goal && p.action ? <article className="chat-message chat-pex">
        <span className="chat-speaker">PEX · {recordedActionLabel(p.action)}</span>
        <p>{actionExplanation(p.action)}</p>
        <details><summary>View evidence</summary><p>{supervisorInferenceReceipt(p.action)}</p>{p.action.evidence?.map((line,i)=><p key={i}>{line}</p>)}<button className="ghost" type="button" onClick={p.onDetails}>Full activity</button></details>
      </article> : null}
      {p.answer ? <article className="chat-message chat-pex"><span className="chat-speaker">PEX</span><p>{p.answer}</p></article> : null}
      {p.note ? <p className="chat-feedback" role="status">{p.note}</p> : null}
    </div>
    <footer className="chat-compose-area">
      {composing ? <form className="chat-composer" onSubmit={event=>{p.onSave(event);}}>
        <label htmlFor="simple-goal">Your goal</label>
        <textarea id="simple-goal" value={p.objective} onChange={e=>p.onObjective(e.target.value)} rows={4} placeholder="What should get done? Paste your goal here…" disabled={p.saving}/>
        <div className="chat-compose-actions"><small>{p.current ? "Applies only to the selected session" : "Choose a connected session above"}</small><button className="solid" type="submit" disabled={!p.available || !p.current || !p.workspace || !p.objective.trim() || p.saving}>{p.saving ? "Starting…" : "Start supervising"}</button></div>
      </form> : <form className="chat-composer" onSubmit={p.onAsk}>
        <label htmlFor="simple-question">Ask about this work</label>
        <input id="simple-question" value={p.question} onChange={e=>p.onQuestion(e.target.value)} placeholder="What still needs to be done?" disabled={p.asking}/>
        <div className="chat-compose-actions"><button type="button" className="ghost" onClick={()=>setNewGoal(true)}>New goal</button><button className="solid" disabled={p.asking || !p.question.trim()}>{p.asking ? "Checking…" : "Ask PEX"}</button></div>
      </form>}
      <details className="chat-manual-path"><summary>Enter a folder path instead</summary><input aria-label="Workspace folder path" value={p.workspace} onChange={e=>p.onWorkspace(e.target.value)} disabled={p.saving}/></details>
    </footer>
  </section>;
}

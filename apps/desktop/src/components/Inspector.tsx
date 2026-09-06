import type { FormEvent, ReactNode, RefObject } from "react";

import type { GoalDraft } from "./GoalEditor";
import { GoalEditor } from "./GoalEditor";
import { AskPex } from "./AskPex";
import type {
  Goal,
  GoalCompletion,
  LastAction,
  LedgerDecision,
  SessionRow,
  StatusCopy,
} from "../types";
import {
  canAttachPersistentGoal,
  canOpenSession,
  humanize,
  isSafelyUndoable,
  askPexQuestions,
  meaningfulEvidence,
  nextExpectedEvent,
  partitionLedgerDecisions,
  titleCase,
} from "../viewModel";

export function Inspector({
  current,
  sessions = [],
  goal,
  ledgerDecisions = [],
  completion,
  goals,
  action,
  status,
  supervisorNotice,
  evidenceOpen,
  question,
  answer,
  asking,
  askInput,
  goalDraft,
  savingGoal,
  attachingGoal,
  editingGoal,
  note,
  canonicalStateAvailable = true,
  canonicalStateIssue,
  sessionActionsAvailable = true,
  goalActionsAvailable = true,
  onEvidence,
  onOpen,
  onPause,
  onUndo,
  onAttachGoal,
  onGoalChange,
  onCreateGoal,
  onEditGoal,
  onCancelEdit,
  onQuestion,
  onAsk,
  onAskPrompt,
  onOpenDeck,
  onSelectSession,
}: {
  current?: SessionRow;
  sessions?: SessionRow[];
  goal?: Goal;
  ledgerDecisions?: LedgerDecision[];
  completion?: GoalCompletion | null;
  goals: Goal[];
  action?: LastAction | null;
  status: StatusCopy;
  supervisorNotice?: ReactNode;
  evidenceOpen: boolean;
  question: string;
  answer: string;
  asking: boolean;
  askInput: RefObject<HTMLInputElement | null>;
  goalDraft: GoalDraft;
  savingGoal: boolean;
  attachingGoal: boolean;
  editingGoal?: boolean;
  note?: string | null;
  canonicalStateAvailable?: boolean;
  canonicalStateIssue?: string | null;
  sessionActionsAvailable?: boolean;
  goalActionsAvailable?: boolean;
  onEvidence: () => void;
  onOpen: () => void;
  onPause: () => void;
  onUndo: () => void;
  onAttachGoal: (goalId: string) => void;
  onGoalChange: (field: keyof GoalDraft, value: string) => void;
  onCreateGoal: (event: FormEvent) => void;
  onEditGoal?: () => void;
  onCancelEdit?: () => void;
  onQuestion: (value: string) => void;
  onAsk: (event: FormEvent) => void;
  onAskPrompt?: (prompt: string) => void;
  onOpenDeck: () => void;
  onSelectSession?: (sessionId: string) => void;
}) {
  const canUndo = Boolean(
    action?.id && isSafelyUndoable(action.action, action.reversible, action.result),
  );
  const canOpen = canOpenSession(current);
  const canAttach = canAttachPersistentGoal(current);
  const ledger = partitionLedgerDecisions(ledgerDecisions);
  const actionName = !action
    ? "No recorded action"
    : action.action === "NOOP"
      ? "Stayed quiet"
      : humanize(action.action);
  const actionWhy =
    action?.diagnosis ||
    (action?.action === "NOOP"
      ? "No observed condition justified an intervention."
      : "The bridge recorded this action without a diagnosis.");

  return (
    <section
      className="inspector-shell surface-focus-target"
      aria-label="PEX inspector"
      data-surface-root="inspector"
      tabIndex={-1}
    >
      <header className="surface-heading">
        <div>
          <p className="eyebrow">Inspector · {current ? titleCase(current.harness_type) : "No worker"}</p>
          <h1>{goal?.title || current?.label || "Waiting for an attached goal"}</h1>
          <p>{goal?.objective || status.detail}</p>
        </div>
        <button type="button" className="solid" onClick={onOpenDeck}>
          Open command deck
        </button>
      </header>
      {supervisorNotice}
      {canonicalStateIssue ? (
        <p className="canonical-state-warning" role="status" aria-live="polite">
          {canonicalStateIssue} Revision-dependent controls stay disabled until refresh succeeds.
        </p>
      ) : null}
      {sessions.length > 1 ? (
        <div className="session-chips" role="group" aria-label="Sessions">
          {sessions.map((session) => (
            <button
              type="button"
              className={session.id === current?.id ? "active" : ""}
              aria-pressed={session.id === current?.id}
              onClick={() => onSelectSession?.(session.id)}
              key={session.id}
            >
              {titleCase(session.harness_type)}
              <span className={`state-pill state-${session.status}`}>{humanize(session.status)}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="inspector-grid">
        <section className="story-card session-story">
          <div className="card-heading">
            <span>
              <small>Current agent / session</small>
              <strong>{current?.label || (current ? titleCase(current.harness_type) : "No active worker")}</strong>
            </span>
            <span className={`state-pill state-${current?.status || "idle"}`}>
              {humanize(current?.status || "idle")}
            </span>
          </div>
          <dl className="inspector-facts">
            <div>
              <dt>Latest meaningful progress</dt>
              <dd>{meaningfulEvidence(current)}</dd>
            </div>
            <div>
              <dt>Next expected event</dt>
              <dd>{nextExpectedEvent(current)}</dd>
            </div>
            <div>
              <dt>Adapter control</dt>
              <dd>
                {current?.capabilities?.support_label
                  ? `${titleCase(String(current.capabilities.support_label))} · `
                  : "Unprobed · "}
                {canOpen ? "existing-window focus available" : "window focus unavailable"}
              </dd>
            </div>
          </dl>
          {current ? (
            <div className="button-row">
              <button type="button" className="solid" onClick={onOpen} disabled={!canOpen}>
                {canOpen ? "Open agent" : "Open unavailable"}
              </button>
              <button type="button" className="ghost" onClick={onPause} disabled={!sessionActionsAvailable}>
                {current.supervision_paused ? "Resume supervision" : "Pause supervision"}
              </button>
            </div>
          ) : (
            <p className="empty-copy">
              PEX lists already-open Cursor, Codex, OpenCode, Hermes, and Claude Code
              sessions without restarting them. A closed harness stays unavailable until
              its app or API is actually running.
            </p>
          )}
        </section>

        <section className="story-card action-story">
          <div className="card-heading">
            <span>
              <small>What PEX changed</small>
              <strong>{titleCase(actionName)}</strong>
            </span>
            {action?.confidence != null ? (
              <span className="confidence">{Math.round(action.confidence * 100)}% confidence</span>
            ) : null}
          </div>
          <p className="diagnosis">{actionWhy}</p>
          {action?.result ? (
            <p className="result-line">
              <span>Observed result</span>
              {humanize(action.result)}
            </p>
          ) : null}
          {action?.verification_status || action?.evidence_tools?.length ? (
            <p className="result-line">
              <span>Inspected state</span>
              {[
                action.verification_status ? humanize(action.verification_status) : "",
                action.evidence_tools?.length ? `tools: ${action.evidence_tools.join(", ")}` : "",
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          ) : null}
          {evidenceOpen && action?.evidence?.length ? (
            <ul className="evidence-list">
              {action.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          <div className="button-row">
            <button type="button" className="ghost" onClick={onEvidence} disabled={!action?.evidence?.length}>
              {evidenceOpen ? "Hide evidence" : "Show evidence"}
            </button>
            <button type="button" className="ghost" onClick={onUndo} disabled={!canUndo}>
              Undo last intervention
            </button>
          </div>
        </section>
      </div>

      <section className="goal-card" data-goal-setup="true" tabIndex={-1} aria-label="Persistent goal setup">
        <div className="card-heading">
          <span>
            <small>Persistent goal</small>
            <strong>{goal ? goal.title : "No goal attached"}</strong>
          </span>
          {current ? (
            <label className="goal-select">
              {canAttach
                ? current.goal_id
                  ? "Replace goal"
                  : "Attach goal"
                : "Observe-only tile"}
              <select
                value={canAttach ? current.goal_id || "" : ""}
                disabled={attachingGoal || !canAttach || !goalActionsAvailable}
                onChange={(event) => onAttachGoal(event.target.value)}
              >
                <option value="">
                  {canAttach
                    ? "Choose a stored goal"
                    : "Attach a goal to a live vendor session, not this desktop row"}
                </option>
                {canAttach
                  ? goals.map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.title}
                      </option>
                    ))
                  : null}
              </select>
            </label>
          ) : null}
        </div>
        {goal ? (
          <>
            <p className="note" role="status">
              {!canonicalStateAvailable
                ? "Goal completion unavailable while canonical state is offline."
                : completion?.status === "verified_complete"
                  ? "Verified complete for the current persistent intent."
                  : completion?.status === "incomplete"
                    ? "Current evidence shows unmet acceptance requirements."
                    : completion?.status === "in_progress"
                      ? "Work is active; completion is not yet established."
                      : "Completion remains uncertain; PEX will not infer it from narration."}
            </p>
            <div className="goal-boundaries">
              <Boundary label="Acceptance" values={goal.acceptance_criteria} />
              <Boundary label="Constraints" values={goal.constraints} />
              <Boundary label="Non-goals" values={goal.non_goals} />
              <Boundary label="Preferences" values={goal.preferences} />
              <Boundary label="Required evidence" values={goal.evidence_requirements} />
              <Boundary label="Decisions" values={ledger.decisions.map((item) => item.statement)} />
              <Boundary label="Rejected approaches" values={ledger.rejected.map((item) => item.statement)} />
              <Boundary label="Unresolved questions" values={ledger.unresolved.map((item) => item.statement)} />
            </div>
            {onEditGoal ? (
              <div className="button-row">
                <button type="button" className="ghost" onClick={onEditGoal} disabled={savingGoal || !goalActionsAvailable}>
                  Edit this ledger
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <p className="empty-copy">PEX inspects against a stored goal, not whichever chat spoke last.</p>
        )}
        <details
          className="goal-editor"
          key={editingGoal ? "editing" : "create"}
          {...(editingGoal || !goal ? { open: true } : {})}
        >
          <summary>
            {editingGoal
              ? "Edit persistent ledger"
              : goal
                ? "Create another persistent goal"
                : "Create persistent goal"}
          </summary>
          <GoalEditor
            draft={goalDraft}
            saving={savingGoal}
            disabled={!goalActionsAvailable}
            willAttach={canAttach && !editingGoal}
            editing={editingGoal}
            projectIdentity={current?.project_id || current?.cwd || undefined}
            onChange={onGoalChange}
            onSubmit={onCreateGoal}
            onCancel={onCancelEdit}
          />
        </details>
        {note ? <p className="note" role="status" aria-live="polite">{note}</p> : null}
      </section>

      <AskPex
        question={question}
        answer={answer}
        asking={asking}
        inputRef={askInput}
        questions={canonicalStateAvailable ? askPexQuestions(sessions, action) : []}
        onQuestion={onQuestion}
        onSubmit={onAsk}
        onAskPrompt={onAskPrompt}
      />
    </section>
  );
}

function Boundary({ label, values }: { label: string; values?: string[] }) {
  return (
    <div>
      <small>{label}</small>
      {values?.length ? (
        <ul>
          {values.map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      ) : (
        <p>None recorded</p>
      )}
    </div>
  );
}

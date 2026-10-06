import { useState, type FormEvent, type ReactNode, type RefObject } from "react";

import type { GoalDraft } from "./GoalEditor";
import { GoalEditor } from "./GoalEditor";
import { unifiedDiff } from "../diffText";
import { isLiveWorkerSession, isReplaySession } from "../demoReplay";
import { AskPex } from "./AskPex";
import { goalCompletionCopy } from "../completionPresentation";
import { handoffAssimilationPresentation } from "../handoffPresentation";
import {
  verificationSummaryLine,
  verificationVerdictLabel,
  type VerificationReportView,
} from "../verificationReport";
import type {
  AcceptanceDiff,
  Goal,
  GoalCompletion,
  HandoffAssimilationStatus,
  Intervention,
  LastAction,
  LedgerDecision,
  SessionRow,
  StatusCopy,
} from "../types";
import {
  actionExplanation,
  recordedActionLabel,
  canAttachPersistentGoal,
  canOpenSession,
  humanize,
  goalDeadlineCopy,
  isSafelyUndoable,
  askPexQuestions,
  meaningfulEvidence,
  nextExpectedEvent,
  observationGapCopy,
  partitionLedgerDecisions,
  supervisorReviewAllowanceCopy,
  supervisorInferenceReceipt,
  titleCase,
} from "../viewModel";

function interventionLogLabel(item: Intervention): string {
  if (item.action_taken === "NOOP") return "Stayed quiet";
  if (item.action_taken === "SUPPRESSED_COOLDOWN") {
    return "Repeat proposal suppressed (cooldown)";
  }
  return humanize(item.action_taken);
}

function interventionLogResult(item: Intervention): string | null {
  const result = item.result || item.outcome || "";
  if (!result || result === "noop" || result === item.action_taken) return null;
  return humanize(result);
}

function interventionLogDetail(item: Intervention): string | undefined {
  const parts = [
    item.proposed_action?.rationale,
    item.diagnosis && item.diagnosis !== item.action_taken ? `diagnosis: ${item.diagnosis}` : "",
    ...(item.evidence || []).slice(0, 6),
  ].filter(Boolean);
  return parts.length ? parts.join("\n") : undefined;
}

export function Inspector({
  current,
  sessions = [],
  goal,
  ledgerDecisions = [],
  completion,
  verificationReport,
  sessionInterventions = [],
  packVerification = null,
  exportingReport,
  onExportReport,
  exportingPack,
  onExportEvidencePack,
  onFetchAcceptanceDiff,
  goals,
  action,
  handoffStatus,
  status,
  supervisorNotice,
  evidenceOpen,
  question,
  answer,
  asking,
  askInput,
  goalDraft,
  goalEditorRevision,
  savingGoal,
  attachingGoal,
  editingGoal,
  goalOverrideMode,
  note,
  canonicalStateAvailable = true,
  canonicalStateIssue,
  sessionActionsAvailable = true,
  goalActionsAvailable = true,
  handoffTargets = [],
  handoffBusy = false,
  onHandoff,
  onEvidence,
  onOpen,
  onPause,
  onUndo,
  onAttachGoal,
  onGoalChange,
  onFillExample,
  onCreateGoal,
  onEditGoal,
  onCancelEdit,
  onGoalOverrideModeChange,
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
  verificationReport?: VerificationReportView | null;
  sessionInterventions?: Intervention[];
  packVerification?: { goalId: string; checks: string[] } | null;
  exportingReport?: boolean;
  onExportReport?: () => void;
  exportingPack?: boolean;
  onExportEvidencePack?: () => void;
  onFetchAcceptanceDiff?: (path: string) => Promise<AcceptanceDiff>;
  goals: Goal[];
  action?: LastAction | null;
  handoffStatus?: HandoffAssimilationStatus | "unreachable";
  status: StatusCopy;
  supervisorNotice?: ReactNode;
  evidenceOpen: boolean;
  question: string;
  answer: string;
  asking: boolean;
  askInput: RefObject<HTMLInputElement | null>;
  goalDraft: GoalDraft;
  goalEditorRevision: number;
  savingGoal: boolean;
  attachingGoal: boolean;
  editingGoal?: boolean;
  goalOverrideMode?: boolean;
  note?: string | null;
  canonicalStateAvailable?: boolean;
  canonicalStateIssue?: string | null;
  sessionActionsAvailable?: boolean;
  goalActionsAvailable?: boolean;
  handoffTargets?: SessionRow[];
  handoffBusy?: boolean;
  onHandoff?: (targetId: string) => void;
  onEvidence: () => void;
  onOpen: () => void;
  onPause: () => void;
  onUndo: () => void;
  onAttachGoal: (goalId: string) => void;
  onGoalChange: (field: keyof GoalDraft, value: string | boolean) => void;
  onFillExample: () => void;
  onCreateGoal: (event: FormEvent) => void;
  onEditGoal?: () => void;
  onCancelEdit?: () => void;
  onGoalOverrideModeChange?: (value: boolean) => void;
  onQuestion: (value: string) => void;
  onAsk: (event: FormEvent) => void;
  onAskPrompt?: (prompt: string) => void;
  onOpenDeck: () => void;
  onSelectSession?: (sessionId: string) => void;
}) {
  const [handoffTarget, setHandoffTarget] = useState("");
  const activeHandoffTarget = handoffTargets.some((s) => s.id === handoffTarget)
    ? handoffTarget
    : (handoffTargets[0]?.id ?? "");
  const canUndo = Boolean(
    action?.id && isSafelyUndoable(action.action, action.reversible, action.result),
  );
  const canOpen = canOpenSession(current);
  const canAttach = canAttachPersistentGoal(current);
  const ledger = partitionLedgerDecisions(ledgerDecisions);
  const deadline = goalDeadlineCopy(goal?.deadline);
  const actionName = recordedActionLabel(action);
  const actionWhy = actionExplanation(action);
  const handoffCopy = action?.action === "FRESH_HANDOFF"
    ? handoffAssimilationPresentation(handoffStatus)
    : null;

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
          <p>{goal?.objective || (current ? meaningfulEvidence(current) : status.detail)}</p>
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
        <label className="session-picker">
          OpenCode or other agent session
          <select value={current?.id || ""} disabled={!onSelectSession}
            onChange={(event) => onSelectSession?.(event.target.value)}>
            {!current ? <option value="" disabled>Choose a worker</option> : null}
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {titleCase(session.harness_type)} · {session.label || session.id} · {humanize(session.status)}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <details className="goal-options" key={goal ? "supervising" : "setup"} open={Boolean(goal)}>
      <summary>Activity and evidence</summary>
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
            {current ? (
              <div>
                <dt>Supervisor review allowance</dt>
                <dd>{supervisorReviewAllowanceCopy(current, canonicalStateAvailable)}</dd>
              </div>
            ) : null}
            <div>
              <dt>Adapter control</dt>
              <dd>
                {current?.capabilities?.support_label
                  ? `${titleCase(String(current.capabilities.support_label))} · `
                  : "Unprobed · "}
                {canOpen ? "existing-window focus available" : "window focus unavailable"}
              </dd>
            </div>
            {observationGapCopy(current) ? (
              <div>
                <dt>Observation gap</dt>
                <dd className="stall-warning">{observationGapCopy(current)}</dd>
              </div>
            ) : null}
            {isReplaySession(current) ? (
              <div>
                <dt>Session origin</dt>
                <dd><span className="replay-badge">Recorded replay</span> · not live worker control</dd>
              </div>
            ) : current && isLiveWorkerSession(current) ? (
              <div>
                <dt>Session origin</dt>
                <dd><span className="replay-badge live-badge">Live worker</span> · observed through the {titleCase(current.harness_type)} transport</dd>
              </div>
            ) : null}
          </dl>
          {current ? (
            <div className="button-row">
              <button type="button" className="solid" onClick={onOpen} disabled={!canOpen}>
                {canOpen ? "Open agent" : "Open unavailable"}
              </button>
              <button type="button" className="ghost" onClick={onPause} disabled={!sessionActionsAvailable}
                title={!sessionActionsAvailable ? "Available in the authenticated PEX desktop app when session state is current" : undefined}>
                {current.supervision_paused ? "Resume supervision" : "Pause supervision"}
              </button>
            </div>
          ) : null}
          {current && handoffTargets.length > 0 ? (
            <div className="handoff-row">
              <label className="handoff-label">
                Hand the durable goal context to
                <select
                  value={activeHandoffTarget}
                  onChange={(event) => setHandoffTarget(event.target.value)}
                  disabled={handoffBusy}
                >
                  {handoffTargets.map((target) => (
                    <option key={target.id} value={target.id}>
                      {titleCase(target.harness_type)} · {target.id.split(":").pop()}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="ghost"
                disabled={!sessionActionsAvailable || handoffBusy || !activeHandoffTarget}
                title={!sessionActionsAvailable ? "Available in the authenticated PEX desktop app or the demo operator bridge" : "PEX reserves a content-addressed context bundle, injects it into the target, and monitors assimilation"}
                onClick={() => activeHandoffTarget && onHandoff?.(activeHandoffTarget)}
              >
                {handoffBusy ? "Handing off…" : "Hand off →"}
              </button>
            </div>
          ) : null}
          {!current ? (
            <p className="empty-copy">
              PEX lists already-open Cursor, Codex, OpenCode, Hermes, and Claude Code
              sessions without restarting them. A closed harness stays unavailable until
              its app or API is actually running.
            </p>
          ) : null}
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
          {handoffCopy ? (
            <div className="result-line" role="status">
              <span>Context handoff</span>
              <strong>{handoffCopy.label}</strong>
              <p>{handoffCopy.detail}</p>
            </div>
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
          {action ? (
            <p className="result-line">
              <span>Supervisor inference</span>
              {supervisorInferenceReceipt(action)}
            </p>
          ) : null}
          {sessionInterventions.length > 1 ? (
            <div className="supervision-log">
              <small>Supervision log · {sessionInterventions.length} recorded</small>
              <ul>
                {sessionInterventions.map((item) => (
                  <li key={item.id} title={interventionLogDetail(item)}>
                    <span>{interventionLogLabel(item)}</span>
                    {interventionLogResult(item) ? (
                      <em>{interventionLogResult(item)}</em>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
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

      </details>
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
              {goalCompletionCopy(goal, completion, canonicalStateAvailable)}
            </p>
            <p className="goal-help">{goal.objective}</p>
            {verificationReport ? (
              <details className="goal-options verification-report" open>
              <summary>Independent claim verification</summary>
              <p className="verification-summary">{verificationSummaryLine(verificationReport)}</p>
              {verificationReport.claims.length ? (
                <ul className="verification-timeline">
                  {verificationReport.claims.map((claim) => (
                    <li key={`${claim.at}-${claim.action}`}>
                      <span className={`verification-verdict verdict-${claim.status || "observed"}`}>
                        {verificationVerdictLabel(claim.status)}
                      </span>
                      <span className="verification-claim">
                        {humanize(claim.action)} · {new Date(claim.at).toLocaleTimeString()}
                      </span>
                      {claim.statements.length ? (
                        <span className="verification-statements">
                          {claim.statements.map((statement) => (
                            <q key={statement}>{statement}</q>
                          ))}
                        </span>
                      ) : null}
                      {claim.flaggedFiles.length ? (
                        <span className="verification-flagged">
                          {claim.flaggedFiles.map((file) => (
                            <FlaggedFileDiff
                              key={`${claim.at}-${claim.action}-${file}`}
                              file={file}
                              onFetchAcceptanceDiff={onFetchAcceptanceDiff}
                            />
                          ))}
                        </span>
                      ) : null}
                      {claim.evidence.length ? (
                        <span className="verification-evidence">
                          {claim.evidence.map((item) => (
                            <code key={item}>{item}</code>
                          ))}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              {onExportReport || onExportEvidencePack ? (
                <div className="button-row">
                  {onExportReport ? (
                    <button
                      type="button"
                      className="ghost"
                      onClick={onExportReport}
                      disabled={exportingReport}
                    >
                      {exportingReport ? "Exporting…" : "Export report"}
                    </button>
                  ) : null}
                  {onExportEvidencePack ? (
                    <button
                      type="button"
                      className="ghost"
                      title="Download the hash-chained evidence bundle — verify offline with scripts/verify_pack.py"
                      onClick={onExportEvidencePack}
                      disabled={exportingPack}
                    >
                      {exportingPack ? "Packing…" : "Evidence pack"}
                    </button>
                  ) : null}
                </div>
              ) : null}
              {packVerification && goal && packVerification.goalId === goal.id ? (
                <details className="pack-verification">
                  <summary>
                    {packVerification.checks.some((line) => line.startsWith("FAIL"))
                      ? `${packVerification.checks.filter((line) => line.startsWith("FAIL")).length} checks failed — re-verify with scripts/verify_pack.py`
                      : `${packVerification.checks.filter((line) => line.startsWith("PASS")).length}/${packVerification.checks.length} checks recomputed in this browser`}
                  </summary>
                  <ul>
                    {packVerification.checks.map((line) => (
                      <li
                        key={line}
                        className={`pack-check pack-check-${line.split(" ", 1)[0].toLowerCase()}`}
                      >
                        {line}
                      </li>
                    ))}
                  </ul>
                  <p className="note">
                    Digests recomputed locally — independent of the bridge. Proves this
                    bundle is internally consistent; it does not prove a live worker ran.
                  </p>
                </details>
              ) : null}
              </details>
            ) : null}
            <details className="goal-options">
            <summary>Checks and details</summary>
            <div className="goal-boundaries">
              <Boundary label="Acceptance" values={goal.acceptance_criteria} />
              {deadline ? <Boundary label="Deadline" values={[deadline]} /> : null}
              <Boundary label="Constraints" values={goal.constraints} />
              <Boundary label="Forbidden outcomes" values={goal.forbidden_outcomes} />
              <Boundary label="Non-goals" values={goal.non_goals} />
              <Boundary label="Preferences" values={goal.preferences} />
              <Boundary label="Required evidence" values={goal.evidence_requirements} />
              <Boundary label="Decisions" values={ledger.decisions.map((item) => item.statement)} />
              <Boundary label="Rejected approaches" values={ledger.rejected.map((item) => item.statement)} />
              <Boundary label="Unresolved questions" values={ledger.unresolved.map((item) => item.statement)} />
            </div>
            </details>
            {onEditGoal ? (
              <div className="button-row">
                <button type="button" className="ghost" onClick={onEditGoal} disabled={savingGoal || !goalActionsAvailable}>
                  Edit goal
                </button>
              </div>
            ) : null}
          </>
        ) : (
          <p className="empty-copy">{canAttach
            ? "Give PEX a goal to supervise this session."
            : "This worker is observe-only. Connect OpenCode or an isolated Codex session before attaching a goal."}</p>
        )}
        <details
          className="goal-editor"
          key={`${current?.id || "none"}-${goalEditorRevision}-${editingGoal ? "editing" : "create"}`}
          {...(editingGoal ? { open: true } : {})}
        >
          <summary>
            {editingGoal
              ? "Edit goal"
              : goal
                ? "Create another goal"
                : "Create goal"}
          </summary>
          <GoalEditor
            draft={goalDraft}
            saving={savingGoal}
            disabled={!goalActionsAvailable}
            willAttach={canAttach && !editingGoal}
            editing={editingGoal}
            projectIdentity={current?.project_id || current?.cwd || undefined}
            overrideMode={goalOverrideMode}
            onFillExample={onFillExample}
            onChange={onGoalChange}
            onSubmit={onCreateGoal}
            onCancel={onCancelEdit}
            onOverrideModeChange={onGoalOverrideModeChange}
          />
        </details>
        {note ? <p className="note" role="status" aria-live="polite">{note}</p> : null}
      </section>

      <AskPex
        question={question}
        answer={answer}
        asking={asking}
        inputRef={askInput}
        questions={canonicalStateAvailable ? askPexQuestions(sessions, action, current) : []}
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

function FlaggedFileDiff({
  file,
  onFetchAcceptanceDiff,
}: {
  file: string;
  onFetchAcceptanceDiff?: (path: string) => Promise<AcceptanceDiff>;
}) {
  const [state, setState] = useState<
    | { kind: "closed" }
    | { kind: "loading" }
    | { kind: "open"; diff: AcceptanceDiff }
    | { kind: "error"; message: string }
  >({ kind: "closed" });

  if (!onFetchAcceptanceDiff) {
    return <span className="verification-flag">{file}</span>;
  }

  const open = () => {
    setState({ kind: "loading" });
    onFetchAcceptanceDiff(file)
      .then((diff) => setState({ kind: "open", diff }))
      .catch((error: unknown) =>
        setState({
          kind: "error",
          message: error instanceof Error ? error.message : String(error),
        }),
      );
  };

  return (
    <span className="verification-flag">
      <button
        type="button"
        className="flag-file"
        title={
          state.kind === "open"
            ? "Hide the sealed-baseline diff"
            : "Diff the sealed baseline against the bytes on disk now"
        }
        onClick={() => (state.kind === "open" ? setState({ kind: "closed" }) : open())}
      >
        {file}
        <span className="flag-diff-hint">
          {state.kind === "open" ? "hide diff" : state.kind === "loading" ? "loading…" : "diff"}
        </span>
      </button>
      {state.kind === "error" ? (
        <span className="flag-diff-note">No baseline diff: {state.message}</span>
      ) : null}
      {state.kind === "open" ? <AcceptanceDiffView diff={state.diff} /> : null}
    </span>
  );
}

function AcceptanceDiffView({ diff }: { diff: AcceptanceDiff }) {
  const baseline = diff.baseline;
  const flagged = diff.flagged;
  const current = diff.current;
  const baselineText = baseline?.text;
  const flaggedText = flagged?.text;
  // A file injected after the seal has no baseline side — the honest render
  // is an additions-only diff of the bytes PEX flagged, not "no diff".
  const addedAfterSeal =
    baseline?.state === "not_in_baseline" || baseline?.present === false;
  if (baseline?.state === "digest_only" || (baselineText == null && !addedAfterSeal)) {
    return (
      <span className="flag-diff-note">
        {baseline?.state === "digest_only"
          ? "Baseline sealed digest-only — this goal predates content capture."
          : "Baseline text unavailable."}
      </span>
    );
  }
  const targetText = flaggedText ?? current?.text;
  const flaggedSuffix = flagged?.captured_at
    ? ` at ${new Date(flagged.captured_at).toLocaleTimeString()}`
    : "";
  const targetLabel = addedAfterSeal
    ? `not in sealed baseline → ${
        flaggedText != null ? `bytes PEX flagged${flaggedSuffix}` : "current disk bytes"
      }`
    : flaggedText != null
      ? `sealed baseline → bytes PEX flagged${flaggedSuffix}`
      : "sealed baseline → current disk bytes";
  if (targetText == null) {
    return (
      <span className="flag-diff-note">
        {addedAfterSeal
          ? "Appeared after the sealed baseline — no bytes captured."
          : current?.state === "missing"
            ? "The sealed file no longer exists on disk."
            : "Flagged/current bytes unavailable — diff cannot be shown."}
      </span>
    );
  }
  if (baselineText != null && baselineText === targetText) {
    return <span className="flag-diff-note">Restored — identical to the sealed baseline.</span>;
  }
  const lines = unifiedDiff(addedAfterSeal ? "" : baselineText ?? "", targetText).filter(
    (line, index, all) =>
      line.type !== "same" ||
      all.some(
        (other, otherIndex) =>
          other.type !== "same" && Math.abs(otherIndex - index) <= 3,
      ),
  );
  return (
    <span className="flag-diff">
      <span className="flag-diff-label">{targetLabel}</span>
      <pre className="flag-diff-pre">
        {lines.map((line, index) => (
          <code key={index} className={`diff-${line.type}`}>
            {line.type === "add" ? "+ " : line.type === "del" ? "− " : "  "}
            {line.text}
            {"\n"}
          </code>
        ))}
      </pre>
    </span>
  );
}

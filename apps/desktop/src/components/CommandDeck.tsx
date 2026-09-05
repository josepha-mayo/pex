import { useEffect, useMemo, useRef, useState } from "react";

import { AskPex } from "./AskPex";
import { ProjectIdentityPanel } from "./ProjectIdentityPanel";
import { prepareFreeformDecision } from "../decisionContract";
import type {
  AdapterRow,
  AttentionMetrics,
  BenchState,
  ContextItem,
  DecisionFeedback,
  DeckView,
  Fingerprint,
  Goal,
  HandoffAssimilationStatus,
  HumanDecisionChoice,
  Intervention,
  ProjectIdentityConflictPage,
  ProjectIdentityFeedback,
  ProjectIdentityStatusView,
  SessionRow,
} from "../types";
import {
  askPexQuestions,
  canOpenSession,
  contextHealthCopy,
  contextItemMarks,
  fingerprintCompletionReliability,
  fingerprintFailureModes,
  fingerprintPrematureRate,
  fingerprintStrengths,
  fingerprintSuggestedConfig,
  fingerprintTokenBehavior,
  humanize,
  isPendingHumanDecision,
  isPendingLifecycleDecision,
  isPendingPermissionDecision,
  isPendingRequestedHumanDecision,
  isSafelyUndoable,
  isStale,
  meaningfulEvidence,
  permissionRequestDetails,
  type ProjectIdentityResolutionAttempt,
  requestedHumanDecisionDetails,
  starterHarnessInventoryCopy,
  titleCase,
} from "../viewModel";

const VIEWS: Array<{ id: DeckView; label: string; hint: string }> = [
  { id: "now", label: "Now", hint: "live work" },
  { id: "decisions", label: "Decisions", hint: "needs you" },
  { id: "context", label: "Context", hint: "durable state" },
  { id: "interventions", label: "Interventions", hint: "audit trail" },
  { id: "agents", label: "Agents", hint: "fingerprints" },
  { id: "bench", label: "Bench", hint: "verified runs" },
];

function sessionObservationCopy(session: SessionRow, degraded: boolean): string {
  const parsed = session.last_activity ? Date.parse(session.last_activity) : Number.NaN;
  const observed = Number.isFinite(parsed)
    ? new Date(parsed).toLocaleString()
    : "observation time unavailable";
  return degraded ? `Cached · last observed ${observed}` : `Last observed ${observed}`;
}

function isUnresolvedAskHuman(item: Intervention): boolean {
  return (
    item.action_taken === "ASK_HUMAN" &&
    item.policy_verdict === "ask_human" &&
    !item.outcome &&
    item.helped == null
  );
}

function isCurrentGeneralDecision(item: Intervention, sessions: SessionRow[]): boolean {
  return (
    isUnresolvedAskHuman(item) &&
    sessions.some(
      (session) => session.id === item.session_id && session.status === "needs_decision",
    )
  );
}

export function CommandDeck({
  activeView,
  sessions,
  goals,
  interventions,
  pendingInterventions,
  pendingInterventionsTruncated,
  auditInterventions,
  handoffAssimilation,
  attentionMetrics,
  contextItems,
  fingerprints,
  adapters,
  bench,
  selectedSessionId,
  loading,
  error,
  mutationsAvailable = true,
  auditMutationsAvailable = true,
  decisionFeedback,
  identityConflicts,
  identityConflictsLoading,
  identityConflictsError,
  identitySelectedProjectId,
  identityStatus,
  identityLoading,
  identityError,
  identityResolving,
  identityFeedback,
  question,
  answer,
  asking,
  onView,
  onSelectSession,
  onOpenSession,
  onPauseSession,
  onUndo,
  onResolveDecision,
  onSelectIdentityProject,
  onResolveIdentity,
  onLoadMoreIdentityConflicts,
  onLoadMoreIdentityCandidates,
  onQuestion,
  onAsk,
  onAskPrompt,
}: {
  activeView: DeckView;
  sessions: SessionRow[];
  goals: Goal[];
  interventions: Intervention[];
  pendingInterventions: Intervention[];
  pendingInterventionsTruncated: boolean;
  auditInterventions: Intervention[];
  handoffAssimilation: Record<string, HandoffAssimilationStatus | "unreachable">;
  attentionMetrics: AttentionMetrics | null;
  contextItems: ContextItem[];
  fingerprints: Fingerprint[];
  adapters: AdapterRow[];
  bench: BenchState;
  selectedSessionId?: string;
  loading: boolean;
  error?: string | null;
  mutationsAvailable?: boolean;
  auditMutationsAvailable?: boolean;
  decisionFeedback: DecisionFeedback | null;
  identityConflicts: ProjectIdentityConflictPage | null;
  identityConflictsLoading: boolean;
  identityConflictsError: string | null;
  identitySelectedProjectId: string;
  identityStatus: ProjectIdentityStatusView | null;
  identityLoading: boolean;
  identityError: string | null;
  identityResolving: boolean;
  identityFeedback: ProjectIdentityFeedback | null;
  question: string;
  answer: string;
  asking: boolean;
  onView: (view: DeckView) => void;
  onSelectSession: (sessionId: string) => void;
  onOpenSession: (session: SessionRow) => void;
  onPauseSession: (session: SessionRow) => void;
  onUndo: (intervention: Intervention) => void;
  onResolveDecision: (intervention: Intervention, decision: HumanDecisionChoice) => void;
  onSelectIdentityProject: (legacyProjectId: string) => void;
  onResolveIdentity: (attempt: ProjectIdentityResolutionAttempt) => void;
  onLoadMoreIdentityConflicts: () => void;
  onLoadMoreIdentityCandidates: () => void;
  onQuestion: (value: string) => void;
  onAsk: (event: React.FormEvent) => void;
  onAskPrompt?: (prompt: string) => void;
}) {
  const pendingDecisions = pendingInterventions.filter(
    (item) => isPendingHumanDecision(item) || isCurrentGeneralDecision(item, sessions),
  );
  const explainedSessions = new Set(pendingDecisions.map((item) => item.session_id));
  const currentDecisionCount = attentionMetrics
    ? attentionMetrics.current_pending.count +
      attentionMetrics.current_pending.unexplained_session_count
    : pendingDecisions.length +
      sessions.filter(
        (item) => item.status === "needs_decision" && !explainedSessions.has(item.id),
      ).length;
  const attentionCount = currentDecisionCount + (identityConflicts?.total || 0);

  return (
    <section
      className="deck-shell surface-focus-target"
      aria-label="PEX command deck"
      data-surface-root="deck"
      tabIndex={-1}
    >
      <aside className="deck-nav" aria-label="Command deck views">
        <div className="deck-nav-title">
          <span className="status-dot" aria-hidden="true" />
          <span>
            <strong>Command deck</strong>
            <small>{error ? "Cached state · degraded" : "Canonical local state"}</small>
          </span>
        </div>
        {VIEWS.map((view) => (
          <button
            key={view.id}
            type="button"
            className={activeView === view.id ? "active" : ""}
            aria-current={activeView === view.id ? "page" : undefined}
            onClick={() => onView(view.id)}
          >
            <span>{view.label}</span>
            <small>{view.id === "decisions" ? `${attentionCount} waiting` : view.hint}</small>
          </button>
        ))}
        <div className="deck-integrity-note">
          <strong>Evidence before action</strong>
          <span>Unsupported data stays visibly unavailable.</span>
        </div>
      </aside>

      <div className="deck-main">
        <header className="deck-heading">
          <div>
            <p className="eyebrow">{VIEWS.find((view) => view.id === activeView)?.hint}</p>
            <h1>{titleCase(activeView)}</h1>
          </div>
          <p role="status" aria-live="polite">
            {loading ? "Refreshing live state…" : error || viewDescription(activeView)}
          </p>
        </header>

        <div className="deck-view">
          {activeView === "now" ? (
            <NowView
              sessions={sessions}
              goals={goals}
              interventions={interventions}
              attentionMetrics={attentionMetrics}
              degraded={Boolean(error)}
              mutationsAvailable={mutationsAvailable}
              onSelect={onSelectSession}
              onOpen={onOpenSession}
              onPause={onPauseSession}
            />
          ) : null}
          {activeView === "decisions" ? (
            <DecisionsView
              sessions={sessions}
              interventions={pendingInterventions}
              itemsTruncated={pendingInterventionsTruncated}
              feedback={decisionFeedback}
              identityConflicts={identityConflicts}
              identityConflictsLoading={identityConflictsLoading}
              identityConflictsError={identityConflictsError}
              identitySelectedProjectId={identitySelectedProjectId}
              identityStatus={identityStatus}
              identityLoading={identityLoading}
              identityError={identityError}
              identityResolving={identityResolving}
              identityFeedback={identityFeedback}
              mutationsAvailable={mutationsAvailable}
              onOpen={onOpenSession}
              onResolve={onResolveDecision}
              onSelectIdentityProject={onSelectIdentityProject}
              onResolveIdentity={onResolveIdentity}
              onLoadMoreIdentityConflicts={onLoadMoreIdentityConflicts}
              onLoadMoreIdentityCandidates={onLoadMoreIdentityCandidates}
            />
          ) : null}
          {activeView === "context" ? (
            <ContextView
              goals={goals}
              items={contextItems}
              sessions={sessions}
              selectedSessionId={selectedSessionId}
            />
          ) : null}
          {activeView === "interventions" ? (
            <InterventionsView
              interventions={auditInterventions}
              handoffAssimilation={handoffAssimilation}
              mutationsAvailable={auditMutationsAvailable}
              onUndo={onUndo}
            />
          ) : null}
          {activeView === "agents" ? (
            <AgentsView sessions={sessions} fingerprints={fingerprints} adapters={adapters} />
          ) : null}
          {activeView === "bench" ? <BenchView bench={bench} /> : null}
        </div>

        <AskPex
          compact
          question={question}
          answer={answer}
          asking={asking}
          questions={error ? [] : askPexQuestions(sessions, interventions[0])}
          onQuestion={onQuestion}
          onSubmit={onAsk}
          onAskPrompt={onAskPrompt}
        />
      </div>
    </section>
  );
}

function NowView({
  sessions,
  goals,
  interventions,
  attentionMetrics,
  degraded,
  mutationsAvailable,
  onSelect,
  onOpen,
  onPause,
}: {
  sessions: SessionRow[];
  goals: Goal[];
  interventions: Intervention[];
  attentionMetrics: AttentionMetrics | null;
  degraded: boolean;
  mutationsAvailable: boolean;
  onSelect: (sessionId: string) => void;
  onOpen: (session: SessionRow) => void;
  onPause: (session: SessionRow) => void;
}) {
  const goalById = useMemo(() => new Map(goals.map((goal) => [goal.id, goal])), [goals]);
  const actionCount = useMemo(() => {
    const count = new Map<string, number>();
    for (const item of interventions) {
      if (item.action_taken === "NOOP") continue;
      count.set(item.session_id, (count.get(item.session_id) || 0) + 1);
    }
    return count;
  }, [interventions]);

  return (
    <div className="now-layout">
      <dl className="attention-metrics" aria-label="Human attention metrics">
        <div>
          <dt>Human interventions</dt>
          <dd>{attentionMetrics?.human_interventions.value ?? "Not fully measured"}</dd>
          <small>
            {attentionMetrics
              ? `${attentionMetrics.human_interventions.observed_count} authenticated actions recorded; coverage incomplete`
              : "Backend aggregate unavailable"}
          </small>
        </div>
        <div>
          <dt>Human active seconds</dt>
          <dd>{attentionMetrics?.human_active_seconds.value ?? "Not measured"}</dd>
          <small>
            {attentionMetrics
              ? "Consent-gated focus timing is not configured"
              : "Backend aggregate unavailable"}
          </small>
        </div>
        <div>
          <dt>Resolved decisions</dt>
          <dd>{attentionMetrics?.decisions.resolved ?? "Unavailable"}</dd>
          <small>
            {attentionMetrics
              ? `${attentionMetrics.decisions.requested} requests in durable history`
              : "Backend aggregate unavailable"}
          </small>
        </div>
        <div>
          <dt>Unnecessary alert rate</dt>
          <dd>{attentionMetrics?.unnecessary_alert_rate.value ?? "Not measured"}</dd>
          <small>
            {attentionMetrics
              ? `${attentionMetrics.unnecessary_alert_rate.denominator} alerts adjudicated`
              : "Backend aggregate unavailable"}
          </small>
        </div>
        <div>
          <dt>Avg auto-resolution confidence</dt>
          <dd>{attentionMetrics?.average_auto_resolution_confidence.value ?? "Not measured"}</dd>
          <small>
            {attentionMetrics
              ? `${attentionMetrics.average_auto_resolution_confidence.sample_count} eligible samples`
              : "Backend aggregate unavailable"}
          </small>
        </div>
        <div>
          <dt>Reversals of PEX actions</dt>
          <dd>{attentionMetrics?.reversals.completed ?? "Unavailable"}</dd>
          <small>
            {attentionMetrics
              ? `${attentionMetrics.reversals.attempted} attempts · ${attentionMetrics.reversals.delivery_uncertain} uncertain`
              : "Backend aggregate unavailable"}
          </small>
        </div>
      </dl>
      <p className="attention-basis">
        {attentionMetrics
          ? `All durable local history · exact aggregate · as of ${new Date(attentionMetrics.window.as_of).toLocaleString()} · not benchmark evidence`
          : "Attention metrics are unavailable; recent intervention rows are not used as a substitute."}
      </p>
      <div className="now-grid">
      {!sessions.length ? (
        <EmptyState
          title="No active sessions"
          body="Start a supported worker normally. PEX will not manufacture one for the deck."
        />
      ) : null}
      {sessions.map((session) => {
        const goal = goalById.get(session.goal_id || "");
        const attention = session.status === "needs_decision";
        const canOpen = canOpenSession(session);
        return (
          <article className={`session-card ${attention ? "attention" : ""}`} key={session.id}>
            <div className="card-heading">
              <span>
                <small>{titleCase(session.harness_type)} {session.model ? `· ${session.model}` : ""}</small>
                <strong>{session.label || titleCase(session.harness_type)}</strong>
              </span>
              <span className={`state-pill state-${session.status}`}>{humanize(session.status)}</span>
            </div>
            <p className="goal-line">{goal ? goal.objective : "No persistent goal attached."}</p>
            <dl className="now-facts">
              <div>
                <dt>Latest state / evidence</dt>
                <dd>{meaningfulEvidence(session)}</dd>
              </div>
              <div>
                <dt>Recent PEX actions</dt>
                <dd>{actionCount.get(session.id) || 0}</dd>
              </div>
              <div>
                <dt>Attention</dt>
                <dd>{attention ? "Human judgment required" : "Not required"}</dd>
              </div>
              <div>
                <dt>Freshness</dt>
                <dd>{sessionObservationCopy(session, degraded)}</dd>
              </div>
            </dl>
            <div className="button-row">
              <button type="button" className="solid" disabled={!canOpen} onClick={() => onOpen(session)}>
                {canOpen ? "Open agent" : "Open unavailable"}
              </button>
              <button type="button" className="ghost" onClick={() => onSelect(session.id)}>Inspect</button>
              <button type="button" className="ghost" disabled={!mutationsAvailable} onClick={() => onPause(session)}>
                {session.supervision_paused ? "Resume" : "Pause"}
              </button>
            </div>
          </article>
        );
      })}
      </div>
    </div>
  );
}

function DecisionsView({
  sessions,
  interventions,
  itemsTruncated,
  feedback,
  identityConflicts,
  identityConflictsLoading,
  identityConflictsError,
  identitySelectedProjectId,
  identityStatus,
  identityLoading,
  identityError,
  identityResolving,
  identityFeedback,
  mutationsAvailable,
  onOpen,
  onResolve,
  onSelectIdentityProject,
  onResolveIdentity,
  onLoadMoreIdentityConflicts,
  onLoadMoreIdentityCandidates,
}: {
  sessions: SessionRow[];
  interventions: Intervention[];
  itemsTruncated: boolean;
  feedback: DecisionFeedback | null;
  identityConflicts: ProjectIdentityConflictPage | null;
  identityConflictsLoading: boolean;
  identityConflictsError: string | null;
  identitySelectedProjectId: string;
  identityStatus: ProjectIdentityStatusView | null;
  identityLoading: boolean;
  identityError: string | null;
  identityResolving: boolean;
  identityFeedback: ProjectIdentityFeedback | null;
  mutationsAvailable: boolean;
  onOpen: (session: SessionRow) => void;
  onResolve: (intervention: Intervention, decision: HumanDecisionChoice) => void;
  onSelectIdentityProject: (legacyProjectId: string) => void;
  onResolveIdentity: (attempt: ProjectIdentityResolutionAttempt) => void;
  onLoadMoreIdentityConflicts: () => void;
  onLoadMoreIdentityCandidates: () => void;
}) {
  const waitingSessions = sessions.filter((item) => item.status === "needs_decision");
  const permissionActions = interventions.filter(isPendingPermissionDecision);
  const lifecycleActions = interventions.filter(isPendingLifecycleDecision);
  const requestedActions = interventions.filter(isPendingRequestedHumanDecision);
  const generalActions = interventions.filter((item) =>
    !isPendingRequestedHumanDecision(item) && isCurrentGeneralDecision(item, sessions)
  );
  const feedbackIsInline = feedback != null && [
    ...permissionActions,
    ...lifecycleActions,
    ...requestedActions,
  ]
    .some((item) => item.id === feedback.interventionId);
  const explainedSessions = new Set(
    [...permissionActions, ...lifecycleActions, ...requestedActions, ...generalActions]
      .map((item) => item.session_id),
  );
  const unexplainedSessions = waitingSessions.filter((item) => !explainedSessions.has(item.id));

  return (
    <div className="decision-list">
      {itemsTruncated ? (
        <p className="inline-note" role="status">
          The current-authority decision count is exact, but this view shows only the newest
          decision page. Older decisions remain durable and are not counted as absent.
        </p>
      ) : null}
      <ProjectIdentityPanel
        conflicts={identityConflicts}
        conflictsLoading={identityConflictsLoading}
        conflictsError={identityConflictsError}
        selectedLegacyProjectId={identitySelectedProjectId}
        status={identityStatus}
        loading={identityLoading}
        error={identityError}
        resolving={identityResolving}
        feedback={identityFeedback}
        onSelectProject={onSelectIdentityProject}
        onResolve={onResolveIdentity}
        onLoadMoreConflicts={onLoadMoreIdentityConflicts}
        onLoadMoreCandidates={onLoadMoreIdentityCandidates}
      />
      {feedback && !feedbackIsInline ? (
        <p
          className={`decision-feedback decision-feedback-${feedback.state}`}
          role={feedback.state === "error" ? "alert" : "status"}
          aria-live={feedback.state === "error" ? "assertive" : "polite"}
        >
          {feedback.message}
        </p>
      ) : null}
      {permissionActions.map((item) => {
        const session = sessions.find((row) => row.id === item.session_id);
        const details = permissionRequestDetails(item);
        const feedbackForItem = feedback?.interventionId === item.id ? feedback : null;
        const busy = !mutationsAvailable || feedback?.state === "submitting";
        const responseMode = String(session?.capabilities?.permission_response_mode || "none");
        const canRespondLater = responseMode === "async" || responseMode === "both";
        const canAllow = canRespondLater && session?.capabilities?.approve === true;
        const canDeny = canRespondLater && session?.capabilities?.deny === true;
        const evidenceId = `permission-evidence-${item.id}`;
        const statusId = `permission-status-${item.id}`;
        return (
          <article className="decision-card permission-decision-card" key={item.id}>
            <span className="decision-mark" aria-hidden="true">!</span>
            <div>
              <p className="eyebrow">
                {session ? titleCase(session.harness_type) : "Missing session"} · {humanize(item.risk || "unknown risk")}
              </p>
              <h2>{permissionTitle(details)}</h2>
              <dl className="permission-facts" id={evidenceId}>
                <div>
                  <dt>Exact request</dt>
                  <dd>
                    {details.command ? <code>{details.command}</code> : (
                      details.toolName || details.approvalMethod || "No command or tool was recorded."
                    )}
                  </dd>
                </div>
                {details.filePaths.length ? (
                  <div>
                    <dt>Paths</dt>
                    <dd>{details.filePaths.join(", ")}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Observed evidence</dt>
                  <dd>
                    {item.evidence?.length ? (
                      <ul className="permission-evidence-list">
                        {item.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}
                      </ul>
                    ) : "No additional evidence was recorded."}
                  </dd>
                </div>
              </dl>
              <p className="decision-rationale">
                {item.proposed_action?.rationale || "Local policy did not authorize an automatic response."}
              </p>
              {feedbackForItem ? (
                <p
                  id={statusId}
                  className={`decision-inline-status decision-inline-${feedbackForItem.state}`}
                  role={feedbackForItem.state === "error" ? "alert" : "status"}
                >
                  {feedbackForItem.message}
                </p>
              ) : null}
            </div>
            <div className="decision-controls" role="group" aria-label="Resolve permission request">
              {canDeny ? (
                <button
                  type="button"
                  className="solid decision-deny"
                  disabled={busy}
                  aria-describedby={`${evidenceId}${feedbackForItem ? ` ${statusId}` : ""}`}
                  onClick={() => onResolve(item, "deny")}
                >
                  {feedbackForItem?.state === "submitting" && feedbackForItem.decision === "deny"
                    ? "Denying…"
                    : "Deny"}
                </button>
              ) : null}
              {canAllow ? (
                <button
                  type="button"
                  className="ghost decision-allow"
                  disabled={busy}
                  aria-describedby={`${evidenceId}${feedbackForItem ? ` ${statusId}` : ""}`}
                  onClick={() => onResolve(item, "allow")}
                >
                  {feedbackForItem?.state === "submitting" && feedbackForItem.decision === "allow"
                    ? "Allowing…"
                    : "Allow"}
                </button>
              ) : null}
              {!canAllow && !canDeny ? (
                <p className="permission-unsupported">
                  This hook cannot accept a later PEX response. Decide in the active harness prompt.
                </p>
              ) : null}
              {session && canOpenSession(session) ? (
                <button type="button" className="text-button" onClick={() => onOpen(session)}>
                  Open agent
                </button>
              ) : null}
            </div>
          </article>
        );
      })}
      {lifecycleActions.map((item) => {
        const session = sessions.find((row) => row.id === item.session_id);
        const feedbackForItem = feedback?.interventionId === item.id ? feedback : null;
        const busy = !mutationsAvailable || feedback?.state === "submitting";
        const evidenceId = `lifecycle-evidence-${item.id}`;
        const statusId = `lifecycle-status-${item.id}`;
        return (
          <article className="decision-card permission-decision-card" key={item.id}>
            <span className="decision-mark" aria-hidden="true">!</span>
            <div>
              <p className="eyebrow">
                Lifecycle · {humanize(item.risk || "unknown risk")}
              </p>
              <h2>{lifecycleTitle(item.action_taken)}</h2>
              <dl className="permission-facts" id={evidenceId}>
                <div>
                  <dt>Exact action</dt>
                  <dd><code>{lifecycleSummary(item)}</code></dd>
                </div>
                <div>
                  <dt>Observed evidence</dt>
                  <dd>
                    {item.evidence?.length ? (
                      <ul className="permission-evidence-list">
                        {item.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}
                      </ul>
                    ) : "No evidence was recorded; decline or inspect the worker."}
                  </dd>
                </div>
              </dl>
              <p className="decision-rationale">
                {item.proposed_action?.rationale || "Local policy requires explicit human authority."}
              </p>
              {feedbackForItem ? (
                <p
                  id={statusId}
                  className={`decision-inline-status decision-inline-${feedbackForItem.state}`}
                  role={feedbackForItem.state === "error" ? "alert" : "status"}
                >
                  {feedbackForItem.message}
                </p>
              ) : null}
            </div>
            <div className="decision-controls" role="group" aria-label="Resolve lifecycle request">
              <button
                type="button"
                className="solid decision-deny"
                disabled={busy}
                aria-describedby={`${evidenceId}${feedbackForItem ? ` ${statusId}` : ""}`}
                onClick={() => onResolve(item, "deny")}
              >
                {feedbackForItem?.state === "submitting" && feedbackForItem.decision === "deny"
                  ? "Declining…"
                  : "Decline"}
              </button>
              <button
                type="button"
                className="ghost decision-allow"
                disabled={busy}
                aria-describedby={`${evidenceId}${feedbackForItem ? ` ${statusId}` : ""}`}
                onClick={() => onResolve(item, "allow")}
              >
                {feedbackForItem?.state === "submitting" && feedbackForItem.decision === "allow"
                  ? "Approving…"
                  : "Approve"}
              </button>
              {session && canOpenSession(session) ? (
                <button type="button" className="text-button" onClick={() => onOpen(session)}>
                  Open agent
                </button>
              ) : null}
            </div>
          </article>
        );
      })}
      {requestedActions.map((item) => (
        <RequestedDecisionCard
          key={item.id}
          intervention={item}
          session={sessions.find((row) => row.id === item.session_id)}
          feedback={feedback?.interventionId === item.id ? feedback : null}
          busy={!mutationsAvailable || feedback?.state === "submitting"}
          onOpen={onOpen}
          onResolve={onResolve}
        />
      ))}
      {unexplainedSessions.map((session) => (
        <article className="decision-card" key={session.id}>
          <span className="decision-mark">?</span>
          <div>
            <p className="eyebrow">{titleCase(session.harness_type)} · unresolved</p>
            <h2>{session.label || `${titleCase(session.harness_type)} needs a decision`}</h2>
            <p>{session.last_message || "The worker is waiting for explicit human judgment."}</p>
          </div>
          {canOpenSession(session) ? (
            <button type="button" className="solid" onClick={() => onOpen(session)}>Open agent</button>
          ) : <span />}
        </article>
      ))}
      {generalActions.map((item) => {
        const session = sessions.find((row) => row.id === item.session_id);
        return (
        <article className="decision-card" key={item.id}>
          <span className="decision-mark">!</span>
          <div>
            <p className="eyebrow">Policy · {humanize(item.risk || "unknown risk")}</p>
            <h2>{item.diagnosis || "PEX requested human authority"}</h2>
            <p>{item.proposed_action?.rationale || item.result || "No additional rationale was recorded."}</p>
          </div>
          {session && canOpenSession(session) ? (
            <button type="button" className="solid" onClick={() => onOpen(session)}>Open agent</button>
          ) : null}
        </article>
        );
      })}
      {!permissionActions.length && !lifecycleActions.length && !requestedActions.length && !generalActions.length && !unexplainedSessions.length ? (
        <EmptyState title="No unresolved judgments" body="The last decision was refreshed from canonical bridge state." />
      ) : null}
    </div>
  );
}

function RequestedDecisionCard({
  intervention,
  session,
  feedback,
  busy,
  onOpen,
  onResolve,
}: {
  intervention: Intervention;
  session?: SessionRow;
  feedback: DecisionFeedback | null;
  busy: boolean;
  onOpen: (session: SessionRow) => void;
  onResolve: (intervention: Intervention, decision: HumanDecisionChoice) => void;
}) {
  const details = requestedHumanDecisionDetails(intervention);
  const [freeform, setFreeform] = useState("");
  const freeformSubmission = useRef(false);
  const freeformInput = useRef<HTMLInputElement>(null);
  const evidenceId = `requested-decision-evidence-${intervention.id}`;
  const statusId = `requested-decision-status-${intervention.id}`;
  const describedBy = `${evidenceId}${feedback ? ` ${statusId}` : ""}`;
  const canSubmitFreeform = prepareFreeformDecision(
    freeform,
    busy || freeformSubmission.current,
  ) !== null;

  useEffect(() => {
    if (!busy) freeformSubmission.current = false;
  }, [busy]);

  return (
    <article className="decision-card requested-decision-card">
      <span className="decision-mark" aria-hidden="true">?</span>
      <div>
        <p className="eyebrow">
          {session ? titleCase(session.harness_type) : "Missing session"} · {humanize(details.urgency)}
        </p>
        <h2>{details.question}</h2>
        <div id={evidenceId}>
          {details.context ? <p className="decision-rationale">{details.context}</p> : null}
          <p className="decision-rationale">
            PEX will reserve this exact answer before attempting delivery to the same worker.
          </p>
        </div>
        {feedback ? (
          <p
            id={statusId}
            className={`decision-inline-status decision-inline-${feedback.state}`}
            data-delivery-status={feedback.deliveryStatus}
            role={feedback.state === "error" ? "alert" : "status"}
          >
            {feedback.message}
          </p>
        ) : null}
      </div>
      <div className="decision-controls" role="group" aria-label="Answer worker question">
        {details.options.length ? details.options.map((option) => (
          <button
            key={option}
            type="button"
            className="solid decision-option"
            disabled={busy}
            aria-describedby={describedBy}
            onClick={() => onResolve(intervention, option)}
          >
            {feedback?.state === "submitting" && feedback.decision === option
              ? "Delivering…"
              : option}
          </button>
        )) : (
          <form
            className="decision-freeform"
            onSubmit={(event) => {
              event.preventDefault();
              const prepared = prepareFreeformDecision(
                freeform,
                busy || freeformSubmission.current,
              );
              if (!prepared) return;
              freeformSubmission.current = true;
              if (freeformInput.current) freeformInput.current.value = "";
              setFreeform(prepared.nextValue);
              onResolve(intervention, prepared.decision);
            }}
          >
            <label htmlFor={`requested-decision-choice-${intervention.id}`}>
              Your answer
            </label>
            <input
              ref={freeformInput}
              id={`requested-decision-choice-${intervention.id}`}
              value={freeform}
              maxLength={500}
              disabled={busy}
              aria-describedby={describedBy}
              onChange={(event) => setFreeform(event.target.value)}
            />
            <button type="submit" className="solid" disabled={busy || !canSubmitFreeform}>
              {feedback?.state === "submitting" ? "Delivering…" : "Send decision"}
            </button>
          </form>
        )}
        {session && canOpenSession(session) ? (
          <button type="button" className="text-button" onClick={() => onOpen(session)}>
            Open agent
          </button>
        ) : null}
      </div>
    </article>
  );
}

function lifecycleTitle(action: string): string {
  const titles: Record<string, string> = {
    START_AGENT: "Start another worker session?",
    STOP_AGENT: "Stop this worker session?",
    FORK_PROBE: "Fork an isolated probe?",
    CLEANUP: "Quarantine registered PEX residue?",
  };
  return titles[action] || "Review lifecycle action";
}

function lifecycleSummary(intervention: Intervention): string {
  const payload = intervention.proposed_action?.payload || {};
  const text = (key: string) => {
    const value = payload[key];
    return typeof value === "string" && value.trim() ? value.trim() : null;
  };
  if (intervention.action_taken === "START_AGENT") {
    return `Start a worker in ${text("project") || "an unspecified project"}`;
  }
  if (intervention.action_taken === "STOP_AGENT") {
    return `Stop source session ${intervention.session_id}`;
  }
  if (intervention.action_taken === "FORK_PROBE") {
    return `Fork a bounded probe from ${intervention.session_id}`;
  }
  if (intervention.action_taken === "CLEANUP") {
    const resources = Array.isArray(payload.resource_ids) ? payload.resource_ids.length : 0;
    return `${titleCase(text("mode") || "quarantine")} ${resources} registered resource${resources === 1 ? "" : "s"}`;
  }
  return humanize(intervention.action_taken);
}

function permissionTitle(details: ReturnType<typeof permissionRequestDetails>): string {
  if (details.command) return "Review command permission";
  if (details.toolName) return `Review ${details.toolName} permission`;
  return "Permission requires human authority";
}

function ContextView({
  goals,
  items,
  sessions,
  selectedSessionId,
}: {
  goals: Goal[];
  items: ContextItem[];
  sessions: SessionRow[];
  selectedSessionId?: string;
}) {
  const selected = sessions.find((session) => session.id === selectedSessionId);
  const goal = goals.find((item) => item.id === selected?.goal_id) ||
    goals.find((item) => sessions.some((session) => session.goal_id === item.id)) ||
    goals[0];
  const staleCount = items.filter((item) => isStale(item.stale_after)).length;
  const health = contextHealthCopy(selected, staleCount);

  return (
    <div className="context-layout">
      <aside className="context-boundaries">
        <p className="eyebrow">Active goal boundaries</p>
        <h2>{goal?.title || "No goal selected"}</h2>
        <ContextBoundary label="Constraints" values={goal?.constraints} />
        <ContextBoundary label="Non-goals" values={goal?.non_goals} />
        <ContextBoundary label="Preferences" values={goal?.preferences} />
        <ContextBoundary label="Acceptance" values={goal?.acceptance_criteria} />
        <p className={`context-health ${health.warning ? "warning" : ""}`}>
          {health.label}
        </p>
      </aside>
      <div className="context-list">
        {items.length ? items.map((item) => {
          const marks = contextItemMarks(item, items);
          return (
          <article
            className={`context-item ${marks.stale ? "stale" : ""} ${marks.superseded ? "superseded" : ""}`}
            key={item.id}
          >
            <div className="card-heading">
              <span className="context-kind">{humanize(item.kind)}</span>
              <small>{item.provenance ? `from ${humanize(item.provenance)}` : "source unavailable"}</small>
            </div>
            <p>{item.content}</p>
            <footer>
              <span>{item.source_refs?.length ? `Known by / observed in: ${item.source_refs.join(", ")}` : "No session source recorded"}</span>
              <span>
                {item.sensitivity ? `Sensitivity: ${humanize(item.sensitivity)}` : "Sensitivity unavailable"}
                {item.confidence != null ? ` · ${Math.round(item.confidence * 100)}% confidence` : ""}
              </span>
              {marks.stale ? <strong>Stale</strong> : null}
              {marks.superseded ? <strong>Superseded</strong> : null}
              {marks.replacesPrior ? <strong>Replaces a prior fact</strong> : null}
            </footer>
          </article>
          );
        }) : (
          <EmptyState title="No durable context recorded" body="Facts, decisions, constraints, and artifacts appear only after real ingestion." />
        )}
      </div>
    </div>
  );
}

type HandoffAssimilationPresentation = {
  label: string;
  detail: string;
};

type HandoffBundlePresentation = {
  tokenEstimate: number | null;
  nextObjective: string;
  doNotRedo: string[];
  items: Array<{
    id: string;
    kind: string;
    provenance: string;
    content: string;
    sourceRefs: string[];
  }>;
};

function handoffMonitoringDetail(status: HandoffAssimilationStatus): string {
  const monitoring = status.target_action_monitoring;
  if (!monitoring.available) return "";
  if (monitoring.possible_failure_observed) {
    return " A first target action reported a possible failure; that observation is not proof the handoff caused it.";
  }
  if (monitoring.observed_count) {
    return ` ${monitoring.observed_count} early target action${monitoring.observed_count === 1 ? " was" : "s were"} monitored.`;
  }
  return " No meaningful target action has been accepted yet.";
}

function handoffBundlePresentation(item: Intervention): HandoffBundlePresentation | null {
  const rawBundle = item.proposed_action?.payload?.bundle;
  if (!rawBundle || typeof rawBundle !== "object" || Array.isArray(rawBundle)) return null;
  const bundle = rawBundle as Record<string, unknown>;
  const rawItems = Array.isArray(bundle.items) ? bundle.items : [];
  const items = rawItems.flatMap((raw): HandoffBundlePresentation["items"] => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
    const value = raw as Record<string, unknown>;
    if (typeof value.id !== "string" || typeof value.content !== "string") return [];
    return [{
      id: value.id,
      kind: typeof value.kind === "string" ? value.kind : "unknown",
      provenance: typeof value.provenance === "string" ? value.provenance : "unknown",
      content: value.content,
      sourceRefs: Array.isArray(value.source_refs)
        ? value.source_refs.filter((ref): ref is string => typeof ref === "string")
        : [],
    }];
  });
  return {
    tokenEstimate: typeof bundle.token_estimate === "number" ? bundle.token_estimate : null,
    nextObjective: typeof bundle.next_objective === "string" ? bundle.next_objective : "",
    doNotRedo: Array.isArray(bundle.do_not_redo)
      ? bundle.do_not_redo.filter((value): value is string => typeof value === "string")
      : [],
    items,
  };
}

function handoffAssimilationPresentation(
  status: HandoffAssimilationStatus | "unreachable" | undefined,
): HandoffAssimilationPresentation {
  if (status === "unreachable") {
    return {
      label: "Target-use check unreachable",
      detail: "PEX could not reach canonical handoff monitoring state; this is not evidence that the target ignored the context.",
    };
  }
  if (!status) {
    return {
      label: "Assimilation evidence unavailable",
      detail: "The status endpoint did not provide a current target-use record.",
    };
  }
  const monitoringDetail = handoffMonitoringDetail(status);
  if (status.status === "not_delivered") {
    return {
      label: "Handoff not delivered · no target-use evidence",
      detail: `The operator effect has not reached the delivered state.${monitoringDetail}`,
    };
  }
  if (status.status === "monitoring_unavailable_legacy") {
    const reason = status.watermark
      ? "A causal first-action watermark exists, but this delivery predates the immutable typed-evidence candidate index, so exact artifact or acknowledgement routing is unavailable."
      : "This delivery predates the causal target-action watermark, so later target activity cannot be safely attributed.";
    return {
      label: "Context delivered · legacy monitoring unavailable",
      detail: `${reason}${monitoringDetail}`,
    };
  }
  if (status.status === "relevant_action_observed") {
    const action = status.first_relevant_action;
    const paths = action?.matched_artifact_paths.length
      ? ` Exact transferred artifact: ${action.matched_artifact_paths.join(", ")}.`
      : "";
    return {
      label: "Relevant target action observed · behavioral evidence",
      detail: `The target performed an ${humanize(action?.evidence_kind || "artifact action")} after delivery.${paths}${monitoringDetail}`,
    };
  }
  if (status.status === "target_acknowledged") {
    return {
      label: "Target acknowledged receipt · self-attested",
      detail: `The target cited exact transferred context references; this remains a self-attested acknowledgement.${monitoringDetail}`,
    };
  }
  if (status.status === "evidence_window_expired") {
    return {
      label: "Context delivered · target use not observed",
      detail: `No qualifying target evidence was observed before the monitoring window expired.${monitoringDetail}`,
    };
  }
  return {
    label: "Context delivered · target use not observed",
    detail: `The target evidence window is still open, but no qualifying acknowledgement or action is recorded.${monitoringDetail}`,
  };
}

function interventionHandoffEffectId(item: Intervention): string | null {
  const deliveryStatus = item.metadata?.handoff_delivery_status;
  if (item.action_taken !== "FRESH_HANDOFF" && typeof deliveryStatus !== "string") {
    return null;
  }
  const effectId = item.metadata?.operator_effect_id;
  return typeof effectId === "string" && effectId.trim() ? effectId.trim() : null;
}

function InterventionsView({
  interventions,
  handoffAssimilation,
  mutationsAvailable,
  onUndo,
}: {
  interventions: Intervention[];
  handoffAssimilation: Record<string, HandoffAssimilationStatus | "unreachable">;
  mutationsAvailable: boolean;
  onUndo: (intervention: Intervention) => void;
}) {
  if (!interventions.length) {
    return <EmptyState title="No interventions" body="Quiet is a valid result when no evidence justifies action." />;
  }

  return (
    <div className="audit-list">
      <p className="inline-note">
        Recent forensic detail only (up to 200 newest records). Headline attention metrics use
        the separate exact backend aggregate.
      </p>
      {interventions.map((item) => {
        const effectId = interventionHandoffEffectId(item);
        const isHandoff = effectId !== null || item.action_taken === "FRESH_HANDOFF";
        const assimilation = effectId && Object.hasOwn(handoffAssimilation, effectId)
          ? handoffAssimilation[effectId]
          : handoffAssimilation[item.id];
        const assimilationCopy = handoffAssimilationPresentation(assimilation);
        const deliveredBundle = isHandoff ? handoffBundlePresentation(item) : null;
        return (
          <article className="audit-row" key={item.id}>
            <div className="audit-time">
              <span className={`audit-dot helped-${String(item.helped)}`} aria-hidden="true" />
              <time>{formatTime(item.created_at)}</time>
            </div>
            <div className="audit-copy">
              <p className="eyebrow">Observed condition</p>
              <h2>{item.diagnosis || humanize(item.trigger || "unspecified trigger")}</h2>
              {item.evidence?.length ? (
                <details>
                  <summary>{item.evidence.length} evidence item{item.evidence.length === 1 ? "" : "s"}</summary>
                  <ul className="evidence-list">
                    {item.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}
                  </ul>
                </details>
              ) : null}
            </div>
            <div className="audit-action">
              <small>Action</small>
              <strong>{humanize(item.action_taken)}</strong>
              <span>{item.proposed_action?.rationale || "No rationale recorded."}</span>
            </div>
            <div className="audit-result">
              <small>Resulting state</small>
              <strong>{item.outcome || item.worker_response || item.result || "Awaiting observation"}</strong>
              <span>{helpedLabel(item.helped)}</span>
              {isHandoff ? (
                <div className="handoff-assimilation">
                  <small>Target-use evidence</small>
                  <strong>{assimilationCopy.label}</strong>
                  <span>{assimilationCopy.detail}</span>
                  <span>Verified: false · Not proof of understanding or correct use.</span>
                  {deliveredBundle ? (
                    <details>
                      <summary>
                        Exact delivered bundle · {deliveredBundle.items.length} selected item
                        {deliveredBundle.items.length === 1 ? "" : "s"}
                        {deliveredBundle.tokenEstimate == null ? "" : ` · ${deliveredBundle.tokenEstimate} estimated tokens`}
                      </summary>
                      {deliveredBundle.nextObjective ? (
                        <p><strong>Next objective:</strong> {deliveredBundle.nextObjective}</p>
                      ) : null}
                      {deliveredBundle.doNotRedo.length ? (
                        <p><strong>Do not redo:</strong> {deliveredBundle.doNotRedo.join(" · ")}</p>
                      ) : null}
                      <ul className="evidence-list">
                        {deliveredBundle.items.map((bundleItem) => (
                          <li key={bundleItem.id}>
                            <strong>{bundleItem.id}</strong> · {humanize(bundleItem.kind)} · {humanize(bundleItem.provenance)}
                            <br />{bundleItem.content}
                            {bundleItem.sourceRefs.length ? (
                              <small> Sources: {bundleItem.sourceRefs.join(", ")}</small>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>
              ) : null}
              {isSafelyUndoable(item.action_taken, item.reversible, item.result) ? (
                <button type="button" className="text-button" disabled={!mutationsAvailable} onClick={() => onUndo(item)}>Undo</button>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function AgentsView({
  sessions,
  fingerprints,
  adapters,
}: {
  sessions: SessionRow[];
  fingerprints: Fingerprint[];
  adapters: AdapterRow[];
}) {
  const adapterByName = useMemo(() => new Map(adapters.map((item) => [item.name, item])), [adapters]);
  const sessionsByHarness = useMemo(() => {
    const result = new Map<string, SessionRow[]>();
    for (const session of sessions) {
      const bucket = result.get(session.harness_type) || [];
      bucket.push(session);
      result.set(session.harness_type, bucket);
    }
    return result;
  }, [sessions]);
  const harnesses = Array.from(new Set([
    ...sessionsByHarness.keys(),
    ...fingerprints.map((item) => item.harness),
    ...adapters.map((item) => item.name),
  ]));

  if (!harnesses.length) {
    return <EmptyState title="No agent fingerprints yet" body="PEX learns from observed sessions; it does not invent strengths or failure patterns." />;
  }

  return (
    <div className="agent-grid">
      {harnesses.map((harness) => {
        const observed = sessionsByHarness.get(harness) || [];
        const fingerprint = fingerprints.find((item) => item.harness === harness);
        const adapter = adapterByName.get(harness);
        const models = fingerprint?.models?.length
          ? fingerprint.models
          : Array.from(new Set(observed.map((item) => item.model).filter(Boolean))) as string[];
        return (
          <article className="agent-card" key={harness}>
            <div className="card-heading">
              <span>
                <small>Harness fingerprint</small>
                <strong>{titleCase(harness)}</strong>
              </span>
              <span className="support-pill">
                {titleCase(String(adapter?.capabilities?.support_label || "unprobed"))}
              </span>
            </div>
            <dl>
              <div><dt>Model</dt><dd>{models.length ? models.join(", ") : "Not observed"}</dd></div>
              <div><dt>Observed sessions</dt><dd>{fingerprint?.observed_sessions ?? observed.length}</dd></div>
              <div><dt>Completion reliability</dt><dd>{fingerprintCompletionReliability(fingerprint)}</dd></div>
              <div><dt>Token behavior</dt><dd>{fingerprintTokenBehavior(fingerprint)}</dd></div>
              <div><dt>Recurring strengths</dt><dd>{fingerprintStrengths(fingerprint)}</dd></div>
              <div><dt>Premature STOP rate</dt><dd>{fingerprintPrematureRate(fingerprint)}</dd></div>
              <div><dt>Failure pattern</dt><dd>{fingerprintFailureModes(fingerprint)}</dd></div>
              <div><dt>Suggested configuration</dt><dd>{fingerprintSuggestedConfig(fingerprint)}</dd></div>
              <div>
                <dt>Adapter note</dt>
                <dd>{String(adapter?.capabilities?.notes || "No live capability note returned.")}</dd>
              </div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function BenchView({ bench }: { bench: BenchState }) {
  const inventory = starterHarnessInventoryCopy(bench.inventory);
  if (bench.loading && !bench.inventory && !bench.runs.length && !bench.message) {
    return <EmptyState title="Loading benchmark state" body="Waiting for the bridge result endpoint." />;
  }

  return (
    <div className="bench-layout">
      <div className="bench-side">
        <div className="bench-integrity">
          <span>Starter desktop inventory</span>
          <strong>{inventory.running}</strong>
          <p>Not running: {inventory.closed}</p>
          <p>{inventory.note}</p>
        </div>
        <div className="bench-integrity">
          <span>Integrity gate</span>
          <strong>
            {bench.runs.length
              ? bench.runs.every((run) => run.frozen)
                ? "Frozen manifests"
                : "Unfrozen data present"
              : "No verified runs"}
          </strong>
          <p>Only bridge-returned runs are shown. Demo replays are excluded. Inventory is not a freeze.</p>
        </div>
      </div>
      {!bench.runs.length ? (
        <EmptyState
          title="No verified benchmark runs"
          body={bench.message || "PEX will show immutable, reproducible runs here when the bridge exposes them."}
        />
      ) : (
        <div className="bench-runs">
          {bench.runs.map((run) => (
            <article className="bench-card" key={run.id}>
              <div className="card-heading">
                <span>
                  <small>{run.arm || "Unlabelled arm"} · {run.harness || "Unknown harness"}</small>
                  <strong>{run.name || run.id}</strong>
                </span>
                <span className={`state-pill ${run.frozen ? "state-verifying" : "state-needs_decision"}`}>
                  {run.frozen ? "frozen" : "unfrozen"}
                </span>
              </div>
              <dl>
                <Metric label="Task success" value={run.metrics?.task_success_rate} percent />
                <Metric label="Human interventions / success" value={run.metrics?.human_interventions_per_success} />
                <Metric label="Useful PEX interventions" value={run.metrics?.useful_interventions} />
                <Metric label="Harmful PEX interventions" value={run.metrics?.harmful_interventions} />
                <Metric label="Context handoffs" value={run.metrics?.context_handoffs} />
              </dl>
              <footer>{run.manifest_hash ? `Manifest ${run.manifest_hash.slice(0, 12)}…` : "Manifest hash unavailable"}</footer>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, percent = false }: { label: string; value?: number; percent?: boolean }) {
  return <div><dt>{label}</dt><dd>{value == null ? "—" : percent ? `${Math.round(value * 100)}%` : value}</dd></div>;
}

function ContextBoundary({ label, values }: { label: string; values?: string[] }) {
  return (
    <section>
      <h3>{label}</h3>
      {values?.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>None recorded</p>}
    </section>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <span aria-hidden="true">◌</span>
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  );
}

function helpedLabel(helped?: boolean | null): string {
  if (helped === true) return "Observed as helpful";
  if (helped === false) return "Observed as not helpful";
  return "Outcome not established";
}

function formatTime(value?: string): string {
  if (!value) return "time unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function viewDescription(view: DeckView): string {
  const copy: Record<DeckView, string> = {
    now: "Live sessions, one-line goals, evidence, intervention count, and attention state.",
    decisions: "Only unresolved choices requiring human judgment.",
    context: "Durable facts, decisions, constraints, artifacts, sources, and staleness.",
    interventions: "Observed condition → evidence → action → outcome.",
    agents: "Observed harness behavior and configuration suggestions, with unknowns left unknown.",
    bench: "Machine-readable benchmark runs returned by the live bridge.",
  };
  return copy[view];
}

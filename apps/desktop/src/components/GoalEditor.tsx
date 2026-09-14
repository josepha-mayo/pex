import type { FormEvent } from "react";

export type GoalDraft = {
  projectId: string;
  title: string;
  objective: string;
  acceptance: string;
  constraints: string;
  nonGoals: string;
  preferences: string;
  evidence: string;
  decisions: string;
  rejectedApproaches: string;
  unresolvedQuestions: string;
};

export function GoalEditor({
  draft,
  saving,
  disabled = false,
  willAttach,
  editing,
  projectIdentity,
  onChange,
  onSubmit,
  onCancel,
}: {
  draft: GoalDraft;
  saving: boolean;
  disabled?: boolean;
  willAttach: boolean;
  editing?: boolean;
  projectIdentity?: string;
  onChange: (field: keyof GoalDraft, value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel?: () => void;
}) {
  return (
    <form className="goal-form" onSubmit={onSubmit} aria-busy={saving}>
      <fieldset className="goal-form-fields" disabled={saving} aria-label="Goal details">
      {projectIdentity ? (
        <p className="goal-project-identity">
          <span>Workspace</span>
          <code>{projectIdentity}</code>
        </p>
      ) : (
        <label>
          Workspace
          <input
            value={draft.projectId}
            onChange={(event) => onChange("projectId", event.target.value)}
            placeholder="Select a session, or enter its workspace path"
          />
        </label>
      )}
      <label>
        What should get done?
        <textarea
          value={draft.objective}
          onChange={(event) => onChange("objective", event.target.value)}
          rows={6}
          placeholder="Describe the result you want and how to check it. You can paste your whole goal here."
        />
      </label>
      <p className="goal-help">PEX checks this goal as your agent works. Include an “Acceptance criteria:” list for specific checks.</p>
      <details className="goal-options">
      <summary>Optional details</summary>
      <div className="goal-option-fields">
      <label>
        Goal name · optional
        <input
          value={draft.title}
          onChange={(event) => onChange("title", event.target.value)}
          placeholder="Named automatically from your goal"
        />
      </label>
      <label>
        Acceptance criteria · one per line
        <textarea
          value={draft.acceptance}
          onChange={(event) => onChange("acceptance", event.target.value)}
          rows={2}
          placeholder="Clean build passes&#10;End-to-end recovery is observed"
        />
      </label>
      <div className="form-grid two-column">
        <label>
          Constraints · must remain true
          <textarea
            value={draft.constraints}
            onChange={(event) => onChange("constraints", event.target.value)}
            rows={2}
            placeholder="Do not expose secrets"
          />
        </label>
        <label>
          Non-goals · explicitly out of scope
          <textarea
            value={draft.nonGoals}
            onChange={(event) => onChange("nonGoals", event.target.value)}
            rows={2}
            placeholder="Do not redesign unrelated modules"
          />
        </label>
      </div>
      <label>
        Preferences · how the work should feel
        <textarea
          value={draft.preferences}
          onChange={(event) => onChange("preferences", event.target.value)}
          rows={2}
          placeholder="Prefer the smallest reversible change"
        />
      </label>
      <label>
        Required evidence · one item per line
        <textarea
          value={draft.evidence}
          onChange={(event) => onChange("evidence", event.target.value)}
          rows={2}
          placeholder="Full test suite exits 0&#10;Health endpoint returns HTTP 200"
        />
      </label>
      <label>
        Current decisions · one per line
        <textarea
          value={draft.decisions}
          onChange={(event) => onChange("decisions", event.target.value)}
          rows={2}
          placeholder="Use PostgreSQL for the durable ledger"
        />
      </label>
      <div className="form-grid two-column">
        <label>
          Rejected approaches
          <textarea
            value={draft.rejectedApproaches}
            onChange={(event) => onChange("rejectedApproaches", event.target.value)}
            rows={2}
            placeholder="Do not rewrite the evaluator as a new service"
          />
        </label>
        <label>
          Unresolved questions
          <textarea
            value={draft.unresolvedQuestions}
            onChange={(event) => onChange("unresolvedQuestions", event.target.value)}
            rows={2}
            placeholder="Which checkpoint format should survive the migration?"
          />
        </label>
      </div>
      </div>
      </details>
      <div className="button-row">
        <button
          className="solid"
          type="submit"
          disabled={
            saving ||
            disabled ||
            !draft.objective.trim() ||
            (!projectIdentity && !draft.projectId.trim())
          }
        >
          {saving
            ? "Saving…"
            : editing
              ? "Save changes"
              : willAttach
                ? "Start supervising"
                : "Create goal"}
        </button>
        {editing && onCancel ? (
          <button type="button" className="ghost" onClick={onCancel} disabled={saving}>
            Cancel edit
          </button>
        ) : null}
      </div>
      </fieldset>
    </form>
  );
}

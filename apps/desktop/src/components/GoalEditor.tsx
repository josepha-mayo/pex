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
  willAttach,
  editing,
  projectIdentity,
  onChange,
  onSubmit,
  onCancel,
}: {
  draft: GoalDraft;
  saving: boolean;
  willAttach: boolean;
  editing?: boolean;
  projectIdentity?: string;
  onChange: (field: keyof GoalDraft, value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel?: () => void;
}) {
  return (
    <form className="goal-form" onSubmit={onSubmit}>
      {projectIdentity ? (
        <p className="goal-project-identity">
          <span>Project identity</span>
          <code>{projectIdentity}</code>
        </p>
      ) : (
        <label>
          Project identity
          <input
            value={draft.projectId}
            onChange={(event) => onChange("projectId", event.target.value)}
            placeholder="Stable project id or workspace path"
          />
        </label>
      )}
      <label>
        Goal title
        <input
          value={draft.title}
          onChange={(event) => onChange("title", event.target.value)}
          placeholder="Ship a verified release"
        />
      </label>
      <label>
        Objective
        <textarea
          value={draft.objective}
          onChange={(event) => onChange("objective", event.target.value)}
          rows={4}
          placeholder="What outcome should persist across chats? Labeled Acceptance criteria lists are extracted if the fields below are empty."
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
      <div className="button-row">
        <button
          className="solid"
          type="submit"
          disabled={
            saving ||
            !draft.title.trim() ||
            !draft.objective.trim() ||
            (!projectIdentity && !draft.projectId.trim())
          }
        >
          {saving
            ? "Saving…"
            : editing
              ? "Save ledger"
              : willAttach
                ? "Save and attach"
                : "Save goal"}
        </button>
        {editing && onCancel ? (
          <button type="button" className="ghost" onClick={onCancel} disabled={saving}>
            Cancel edit
          </button>
        ) : null}
      </div>
    </form>
  );
}

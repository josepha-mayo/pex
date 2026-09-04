import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import type {
  ProjectIdentityCandidateView,
  ProjectIdentityConflictPage,
  ProjectIdentityFeedback,
  ProjectIdentityStatusView,
  ProjectLocatorView,
} from "../types";
import {
  newProjectIdentityResolutionKey,
  prepareProjectIdentityResolutionAttempt,
  projectIdentityPresentation,
  type ProjectIdentityResolutionAttempt,
} from "../viewModel";

type ProjectIdentityPanelProps = {
  conflicts: ProjectIdentityConflictPage | null;
  conflictsLoading: boolean;
  conflictsError: string | null;
  selectedLegacyProjectId: string;
  status: ProjectIdentityStatusView | null;
  loading: boolean;
  error: string | null;
  resolving: boolean;
  feedback: ProjectIdentityFeedback | null;
  onSelectProject: (legacyProjectId: string) => void;
  onResolve: (attempt: ProjectIdentityResolutionAttempt) => void;
  onLoadMoreConflicts: () => void;
  onLoadMoreCandidates: () => void;
};

export function ProjectIdentityPanel({
  conflicts,
  conflictsLoading,
  conflictsError,
  selectedLegacyProjectId,
  status,
  loading,
  error,
  resolving,
  feedback,
  onSelectProject,
  onResolve,
  onLoadMoreConflicts,
  onLoadMoreCandidates,
}: ProjectIdentityPanelProps) {
  const formId = useId();
  const [selectedIdentityId, setSelectedIdentityId] = useState("");
  const [rationale, setRationale] = useState("");
  const attempt = useRef<ProjectIdentityResolutionAttempt | null>(null);
  const liveProjectId = status?.legacy_project_id ?? "";
  const liveStatus = status?.status ?? "unavailable";
  const presentation = projectIdentityPresentation(status);
  const candidates = status?.status === "quarantined" ? status.candidates : [];
  const selectedCandidateIsLive = candidates.some(
    (candidate) => candidate.identity.id === selectedIdentityId,
  );
  const canSubmit =
    liveStatus === "quarantined" &&
    selectedCandidateIsLive &&
    rationale.trim().length > 0 &&
    rationale.trim().length <= 2_000 &&
    !resolving;
  const statusMessageId = `${formId}-status`;

  useEffect(() => {
    setSelectedIdentityId("");
    setRationale("");
    attempt.current = null;
  }, [liveProjectId]);

  useEffect(() => {
    if (liveStatus !== "quarantined") {
      setSelectedIdentityId("");
      setRationale("");
      attempt.current = null;
    }
  }, [liveStatus]);

  function changeCandidate(identityId: string) {
    setSelectedIdentityId(identityId);
    attempt.current = null;
  }

  function changeRationale(value: string) {
    setRationale(value);
    attempt.current = null;
  }

  function submitResolution(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!status || status.status !== "quarantined" || !selectedCandidateIsLive) return;
    const prepared = prepareProjectIdentityResolutionAttempt(
      attempt.current,
      {
        legacyProjectId: status.legacy_project_id,
        selectedIdentityId,
        rationale,
      },
      newProjectIdentityResolutionKey,
    );
    if (!prepared) return;
    attempt.current = prepared;
    onResolve(prepared);
  }

  return (
    <section className="project-identity-panel" aria-labelledby={`${formId}-heading`}>
      <header className="project-identity-heading">
        <div>
          <p className="eyebrow">Typed project boundary</p>
          <h2 id={`${formId}-heading`}>Project identity</h2>
        </div>
        <span className={`identity-state identity-state-${presentation.tone}`}>
          {status?.status ?? "not selected"}
        </span>
      </header>

      <ConflictPicker
        conflicts={conflicts}
        loading={conflictsLoading}
        error={conflictsError}
        resolving={resolving}
        selectedLegacyProjectId={selectedLegacyProjectId}
        onSelectProject={onSelectProject}
        onLoadMore={onLoadMoreConflicts}
      />

      {loading ? (
        <p className="identity-live-message" role="status" aria-live="polite">
          Refreshing live project identity state…
        </p>
      ) : null}
      {error ? (
        <p className="identity-live-message identity-live-error" role="alert">
          {error} Previously loaded identity details may be stale.
        </p>
      ) : null}

      <article className={`identity-status-card identity-status-${presentation.tone}`}>
        <p className="identity-exact-key">
          Exact legacy key
          <code>{status?.legacy_project_id || selectedLegacyProjectId || "No project selected"}</code>
        </p>
        <h3>{presentation.title}</h3>
        <p>{presentation.detail}</p>
        {presentation.freshCredentialWarning ? (
          <p className="identity-credential-warning" role="status">
            {presentation.freshCredentialWarning}
          </p>
        ) : null}
        {status?.status === "active" ? (
          <CandidateEvidence
            candidate={{ identity: status.identity, locators: status.locators }}
            heading="Active typed identity"
          />
        ) : null}
      </article>

      {status?.status === "quarantined" ? (
        <form className="identity-resolution-form" onSubmit={submitResolution}>
          <fieldset disabled={resolving} aria-describedby={statusMessageId}>
            <legend>Confirmed project identity</legend>
            <p className="decision-rationale">
              Select only the candidate whose exact typed locator evidence you confirmed.
              PEX never chooses the first candidate automatically.
            </p>
            <div className="identity-candidate-list">
              {candidates.map((candidate, index) => {
                const candidateId = `${formId}-candidate-${index}`;
                const evidenceId = `${candidateId}-evidence`;
                return (
                  <div className="identity-candidate" key={candidate.identity.id}>
                    <div className="identity-candidate-choice">
                      <input
                        id={candidateId}
                        type="radio"
                        name={`${formId}-candidate`}
                        value={candidate.identity.id}
                        checked={selectedIdentityId === candidate.identity.id}
                        aria-describedby={`${evidenceId} ${statusMessageId}`}
                        onChange={() => changeCandidate(candidate.identity.id)}
                      />
                      <label htmlFor={candidateId}>
                        Candidate {index + 1}
                        <code>{candidate.identity.id}</code>
                      </label>
                    </div>
                    <div id={evidenceId}>
                      <CandidateEvidence candidate={candidate} />
                    </div>
                  </div>
                );
              })}
            </div>
            {status.next_candidate_offset != null ? (
              <button
                type="button"
                className="ghost"
                disabled={loading || resolving}
                onClick={onLoadMoreCandidates}
              >
                Load more candidates
              </button>
            ) : null}
            <label className="identity-rationale" htmlFor={`${formId}-rationale`}>
              Resolution rationale
              <textarea
                id={`${formId}-rationale`}
                value={rationale}
                maxLength={2000}
                rows={3}
                required
                aria-describedby={statusMessageId}
                onChange={(event) => changeRationale(event.target.value)}
              />
            </label>
            <button
              type="submit"
              className="solid"
              disabled={!canSubmit}
              aria-describedby={statusMessageId}
            >
              {resolving ? "Recording resolution…" : "Resolve exact identity"}
            </button>
          </fieldset>
        </form>
      ) : null}
      {feedback || status?.status === "quarantined" ? (
        <p
          id={statusMessageId}
          className={`identity-resolution-feedback identity-resolution-${feedback?.state || "idle"}`}
          role={feedback?.state === "error" ? "alert" : "status"}
          aria-live={feedback?.state === "error" ? "assertive" : "polite"}
        >
          {feedback?.message ||
            "Resolution is durable and does not restore old MCP or hook credentials."}
        </p>
      ) : null}
    </section>
  );
}

function ConflictPicker({
  conflicts,
  loading,
  error,
  resolving,
  selectedLegacyProjectId,
  onSelectProject,
  onLoadMore,
}: {
  conflicts: ProjectIdentityConflictPage | null;
  loading: boolean;
  error: string | null;
  resolving: boolean;
  selectedLegacyProjectId: string;
  onSelectProject: (legacyProjectId: string) => void;
  onLoadMore: () => void;
}) {
  if (!conflicts) {
    return (
      <p className="identity-conflict-empty">
        {loading
          ? "Loading live project identity quarantines…"
          : error
            ? "The live quarantine list is unavailable; no empty-state conclusion is available."
            : "The live quarantine list has not been loaded."}
      </p>
    );
  }
  if (!conflicts.items.length) {
    return (
      <p className="identity-conflict-empty">
        The last successful live conflict query returned no project identity quarantines.
      </p>
    );
  }
  return (
    <section className="identity-conflicts" aria-label="Live project identity quarantines">
      <p>{conflicts.total} project {conflicts.total === 1 ? "identity needs" : "identities need"} review.</p>
      <div className="identity-conflict-buttons">
        {conflicts.items.map((conflict) => (
          <button
            key={conflict.legacy_project_id}
            type="button"
            className="ghost"
            disabled={resolving}
            aria-pressed={selectedLegacyProjectId === conflict.legacy_project_id}
            onClick={() => onSelectProject(conflict.legacy_project_id)}
          >
            <code>{conflict.legacy_project_id}</code>
            <span>{conflict.candidate_count} candidates</span>
          </button>
        ))}
      </div>
      {conflicts.next_offset != null ? (
        <button
          type="button"
          className="text-button"
          disabled={loading || resolving}
          onClick={onLoadMore}
        >
          Load more quarantines
        </button>
      ) : null}
    </section>
  );
}

function CandidateEvidence({
  candidate,
  heading,
}: {
  candidate: ProjectIdentityCandidateView;
  heading?: string;
}) {
  return (
    <section className="identity-candidate-evidence">
      {heading ? <h4>{heading}</h4> : null}
      <dl>
        <div>
          <dt>Stable identity</dt>
          <dd><code>{candidate.identity.id}</code></dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{candidate.identity.created_at}</dd>
        </div>
      </dl>
      <ul className="identity-locator-list">
        {candidate.locators.map((locator, index) => (
          <LocatorEvidence
            key={`${candidate.identity.id}-${index}-${locator.canonical}`}
            locator={locator}
            label={`Locator ${index + 1}`}
          />
        ))}
      </ul>
    </section>
  );
}

function LocatorEvidence({ locator, label }: { locator: ProjectLocatorView; label: string }) {
  return (
    <li className="identity-locator">
      <strong>{label}</strong>
      <dl>
        <div><dt>Kind</dt><dd>{locator.kind}</dd></div>
        <div><dt>Raw</dt><dd><code>{locator.raw}</code></dd></div>
        <div><dt>Canonical</dt><dd><code>{locator.canonical}</code></dd></div>
        <div>
          <dt>Origin</dt>
          <dd><code>{locator.origin.namespace}:{locator.origin.host}</code></dd>
        </div>
        <div><dt>Platform</dt><dd>{locator.platform || "not applicable"}</dd></div>
        {locator.physical ? (
          <>
            <div><dt>Physical proof</dt><dd>{locator.physical.provider}</dd></div>
            <div><dt>Volume</dt><dd><code>{locator.physical.volume_id}</code></dd></div>
            <div><dt>Object</dt><dd><code>{locator.physical.object_id}</code></dd></div>
          </>
        ) : null}
      </dl>
      {locator.members.length ? (
        <ul className="identity-locator-members">
          {locator.members.map((member, index) => (
            <LocatorEvidence
              key={`${index}-${member.canonical}`}
              locator={member}
              label={`Workspace member ${index + 1}`}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

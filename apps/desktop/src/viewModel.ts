import type {
  CanonicalResourceKey,
  CanonicalResourceMap,
  CanonicalResourceStatus,
  CatalogPet,
  ContextHealthSignals,
  ContextItem,
  Fingerprint,
  Goal,
  HatchBaseCandidateRequest,
  Intervention,
  LedgerDecision,
  PetSnapshot,
  ProjectIdentityResolutionResponse,
  ProjectIdentityStatusView,
  SessionRow,
  StatusCopy,
} from "./types";
import type { PetMood } from "./pets/atlas";

const LIFECYCLE_ACTIONS = new Set(["START_AGENT", "STOP_AGENT", "FORK_PROBE", "CLEANUP"]);

export const BUILT_IN_PET_IDS = [
  "pex",
  "ledger",
  "mesh",
  "nudge",
  "drift",
  "quiet",
  "ember",
  "von",
] as const;

const BUILT_IN_PET_ID_SET = new Set<string>(BUILT_IN_PET_IDS);

export const HATCH_BASE_CANDIDATE_DISCLOSURE =
  "This authorizes exactly one potentially billable image-generation call for one unverified base candidate. It is not an atlas or playable pet; grounded 8x11 assembly and independent mechanical, visual, continuity, and blind-direction QA are still required before import.";
export const HATCH_BASE_CANDIDATE_CONFIRMATION =
  "I authorize exactly one potentially billable image-generation call for this unverified base candidate.";
export const HATCH_EXTERNAL_IMPORT_DISCLOSURE =
  "Import only an externally assembled Codex v2 pet after its 8x11 atlas and independent QA are complete.";

export type HatchBaseCandidateAttempt = {
  idempotencyKey: string;
  requestSignature: string;
};

const HATCH_IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/u;

export function hatchIntentRequiresFreshAcknowledgement(
  currentValue: string,
  nextValue: string,
): boolean {
  return currentValue !== nextValue;
}

export function hatchResponseMatchesCurrentAttempt(
  submitted: HatchBaseCandidateAttempt,
  current: HatchBaseCandidateAttempt | null,
): boolean {
  return current?.idempotencyKey === submitted.idempotencyKey
    && current.requestSignature === submitted.requestSignature;
}

export function prepareHatchBaseCandidateAttempt(
  previous: HatchBaseCandidateAttempt | null,
  input: {
    displayName: string;
    description: string;
    stylePreset: string;
    petNotes: string;
  },
  nextIdempotencyKey: () => string,
): { attempt: HatchBaseCandidateAttempt; request: HatchBaseCandidateRequest } | null {
  const displayName = input.displayName.trim();
  const description = input.description.trim();
  const stylePreset = input.stylePreset.trim();
  const petNotes = input.petNotes.trim();
  if (
    !displayName
    || displayName.length > 128
    || description.length > 4_096
    || !stylePreset
    || stylePreset.length > 64
    || petNotes.length > 8_192
    || [displayName, description, stylePreset, petNotes].some(containsControlCharacters)
  ) return null;

  const requestSignature = JSON.stringify([
    displayName,
    description,
    stylePreset,
    petNotes,
  ]);
  const idempotencyKey = previous?.requestSignature === requestSignature
    ? previous.idempotencyKey
    : nextIdempotencyKey();
  if (!HATCH_IDEMPOTENCY_KEY.test(idempotencyKey)) return null;

  return {
    attempt: { idempotencyKey, requestSignature },
    request: {
      display_name: displayName,
      description,
      style_preset: stylePreset,
      pet_notes: petNotes,
      idempotency_key: idempotencyKey,
      confirm_one_base_candidate_call: true,
    },
  };
}

export function newHatchBaseCandidateKey(): string {
  return `hatch-base-${crypto.randomUUID()}`;
}

export type UndoAttempt = {
  interventionId: string;
  action: string;
  result: string;
  idempotencyKey: string;
};

const UNDO_IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/u;

export function prepareUndoAttempt(
  previous: UndoAttempt | null,
  input: {
    interventionId: string;
    action: string | undefined;
    reversible: boolean | undefined;
    result: string | undefined;
  },
  nextIdempotencyKey: () => string,
): UndoAttempt | null {
  const action = input.action || "";
  const result = input.result || "";
  if (
    !input.interventionId
    || !isSafelyUndoable(action, input.reversible, result)
  ) return null;
  if (
    previous?.interventionId === input.interventionId
    && previous.action === action
    && previous.result === result
  ) return previous;
  const idempotencyKey = nextIdempotencyKey();
  if (!UNDO_IDEMPOTENCY_KEY.test(idempotencyKey)) return null;
  return {
    interventionId: input.interventionId,
    action,
    result,
    idempotencyKey,
  };
}

export function newUndoIdempotencyKey(): string {
  return `undo-${crypto.randomUUID()}`;
}

export type GoalControlAction = "create" | "update" | "attach";

export type GoalControlAttempt = {
  action: GoalControlAction;
  scope: string;
  requestSignature: string;
  idempotencyKey: string;
};

const GOAL_CONTROL_IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/u;

export function newGoalControlIdempotencyKey(action: GoalControlAction): string {
  return `goal-${action}-${crypto.randomUUID()}`;
}

export function prepareGoalControlAttempt<T extends Record<string, unknown>>(
  previous: GoalControlAttempt | undefined,
  action: GoalControlAction,
  scope: string,
  request: T,
  nextIdempotencyKey: () => string = () => newGoalControlIdempotencyKey(action),
): { attempt: GoalControlAttempt; request: T & { idempotency_key: string } } {
  const requestSignature = JSON.stringify(request);
  const idempotencyKey = previous?.action === action
    && previous.scope === scope
    && previous.requestSignature === requestSignature
    ? previous.idempotencyKey
    : nextIdempotencyKey();
  if (!scope || !GOAL_CONTROL_IDEMPOTENCY_KEY.test(idempotencyKey)) {
    throw new Error("A valid goal-control operation identity is required.");
  }
  return {
    attempt: { action, scope, requestSignature, idempotencyKey },
    request: { ...request, idempotency_key: idempotencyKey },
  };
}

export type UndoReceiptResponse = {
  ok?: boolean;
  code?: string;
  state?: string;
  status?: string;
  replayed?: boolean;
};

export function undoResponsePresentation(
  action: string | undefined,
  response: UndoReceiptResponse,
): { completed: boolean; message: string } {
  if (action === "APPLY_OVERLAY") {
    if (response.state === "delivered" && response.ok === true) {
      return {
        completed: true,
        message: response.replayed
          ? "This exact overlay Undo was already completed; PEX did not revert it twice."
          : "Overlay Undo completed and the canonical overlay projection is reverted.",
      };
    }
    if (response.state === "reserved" || response.state === "dispatching") {
      return {
        completed: false,
        message: "Overlay Undo is durably pending. PEX does not yet claim the overlay was reverted.",
      };
    }
    return {
      completed: false,
      message: "Overlay Undo did not return a completed projection. PEX does not claim the overlay was reverted.",
    };
  }
  if (action === "CLEANUP" && ["reserved", "dispatching"].includes(response.status || "")) {
    return {
      completed: false,
      message: "Cleanup restore is durably reserved or dispatching. PEX will show only observed canonical state.",
    };
  }
  return {
    completed: response.ok === true,
    message: "Undo request delivered. PEX will observe the resulting state.",
  };
}

export function undoFailureMessage(action: string | undefined, status: number | null): string {
  if (action !== "APPLY_OVERLAY") return "That intervention could not be undone.";
  if (status === 409) {
    return "Overlay Undo conflicted with or was refused by canonical state. No revert is claimed.";
  }
  if (status === 502) {
    return "Overlay Undo delivery is uncertain. No revert is claimed; an identical retry reuses the same request key.";
  }
  return "That overlay could not be undone. No revert is claimed.";
}

export function projectCompletedOverlayUndo(
  intervention: Intervention,
  completedInterventionIds: ReadonlySet<string>,
): Intervention {
  if (
    intervention.action_taken !== "APPLY_OVERLAY"
    || !completedInterventionIds.has(intervention.id)
  ) return intervention;
  return {
    ...intervention,
    result: "overlay_reverted",
    outcome: "overlay_reverted_by_human",
  };
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ").replaceAll(":", " · ").trim().toLowerCase();
}

export type ProjectIdentityResolutionAttempt = {
  idempotencyKey: string;
  legacyProjectId: string;
  selectedIdentityId: string;
  rationale: string;
};

export function projectIdentityCompletionIsCurrent(
  requestProjectId: string,
  selectedProjectId: string,
  requestSelectionRevision: number,
  currentSelectionRevision: number,
): boolean {
  return requestProjectId === selectedProjectId
    && requestSelectionRevision === currentSelectionRevision;
}

export type ProjectIdentityPresentation = {
  tone: "neutral" | "active" | "quarantined";
  title: string;
  detail: string;
  freshCredentialWarning: string | null;
  canResolve: boolean;
};

const PROJECT_IDENTITY_FRESH_CREDENTIAL_WARNING =
  "Old MCP and hook credentials were not restored. Reconnect or explicitly issue fresh credentials.";

export function projectIdentityPresentation(
  status: ProjectIdentityStatusView | null,
): ProjectIdentityPresentation {
  if (!status) {
    return {
      tone: "neutral",
      title: "No project selected",
      detail: "Select an attached project or a quarantined identity record to inspect live state.",
      freshCredentialWarning: null,
      canResolve: false,
    };
  }
  if (status.status === "quarantined") {
    return {
      tone: "quarantined",
      title: "Project identity is ambiguous",
      detail:
        "Existing project credentials are revoked or absent. Credential reissue remains blocked until explicit resolution.",
      freshCredentialWarning: PROJECT_IDENTITY_FRESH_CREDENTIAL_WARNING,
      canResolve: true,
    };
  }
  if (status.status === "active") {
    return {
      tone: "active",
      title: "Typed project identity is active",
      detail: `Current stable identity: ${status.identity.id}`,
      freshCredentialWarning: status.fresh_credentials_required
        ? PROJECT_IDENTITY_FRESH_CREDENTIAL_WARNING
        : null,
      canResolve: false,
    };
  }
  return {
    tone: "neutral",
    title: "Typed project identity is not registered",
    detail: "PEX has no typed locator binding for this exact legacy project key.",
    freshCredentialWarning: null,
    canResolve: false,
  };
}

function containsControlCharacters(value: string): boolean {
  return /[\u0000-\u001f\u007f-\u009f]/u.test(value);
}

export function prepareProjectIdentityResolutionAttempt(
  previous: ProjectIdentityResolutionAttempt | null,
  input: {
    legacyProjectId: string;
    selectedIdentityId: string;
    rationale: string;
  },
  nextIdempotencyKey: () => string,
): ProjectIdentityResolutionAttempt | null {
  const rationale = input.rationale.trim();
  if (
    !input.legacyProjectId ||
    !/^prj_[0-9a-f]{32}$/u.test(input.selectedIdentityId) ||
    !rationale ||
    rationale.length > 2_000 ||
    containsControlCharacters(rationale)
  ) return null;
  if (
    previous?.legacyProjectId === input.legacyProjectId &&
    previous.selectedIdentityId === input.selectedIdentityId &&
    previous.rationale === rationale
  ) return previous;
  return {
    idempotencyKey: nextIdempotencyKey(),
    legacyProjectId: input.legacyProjectId,
    selectedIdentityId: input.selectedIdentityId,
    rationale,
  };
}

export function newProjectIdentityResolutionKey(): string {
  return `resolve-project-${crypto.randomUUID()}`;
}

export function projectIdentityResolutionMessage(
  response: ProjectIdentityResolutionResponse,
  liveStatus: ProjectIdentityStatusView | null,
): string {
  const receipt = response.outcome === "replayed"
    ? "The exact resolution request was already recorded."
    : "The resolution receipt was recorded.";
  if (!liveStatus) {
    return `${receipt} Live project identity status is unavailable; PEX will not infer that the binding is active.`;
  }
  if (liveStatus.status === "quarantined") {
    return `${receipt} The live binding is quarantined again; no credential was restored.`;
  }
  if (liveStatus.status === "active") {
    return `${receipt} The live binding is active. ${PROJECT_IDENTITY_FRESH_CREDENTIAL_WARNING}`;
  }
  return `${receipt} The live binding is unregistered; no credential was restored.`;
}

export function titleCase(value: string): string {
  return humanize(value).replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function normalizeLines(value: string): string[] {
  return value
    .split("\n")
    .map((row) => row.trim())
    .filter(Boolean);
}

export function selectPrimarySession(sessions: SessionRow[], selectedId?: string | null): SessionRow | undefined {
  const selected = sessions.find((session) => session.id === selectedId);
  if (selected) return selected;
  return (
    sessions.find((session) => session.status === "needs_decision") ??
    sessions.find((session) => session.status === "drifting") ??
    sessions.find((session) => session.status === "blocked" || session.status === "error") ??
    sessions.find((session) => session.status === "working" || session.status === "verifying") ??
    sessions[0]
  );
}

export const ASK_PEX_QUESTIONS = [
  "what is Codex doing?",
  "which agent is blocked?",
  "why did you message Cursor?",
  "what does Devin know that Codex doesn't?",
  "which approach looks better?",
  "did the eval actually finish?",
  "what needs me right now?",
] as const;

export function askPexQuestions(
  sessions: SessionRow[] = [],
  lastAction?: { action?: string; action_taken?: string } | null,
): string[] {
  const live = sessions.filter((session) =>
    ["working", "verifying", "drifting", "needs_decision", "blocked", "error"].includes(
      session.status,
    ),
  );
  const names: string[] = [];
  const seen = new Set<string>();
  for (const session of live) {
    const name = titleCase(session.harness_type);
    if (!name || seen.has(name)) continue;
    seen.add(name);
    names.push(name);
  }
  const questions: string[] = [];
  if (names[0]) questions.push(`what is ${names[0]} doing?`);
  if (live.some((session) => session.status === "blocked" || session.status === "error")) {
    questions.push("which agent is blocked?");
  }
  const action = lastAction?.action || lastAction?.action_taken;
  if (names[0] && (action === "SEND_NUDGE" || action === "APPLY_OVERLAY")) {
    questions.push(`why did you message ${names[0]}?`);
  }
  if (names[0] && names[1]) {
    questions.push(`what does ${names[1]} know that ${names[0]} doesn't?`);
  }
  questions.push(
    "which approach looks better?",
    "did the eval actually finish?",
    "what needs me right now?",
  );
  return questions;
}

export function companionHeadline(pet: PetSnapshot | null): string {
  if (!pet) return "Checking local state";
  const raw = (pet.headline || "").trim();
  if (!raw || raw === "quiet") {
    const working = pet.working || 0;
    const need = pet.needs_you || 0;
    if (working || need) return `${working} working · ${need} need you`;
    return "All quiet";
  }
  return raw.replace(/^[a-z][a-z0-9_]*(?:_[a-z0-9_]+)*/, (word) => titleCase(word));
}

export function supervisorHonestyCopy(info: {
  model_loaded?: boolean;
  has_api_key?: boolean;
  auth_mode?: string | null;
  login_implemented?: boolean;
} | null): string {
  const loaded = info?.model_loaded
    ? "Semantic model is loaded."
    : "PEX stays deterministic until a configured model is available.";
  const mode = info?.auth_mode || "unconfigured";
  const login = info?.login_implemented
    ? "Vendor login is available for this provider."
    : "ChatGPT, Claude, and Grok consumer login are not implemented. Use a BYOK key, a local runtime, or a custom endpoint.";
  return `${loaded} Auth mode: ${mode}. ${login}`;
}

export const CANONICAL_RESOURCE_KEYS: readonly CanonicalResourceKey[] = [
  "pet",
  "pets",
  "goals",
  "deck",
  "context",
  "interventions",
  "decisions",
  "completion",
  "supervisor",
  "channels",
];

export function initialCanonicalResources(): CanonicalResourceMap {
  return Object.fromEntries(
    CANONICAL_RESOURCE_KEYS.map((key) => [
      key,
      { status: "loading", error: null, lastSuccessAt: null },
    ]),
  ) as CanonicalResourceMap;
}

export function settleCanonicalResource(
  current: CanonicalResourceMap,
  key: CanonicalResourceKey,
  outcome: "fresh" | "failed" | "loading" | "reset",
  options: { error?: string; observedAt?: string } = {},
): CanonicalResourceMap {
  const prior = current[key];
  let nextStatus: CanonicalResourceStatus;
  if (outcome === "fresh") nextStatus = "fresh";
  else if (outcome === "loading" || outcome === "reset") nextStatus = "loading";
  else nextStatus = prior.lastSuccessAt ? "stale" : "unavailable";
  const next = {
    status: nextStatus,
    error: outcome === "failed" ? options.error?.trim() || "Canonical data is unavailable." : null,
    lastSuccessAt:
      outcome === "fresh"
        ? options.observedAt || new Date().toISOString()
        : outcome === "reset"
          ? null
          : prior.lastSuccessAt,
  };
  if (
    prior.status === next.status
    && prior.error === next.error
    && prior.lastSuccessAt === next.lastSuccessAt
  ) return current;
  return { ...current, [key]: next };
}

export function canonicalResourcesAreFresh(
  resources: CanonicalResourceMap,
  keys: readonly CanonicalResourceKey[],
): boolean {
  return keys.every((key) => resources[key].status === "fresh");
}

export function canonicalResourceIsFreshForScope(
  resources: CanonicalResourceMap,
  key: CanonicalResourceKey,
  observedScope: string | null,
  requestedScope: string,
): boolean {
  return observedScope === requestedScope && resources[key].status === "fresh";
}

export function canonicalResourceIssue(
  resources: CanonicalResourceMap,
  keys: readonly CanonicalResourceKey[],
): string | null {
  const affected = keys.filter((key) => resources[key].status !== "fresh");
  if (!affected.length) return null;
  const cached = affected.some((key) => resources[key].status === "stale");
  const loading = affected.every((key) => resources[key].status === "loading");
  if (loading) return "Checking canonical local state…";
  const names = affected.map((key) => key.replace("supervisor", "settings")).join(", ");
  return cached
    ? `Cached state · ${names} could not be refreshed.`
    : `Canonical state unavailable · ${names}.`;
}

export function statusCopy(
  pet: PetSnapshot | null,
  bridgeError: string | null,
  freshness: CanonicalResourceStatus = pet ? "fresh" : "loading",
): StatusCopy {
  if (freshness === "loading" && !pet && !bridgeError) {
    return {
      tone: "quiet",
      label: "Checking local state",
      detail: "PEX has not observed canonical local state yet.",
    };
  }
  if (bridgeError || freshness === "unavailable") {
    return {
      tone: "offline",
      label: "Bridge offline",
      detail: "Local state is unavailable. PEX will not invent an answer.",
    };
  }
  if (freshness === "stale") {
    return {
      tone: "offline",
      label: "Last observed state",
      detail: "Cached pet state is visible, but current local state is unavailable.",
    };
  }
  const label = companionHeadline(pet);
  const observed = pet?.last_message?.trim();
  if (pet?.needs_you) {
    return {
      tone: "need",
      label,
      detail:
        observed ||
        (pet.needs_you > 1 ? `${pet.needs_you} need a decision` : "Needs a decision"),
    };
  }
  if (pet?.blocked) {
    return {
      tone: "watch",
      label,
      detail: observed || (pet.blocked > 1 ? `${pet.blocked} blocked` : "A worker is blocked"),
    };
  }
  if (pet?.drifting) {
    return {
      tone: "watch",
      label,
      detail: observed || `${pet.drifting} drifting`,
    };
  }
  if (pet?.working) {
    return {
      tone: "work",
      label,
      detail: observed || `${pet.working} working`,
    };
  }
  if (pet?.paused) {
    return {
      tone: "quiet",
      label,
      detail: "Supervision is paused. PEX will not intervene until it is resumed.",
    };
  }
  return {
    tone: "quiet",
    label,
    detail: pet?.last_message || "Nothing needs babysitting.",
  };
}

export function moodForState(
  pet: PetSnapshot | null,
  bridgeError: string | null,
): PetMood {
  if (bridgeError) return "degraded";
  if (pet?.needs_you) return "decision";
  if (pet?.blocked) return "warning";
  if (pet?.mood === "handoff" || pet?.mood === "approved") return pet.mood;
  if (pet?.drifting) return "drift";
  if (pet?.working) return "working";
  return pet?.mood ?? "idle";
}

export function supportsCapability(
  session: SessionRow | undefined,
  capability: string,
): boolean {
  return session?.capabilities?.[capability] === true;
}

export function meaningfulEvidence(session?: SessionRow): string {
  if (!session) return "No meaningful evidence observed yet.";
  if (session.last_message?.trim()) return session.last_message;
  if (
    session.activity?.trim() &&
    ["working", "verifying", "drifting", "blocked", "error", "stopped"].includes(
      session.status,
    )
  ) {
    return session.activity;
  }
  return "No meaningful evidence observed yet.";
}

export function nextExpectedEvent(session?: SessionRow): string {
  switch (session?.status) {
    case "needs_decision":
      return "Your decision, then an observed continuation in this same session.";
    case "verifying":
      return "A real verification result or a concrete acceptance gap.";
    case "working":
      return "The next meaningful edit, tool result, or completion claim.";
    case "drifting":
      return "Fresh observed progress on the attached goal, or an explicit human redirect.";
    case "blocked":
    case "error":
      return "New evidence, a safe recovery, or a genuine human decision.";
    case "stopped":
      return "Verification of the stop claim against the persistent goal.";
    default:
      return "A new worker event. PEX stays quiet until evidence changes.";
  }
}

export function createGoalPayload(input: {
  projectId: string;
  title: string;
  objective: string;
  acceptance: string;
  constraints: string;
  nonGoals: string;
  evidence: string;
  preferences?: string;
  decisions?: string;
  rejectedApproaches?: string;
  unresolvedQuestions?: string;
  idempotencyKey?: string;
}): Omit<Goal, "id"> & {
  idempotency_key?: string;
  decisions: string[];
  rejected_approaches: string[];
  unresolved_questions: string[];
} {
  return {
    ...(input.idempotencyKey ? { idempotency_key: input.idempotencyKey } : {}),
    project_id: input.projectId,
    title: input.title.trim(),
    objective: input.objective.trim(),
    acceptance_criteria: normalizeLines(input.acceptance),
    constraints: normalizeLines(input.constraints),
    non_goals: normalizeLines(input.nonGoals),
    preferences: normalizeLines(input.preferences || ""),
    evidence_requirements: normalizeLines(input.evidence),
    decisions: normalizeLines(input.decisions || ""),
    rejected_approaches: normalizeLines(input.rejectedApproaches || ""),
    unresolved_questions: normalizeLines(input.unresolvedQuestions || ""),
  };
}

export function updateGoalPayload(input: {
  title: string;
  objective: string;
  acceptance: string;
  constraints: string;
  nonGoals: string;
  evidence: string;
  preferences?: string;
  decisions?: string;
  rejectedApproaches?: string;
  unresolvedQuestions?: string;
}, expectedIntentRevision: number, idempotencyKey?: string): {
  idempotency_key?: string;
  mode: "update";
  expected_intent_revision: number;
  title: string;
  objective: string;
  acceptance_criteria: string[];
  constraints: string[];
  non_goals: string[];
  preferences: string[];
  evidence_requirements: string[];
  decisions: string[];
  rejected_approaches: string[];
  unresolved_questions: string[];
} {
  if (!Number.isSafeInteger(expectedIntentRevision) || expectedIntentRevision < 0) {
    throw new Error("A canonical nonnegative goal intent revision is required.");
  }
  const created = createGoalPayload({ projectId: "unused", ...input });
  return {
    ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    mode: "update",
    expected_intent_revision: expectedIntentRevision,
    title: created.title,
    objective: created.objective,
    acceptance_criteria: created.acceptance_criteria || [],
    constraints: created.constraints || [],
    non_goals: created.non_goals || [],
    preferences: created.preferences || [],
    evidence_requirements: created.evidence_requirements || [],
    decisions: created.decisions || [],
    rejected_approaches: created.rejected_approaches || [],
    unresolved_questions: created.unresolved_questions || [],
  };
}

export function sessionGoalAttachmentPayload(
  goalId: string,
  expectedGoalId: string | null | undefined,
  expectedControlRevision: number,
  expectedGoalIntentRevision: number,
  idempotencyKey?: string,
): {
  idempotency_key?: string;
  goal_id: string;
  replace_existing: boolean;
  expected_goal_id: string | null;
  expected_control_revision: number;
  expected_goal_intent_revision: number;
} {
  if (!Number.isSafeInteger(expectedControlRevision) || expectedControlRevision < 0) {
    throw new Error("A canonical nonnegative session control revision is required.");
  }
  if (!Number.isSafeInteger(expectedGoalIntentRevision) || expectedGoalIntentRevision < 0) {
    throw new Error("A canonical nonnegative goal intent revision is required.");
  }
  const replaceExisting = Boolean(expectedGoalId && expectedGoalId !== goalId);
  return {
    ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    goal_id: goalId,
    replace_existing: replaceExisting,
    expected_goal_id: replaceExisting ? expectedGoalId! : null,
    expected_control_revision: expectedControlRevision,
    expected_goal_intent_revision: expectedGoalIntentRevision,
  };
}

export function goalToDraft(goal: Goal, projectId = "", decisions: LedgerDecision[] = []): {
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
} {
  const partitioned = partitionLedgerDecisions(decisions);
  return {
    projectId: projectId || goal.project_id || "",
    title: goal.title,
    objective: goal.objective,
    acceptance: (goal.acceptance_criteria || []).join("\n"),
    constraints: (goal.constraints || []).join("\n"),
    nonGoals: (goal.non_goals || []).join("\n"),
    preferences: (goal.preferences || []).join("\n"),
    evidence: (goal.evidence_requirements || []).join("\n"),
    decisions: partitioned.decisions.map((item) => item.statement).join("\n"),
    rejectedApproaches: partitioned.rejected.map((item) => item.statement).join("\n"),
    unresolvedQuestions: partitioned.unresolved.map((item) => item.statement).join("\n"),
  };
}

export function partitionLedgerDecisions(rows: LedgerDecision[]): {
  decisions: LedgerDecision[];
  rejected: LedgerDecision[];
  unresolved: LedgerDecision[];
} {
  const live = rows.filter((item) => item.status !== "superseded");
  return {
    decisions: live.filter(
      (item) => ledgerDecisionKind(item) === "decision" && item.status !== "uncertain",
    ),
    rejected: live.filter((item) => ledgerDecisionKind(item) === "rejected_approach"),
    unresolved: live.filter(
      (item) =>
        ledgerDecisionKind(item) === "unresolved_question" ||
        (item.status === "uncertain" && ledgerDecisionKind(item) !== "rejected_approach"),
    ),
  };
}

function ledgerDecisionKind(item: LedgerDecision): string {
  const kind = item.metadata?.kind;
  return typeof kind === "string" && kind.trim() ? kind : "decision";
}

export function currentGoals(goals: Goal[]): Goal[] {
  const superseded = new Set(
    goals
      .map((goal) => goal.supersedes)
      .filter((goalId): goalId is string => typeof goalId === "string" && goalId.length > 0),
  );
  return goals.filter((goal) => !superseded.has(goal.id));
}

export function splitPetCatalog(
  starters: CatalogPet[],
  catalog: CatalogPet[],
): { builtIns: CatalogPet[]; custom: CatalogPet[]; fleetIssues: string[] } {
  const fleetIssues: string[] = [];
  const rows = new Map<string, CatalogPet>();
  for (const pet of [...starters, ...catalog]) {
    const existing = rows.get(pet.id);
    if (existing && existing.source !== pet.source) {
      fleetIssues.push(`Conflicting catalog sources for ${pet.id}.`);
    }
    // The full catalog is authoritative when the starter and catalog payloads
    // repeat the same canonical row.
    rows.set(pet.id, pet);
  }

  for (const pet of rows.values()) {
    if (pet.source === "starter" && !BUILT_IN_PET_ID_SET.has(pet.id)) {
      fleetIssues.push(`Unexpected built-in pet ${pet.id}.`);
    } else if (
      pet.source !== "starter"
      && BUILT_IN_PET_ID_SET.has(pet.id)
    ) {
      fleetIssues.push(`Built-in pet ${pet.id} has source ${pet.source || "unknown"}.`);
    } else if (!pet.source || !["starter", "imported", "hatched"].includes(pet.source)) {
      fleetIssues.push(`Pet ${pet.id} has an unknown source.`);
    }
  }

  const builtIns = BUILT_IN_PET_IDS.flatMap((id) => {
    const pet = rows.get(id);
    if (!pet) {
      fleetIssues.push(`Missing built-in pet ${id}.`);
      return [];
    }
    return pet.source === "starter" ? [pet] : [];
  });
  return {
    builtIns,
    custom: catalog.filter(
      (pet) =>
        !BUILT_IN_PET_ID_SET.has(pet.id)
        && (pet.source === "imported" || pet.source === "hatched"),
    ),
    fleetIssues: [...new Set(fleetIssues)],
  };
}

export function canFocusSession(session: SessionRow | undefined): boolean {
  if (!supportsCapability(session, "focus_ui")) return false;
  // A connected Codex App Server session has no corresponding desktop chat.
  // The adapter can truthfully focus ChatGPT.exe only for its observe-only row.
  return session?.harness_type !== "codex" || session.id === "codex:desktop";
}

export function canAttachPersistentGoal(session: SessionRow | undefined): boolean {
  if (!session) return false;
  return session.id.endsWith(":desktop") === false && session.metadata?.source !== "desktop";
}

export function safeExternalUrl(value?: string | null): string | null {
  const raw = (value || "").trim();
  if (!raw || raw.length > 2048) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:") return null;
    if (url.username || url.password || url.search || url.hash) return null;
    if (url.hostname.toLowerCase() !== "app.devin.ai") return null;
    const match = /^\/sessions\/([A-Za-z0-9._-]{1,128})$/.exec(url.pathname);
    if (!match || match[1] === "new" || match[1] === "create" || match[1].startsWith(".")) {
      return null;
    }
    return `https://app.devin.ai/sessions/${match[1]}`;
  } catch {
    return null;
  }
}

export function sessionExternalUrl(session: SessionRow | undefined): string | null {
  return safeExternalUrl(session?.external_url);
}

export function canOpenSession(session: SessionRow | undefined): boolean {
  return canFocusSession(session) || Boolean(sessionExternalUrl(session));
}

export function reconnectDelay(attempt: number): number {
  const boundedAttempt = Math.max(0, Math.min(Math.trunc(attempt), 5));
  return Math.min(1_000 * 2 ** boundedAttempt, 15_000);
}

export function canonicalEventCursor(value: unknown): string {
  return typeof value === "string" && /^(0|[1-9][0-9]{0,18})$/u.test(value)
    ? value
    : "0";
}

export function eventPageResumeCursor(payload: unknown): string | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const page = payload as Record<string, unknown>;
  const gap = page.gap;
  if (gap && typeof gap === "object" && !Array.isArray(gap)) {
    const gapRecord = gap as Record<string, unknown>;
    if (gapRecord.detected === true) {
      const earliest = canonicalEventCursor(gapRecord.earliest_available);
      if (earliest === "0") return null;
      return (BigInt(earliest) - 1n).toString();
    }
  }
  const next = canonicalEventCursor(page.next);
  return next === "0" && page.next !== "0" ? null : next;
}

export function encodeWebSocketTokenProtocol(token: string): string {
  if (token.length < 32 || token.length > 512 || !/^[\x21-\x7e]+$/.test(token)) {
    throw new Error("PEX bridge token is invalid.");
  }
  const encoded = btoa(token)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/u, "");
  return `pex-token.${encoded}`;
}

export function contextItemMarks(
  item: ContextItem,
  items: ContextItem[] = [],
): { stale: boolean; superseded: boolean; replacesPrior: boolean } {
  return {
    stale: isStale(item.stale_after),
    superseded: items.some((other) => other.id !== item.id && other.supersedes === item.id),
    replacesPrior: Boolean(item.supersedes),
  };
}

export function isStale(staleAfter?: string | null, now = Date.now()): boolean {
  if (!staleAfter) return false;
  const deadline = Date.parse(staleAfter);
  return !Number.isFinite(deadline) || deadline < now;
}

export function isPendingPermissionDecision(intervention: Intervention): boolean {
  const requestId = intervention.proposed_action?.payload?.request_id;
  return (
    intervention.action_taken === "RESPOND_PERMISSION" &&
    intervention.proposed_action?.type === "RESPOND_PERMISSION" &&
    intervention.policy_verdict === "ask_human" &&
    intervention.result === "permission_awaiting_human" &&
    typeof requestId === "string" &&
    requestId.trim().length > 0
  );
}

export function isPendingLifecycleDecision(intervention: Intervention): boolean {
  return (
    LIFECYCLE_ACTIONS.has(intervention.action_taken) &&
    intervention.proposed_action?.type === intervention.action_taken &&
    intervention.policy_verdict === "ask_human" &&
    intervention.result === "awaiting_human"
  );
}

export function isPendingRequestedHumanDecision(intervention: Intervention): boolean {
  const payload = intervention.proposed_action?.payload;
  const question = payload?.question;
  const options = payload?.options;
  return (
    intervention.action_taken === "ASK_HUMAN" &&
    intervention.proposed_action?.type === "ASK_HUMAN" &&
    intervention.policy_verdict === "ask_human" &&
    intervention.result === "awaiting_human" &&
    intervention.metadata?.decision_kind === "mcp_human_request" &&
    typeof question === "string" &&
    question.trim().length > 0 &&
    Array.isArray(options) &&
    options.every((option) => typeof option === "string" && option.trim().length > 0)
  );
}

export function isPendingHumanDecision(intervention: Intervention): boolean {
  return (
    isPendingPermissionDecision(intervention) ||
    isPendingLifecycleDecision(intervention) ||
    isPendingRequestedHumanDecision(intervention)
  );
}

export function requestedHumanDecisionDetails(intervention: Intervention): {
  question: string;
  context: string | null;
  options: string[];
  urgency: string;
} {
  const payload = intervention.proposed_action?.payload || {};
  const question = textValue(payload.question) || "The worker requested a human decision.";
  const context = textValue(payload.context);
  const options = Array.isArray(payload.options)
    ? payload.options.filter(
        (option): option is string => typeof option === "string" && option.trim().length > 0,
      )
    : [];
  return {
    question,
    context,
    options,
    urgency: textValue(payload.urgency) || "normal",
  };
}

export function isSafelyUndoable(
  action: string | undefined,
  reversible: boolean | undefined,
  result: string | undefined,
): boolean {
  if (reversible !== true) return false;
  if (action === "APPLY_OVERLAY") return result === "overlay_applied";
  return action === "CLEANUP" && Boolean(result?.startsWith("cleanup_quarantined:"));
}

export function permissionRequestDetails(intervention: Intervention): {
  requestId: string;
  command: string | null;
  toolName: string | null;
  approvalMethod: string | null;
  filePaths: string[];
} {
  const payload = intervention.proposed_action?.payload || {};
  return {
    requestId: textValue(payload.request_id) || "unavailable",
    command: textValue(payload.command),
    toolName: textValue(payload.tool_name),
    approvalMethod: textValue(payload.approval_method),
    filePaths: Array.isArray(payload.file_paths)
      ? payload.file_paths.filter((item): item is string => typeof item === "string")
      : [],
  };
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function joinObserved(values: string[] | undefined, empty: string): string {
  if (!values?.length) return empty;
  return values.join("; ");
}

export function fingerprintStrengths(fingerprint?: Fingerprint): string {
  return joinObserved(fingerprint?.strengths, "Insufficient observed evidence");
}

export function fingerprintFailureModes(fingerprint?: Fingerprint): string {
  return joinObserved(fingerprint?.failure_modes, "Not established from STOP inspections");
}

export function fingerprintSuggestedConfig(fingerprint?: Fingerprint): string {
  return joinObserved(fingerprint?.recommended_overlays, "No measured overlay recommendation yet");
}

export function fingerprintCompletionReliability(fingerprint?: Fingerprint): string {
  const inspected = fingerprint?.inspected_stop_sessions ?? 0;
  if (!fingerprint || inspected <= 0) return "Not established by this endpoint";
  const rate = fingerprint.verified_success_rate ?? 0;
  const noun = inspected === 1 ? "STOP" : "STOPs";
  return `${rate.toFixed(2)} from ${inspected} inspected ${noun}`;
}

export function fingerprintPrematureRate(fingerprint?: Fingerprint): string {
  if (!fingerprint) return "Insufficient data";
  return fingerprint.premature_stop_rate.toFixed(2);
}

export function fingerprintTokenBehavior(fingerprint?: Fingerprint): string {
  if (fingerprint?.token_efficiency == null) return "Not exposed by this endpoint";
  return String(fingerprint.token_efficiency);
}

export function contextHealthSignals(session?: SessionRow): ContextHealthSignals | null {
  const nested = session?.metadata?.context_health_signals;
  const raw = session?.context_health_signals ?? nested;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  return raw as ContextHealthSignals;
}

export function contextHealthCopy(
  session?: SessionRow,
  staleCount = 0,
): { label: string; warning: boolean } {
  const score = session?.context_health;
  const signals = contextHealthSignals(session);
  const parts: string[] = [];
  if (typeof score === "number") {
    parts.push(`Context health ${Math.round(score * 100)}%`);
  }
  if (signals?.forgotten_fact_count) {
    const count = signals.forgotten_fact_count;
    parts.push(`${count} forgotten fact${count === 1 ? "" : "s"} re-acquired after compaction`);
  }
  if (signals?.compaction_count) {
    const count = signals.compaction_count;
    parts.push(`${count} compaction${count === 1 ? "" : "s"}`);
  }
  if (signals?.contradiction_count) {
    const count = signals.contradiction_count;
    parts.push(`${count} conflicting fact${count === 1 ? "" : "s"}`);
  }
  if (staleCount) {
    parts.push(`${staleCount} stale item${staleCount === 1 ? "" : "s"}`);
  }
  if (signals && signals.token_utilization == null) {
    parts.push("token utilization unavailable");
  }
  if (signals && signals.summary_depth == null) {
    parts.push("summary depth unavailable");
  }
  if (!parts.length) {
    return { label: "Context health not yet measured", warning: false };
  }
  const warning =
    (typeof score === "number" && score < 0.6) ||
    staleCount > 0 ||
    Boolean(signals?.forgotten_fact_count) ||
    Boolean(signals?.contradiction_count);
  return { label: parts.join(" · "), warning };
}

export function channelStatusCopy(row: {
  label: string;
  configured: boolean;
  connected: boolean;
  notes: string;
}): string {
  if (row.connected && row.configured) {
    return `${row.label} is delivering attention notices locally. ${row.notes}`;
  }
  return `${row.label} is not configured. ${row.notes}`;
}

export const STARTER_HARNESS_IDS = [
  "cursor",
  "codex",
  "opencode",
  "hermes",
  "claude_code",
] as const;

const STARTER_HARNESS_LABELS: Record<(typeof STARTER_HARNESS_IDS)[number], string> = {
  cursor: "Cursor",
  codex: "Codex",
  opencode: "OpenCode",
  hermes: "Hermes",
  claude_code: "Claude Code",
};

export function starterHarnessLabel(name: string): string {
  return STARTER_HARNESS_LABELS[name as keyof typeof STARTER_HARNESS_LABELS] ?? titleCase(name);
}

export function starterInventoryFromDiscover(payload: {
  found?: Array<{ name?: string; kind?: string }>;
  not_running?: string[];
}): { running: string[]; not_running: string[] } {
  const allowed = new Set<string>(STARTER_HARNESS_IDS);
  const running = [
    ...new Set(
      (payload.found ?? [])
        .filter(
          (item) =>
            item.kind === "desktop" &&
            typeof item.name === "string" &&
            allowed.has(item.name),
        )
        .map((item) => item.name as string),
    ),
  ].sort();
  const notRunning = [
    ...new Set((payload.not_running ?? []).filter((name) => allowed.has(name))),
  ].sort();
  return { running, not_running: notRunning };
}

export function starterHarnessInventoryCopy(inventory?: {
  running?: string[];
  not_running?: string[];
}): { running: string; closed: string; note: string } {
  if (!inventory) {
    return {
      running: "Starter desktop inventory is unavailable.",
      closed: "Unavailable",
      note: "Desktop process inventory is diagnostic and is never a freeze blocker.",
    };
  }
  const runningLabels = (inventory.running ?? []).map(starterHarnessLabel);
  const closedLabels = (inventory.not_running ?? []).map(starterHarnessLabel);
  return {
    running: runningLabels.length
      ? runningLabels.join(", ")
      : "None of the starter harnesses currently have a desktop process.",
    closed: closedLabels.length ? closedLabels.join(", ") : "None reported closed.",
    note: "Desktop process inventory is diagnostic and is never a freeze blocker.",
  };
}

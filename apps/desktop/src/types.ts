import type { PetMood } from "./pets/atlas";

export type Surface = "compact" | "inspector" | "deck";
export type DeckView = "now" | "decisions" | "context" | "interventions" | "agents" | "bench";

export type BridgeBootstrapStatus = {
  phase: "starting" | "ready" | "failed";
  code: string | null;
  message: string;
  retryable: boolean;
  source: "not_ready" | "owned_sidecar" | "unverified_port_owner";
  attempt: number;
};

export type SessionRow = {
  id: string;
  harness_type: string;
  status: string;
  goal_id?: string | null;
  supervision_paused?: boolean;
  last_message?: string | null;
  cwd?: string | null;
  project_id?: string | null;
  label?: string;
  activity?: string;
  model?: string | null;
  reasoning_effort?: string | null;
  context_health?: number;
  context_health_signals?: ContextHealthSignals;
  last_activity?: string | null;
  capabilities?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  external_url?: string | null;
  revision?: number;
  control_revision?: number;
};

export type SessionGoalAttachmentReceipt = {
  schema: "pex.session-goal-attachment-receipt.v1";
  changed: boolean;
  reason: "session_goal_attached" | "session_goal_replaced" | "session_goal_already_attached";
  goal_id: string;
  goal_intent_revision: number;
  goal_intent_hash: string;
  before_goal_id: string | null;
  after_goal_id: string;
  before_revision: number;
  after_revision: number;
  before_control_revision: number;
  after_control_revision: number;
  project_binding: string;
  discovery_generation: string | null;
  mcp_principals_revoked: number;
  hook_credentials_revoked: number;
};

export type OperatorIntentOperationReceipt = {
  schema: "pex.goal-control-operation.v1";
  operation_id: string;
  action_kind: "goal_create" | "goal_update" | "goal_override" | "session_goal_attach";
  idempotency_key: string;
  request_hash: string;
  principal_id: "local_bridge_operator";
  actor_assurance: "bridge_bearer";
  state: "committed";
  committed_at: string;
};

export type SessionGoalAttachmentResponse = SessionRow & {
  revision: number;
  control_revision: number;
  session_goal_attachment_receipt: SessionGoalAttachmentReceipt;
  operator_operation_receipt?: OperatorIntentOperationReceipt;
};

export type ContextHealthSignals = {
  token_utilization?: number | null;
  compaction_count?: number;
  forgotten_fact_count?: number;
  contradiction_count?: number;
  repeated_read_count?: number;
  stale_decision_count?: number;
  summary_depth?: number | null;
  context_to_progress_ratio?: number | null;
};

export type LastAction = {
  id: string;
  session_id: string;
  action: string;
  diagnosis?: string;
  evidence?: string[];
  result?: string;
  reversible?: boolean;
  confidence?: number;
  used_llm?: boolean;
  verification_status?: string | null;
  evidence_tools?: string[];
};

export type PetSnapshot = {
  headline: string;
  working: number;
  drifting: number;
  blocked?: number;
  needs_you: number;
  paused?: number;
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
  settings?: { custom_name?: string; scale?: number; click_through?: boolean };
  sessions: SessionRow[];
};

export type LedgerDecision = {
  id: string;
  goal_id: string;
  statement: string;
  rationale?: string;
  alternatives_rejected?: string[];
  source?: string;
  status?: string;
  metadata?: Record<string, unknown>;
};

export type Goal = {
  id: string;
  project_id?: string;
  title: string;
  objective: string;
  acceptance_criteria?: string[];
  constraints?: string[];
  non_goals?: string[];
  evidence_requirements?: string[];
  preferences?: string[];
  supersedes?: string | null;
  intent_revision?: number;
  intent_hash?: string;
};

export type GoalCompletion = {
  schema: "pex.goal-completion.v1";
  goal_id: string;
  project_id: string;
  goal_intent_revision: number;
  goal_intent_hash: string;
  status: "verified_complete" | "incomplete" | "uncertain" | "in_progress";
  reason: string;
  as_of: string;
  stale_evidence_excluded: number;
  active_session_ids: string[];
  worker_narration_used: false;
  benchmark_evidence: false;
};

export type GoalMutationReceipt = {
  schema: "pex.goal-mutation-receipt.v1";
  mode: "create" | "update" | "override";
  changed: boolean;
  predecessor_goal_id: string | null;
  before_intent_revision: number | null;
  after_intent_revision: number;
  before_intent_hash: string | null;
  after_intent_hash: string;
  reattached_session_ids: string[];
};

export type GoalMutationResponse = Goal & {
  goal_mutation_receipt: GoalMutationReceipt;
  reattached_session_ids: string[];
  operator_operation_receipt?: OperatorIntentOperationReceipt;
};

export type CatalogPet = {
  id: string;
  display_name: string;
  description: string;
  species?: string;
  atlas_ready?: boolean;
  source?: "starter" | "imported" | "hatched";
};

export type HatchJobRow = {
  id: string;
  display_name: string;
  status: string;
  step: string;
  jobs_complete: number;
  jobs_total: number;
  error?: string | null;
};

export type HatchBaseCandidateRequest = {
  display_name: string;
  description: string;
  style_preset: string;
  pet_notes: string;
  idempotency_key: string;
  confirm_one_base_candidate_call: true;
};

export type HatchCap = {
  ok?: boolean;
  has_image_endpoint?: boolean;
  generation_ready?: boolean;
  provider?: string;
  reason?: string;
  note?: string;
};

export type SupervisorRow = {
  provider: string;
  model_id: string;
  label: string;
  source?: "static_hint" | "live_provider_list";
  availability?: "unverified" | "listed";
};

export type SupervisorInfo = {
  dispatch_limit_override?: number | null;
  max_dispatches_per_session?: number | null;
  version?: 1;
  revision?: number;
  backend?: string | null;
  provider?: string | null;
  model_id?: string | null;
  base_url?: string | null;
  has_api_key?: boolean;
  auth_mode?: string | null;
  protocol?: "openai" | "anthropic" | null;
  credential_source?: "none" | "environment" | "secret_store";
  credential_configured?: boolean;
  requested_auth?: string | null;
  login_implemented?: boolean;
  login_note?: string;
  catalog?: SupervisorRow[];
  providers?: string[];
  note?: string;
  model_loaded?: boolean;
  error?: string;
};

export type ChannelStatus = {
  id: string;
  label: string;
  configured: boolean;
  connected: boolean;
  notes: string;
};

export type ChannelHubStatus = {
  attention_policy?: string;
  channels?: ChannelStatus[];
};

export type ProposedAction = {
  type?: string;
  payload?: Record<string, unknown>;
  rationale?: string;
  expected_benefit?: string;
};

export type Intervention = {
  id: string;
  session_id: string;
  goal_id?: string | null;
  trigger?: string;
  evidence?: string[];
  diagnosis?: string;
  proposed_action?: ProposedAction;
  confidence?: number;
  risk?: string;
  reversible?: boolean;
  authority_required?: string;
  action_taken: string;
  policy_verdict?: string;
  result?: string;
  worker_response?: string;
  outcome?: string;
  helped?: boolean | null;
  created_at?: string;
  metadata?: Record<string, unknown>;
};

export type HandoffAssimilationEvidence = {
  schema: "pex.handoff-assimilation-evidence.v1";
  evidence_id: string;
  effect_id: string;
  handoff_intervention_id: string;
  bundle_digest: string;
  dispatch_started_at: string;
  dispatch_version: number;
  dispatch_target_accept_seq_through: number;
  source_session_id: string;
  source_vendor_session_id: string;
  source_harness_type: string;
  target_session_id: string;
  target_vendor_session_id: string;
  target_harness_type: string;
  source_project_id: string;
  target_project_id: string;
  source_project_binding: string;
  target_project_binding: string;
  goal_project_binding: string;
  goal_id: string;
  target_event_id: string;
  target_event_type: string;
  target_event_accept_seq: number | null;
  target_mutation_id: string | null;
  evidence_kind: "artifact_read" | "artifact_edit" | "target_acknowledgement";
  evidence_strength: "behavioral" | "self_attested";
  matched_context_item_ids: string[];
  matched_artifact_paths: string[];
  target_event_ts: string;
  observed_at: string;
  status: "observed";
  verified: false;
  assimilation_proven: false;
};

export type HandoffDispatchWatermark = {
  schema: "pex.handoff-dispatch-watermark.v1" | "pex.handoff-dispatch-watermark.v2";
  effect_id: string;
  target_session_id: string;
  target_accept_seq_through: number;
  dispatch_started_at: string;
  effect_version: number;
  candidate_index_schema?: "pex.handoff-candidate-manifest.v1";
  context_candidate_count?: number;
  artifact_candidate_count?: number;
  candidate_index_digest?: string;
};

export type HandoffTargetAction = {
  event_id: string;
  event_type: string;
  phase: string;
  accept_seq: number;
  accepted_at: string;
  event_ts: string;
  classification:
    | "relevant_action_observed"
    | "possible_failure_observed"
    | "other_target_action_observed";
  evidence_ids: string[];
  possible_failure: boolean;
  handoff_failure_proven: false;
};

export type HandoffAssimilationStatus = {
  schema: "pex.handoff-assimilation-status.v1";
  effect_id: string;
  handoff_intervention_id: string;
  bundle_digest: string;
  delivery_status: string;
  delivery_finished_at: string | null;
  delivery_version: number | null;
  status:
    | "not_delivered"
    | "monitoring_unavailable_legacy"
    | "relevant_action_observed"
    | "target_acknowledged"
    | "evidence_window_expired"
    | "awaiting_target_evidence";
  assimilation_proven: false;
  watermark: HandoffDispatchWatermark | null;
  typed_evidence_monitoring: {
    available: boolean;
    routing: "immutable_dispatch_candidate_index" | "unavailable_legacy";
    capacity_limited: false;
  };
  monitoring_expires_at: string | null;
  first_relevant_action: HandoffAssimilationEvidence | null;
  target_action_monitoring: {
    available: boolean;
    scope: "first_three_meaningful_accepted_target_events";
    observed_count: number;
    actions_truncated: boolean;
    possible_failure_observed: boolean;
    handoff_failure_proven: false;
    actions: HandoffTargetAction[];
  };
  evidence: HandoffAssimilationEvidence[];
};

export type AttentionMetrics = {
  schema: "pex.attention-metrics.v1";
  definition_version: 1;
  scope: {
    kind: "all_local_durable_history";
    project_id: null;
    goal_id: null;
    session_id: null;
    includes_historical_authority: true;
  };
  window: {
    kind: "all_time";
    started_at: string | null;
    ended_at: string;
    as_of: string;
    records_considered: number;
    aggregate_truncated: false;
    detail_rows_truncated: boolean | null;
  };
  authority: {
    source: "canonical_sqlite_ledgers";
    consistent_read_snapshot: true;
    watermarks: Record<string, number>;
  };
  coverage: {
    complete: boolean;
    coverage_started_at: string | null;
    excluded_legacy_or_unbound_source_rows: number;
    actor_assured_action_coverage: Array<{
      schema: "pex.human-action-coverage.v1";
      action_kind:
        | "pause_supervision"
        | "resume_supervision"
        | "session_message"
        | "context_handoff";
      coverage_started_at: string;
      actor_assurance: "bridge_bearer";
      schema_version: 1;
    }>;
    unmeasured_action_kinds: string[];
  };
  human_interventions: {
    value: number | null;
    measured: boolean;
    observed_count: number;
    coverage_complete: boolean;
    source_counts: Record<string, number>;
    unverified_operator_action_counts: Record<string, number>;
    actor_assured_operator_message_outcomes: Record<string, number>;
    actor_assured_operator_handoff_outcomes: Record<string, number>;
    null_reason: string | null;
    unmeasured_action_kinds: string[];
  };
  human_intervention_requests: {
    value: number;
    measured: true;
    definition: string;
  };
  decisions: {
    requested: number;
    resolved: number;
    pending: number;
    delivery_uncertain: number;
    measured: true;
    scope_note: string;
  };
  current_pending: {
    count: number;
    items: Intervention[];
    items_limit: number;
    items_truncated: boolean;
    unexplained_session_count: number;
    scope: "current_live_authority";
  };
  human_active_seconds: {
    value: number | null;
    measured: boolean;
    consent: "not_configured" | "disabled" | "enabled";
    interval_count: number;
    null_reason: string | null;
  };
  unnecessary_alert_rate: {
    value: number | null;
    measured: boolean;
    numerator: number;
    denominator: number;
    alerts_shown: number | null;
    alerts_adjudicated: number;
    alerts_unjudged: number | null;
    null_reason: string | null;
  };
  average_auto_resolution_confidence: {
    value: number | null;
    measured: boolean;
    sample_count: number;
    eligible_resolution_count: number | null;
    null_reason: string | null;
  };
  reversals: {
    value: number;
    measured: true;
    attempted: number;
    completed: number;
    failed: number;
    delivery_uncertain: number;
    definition: string;
  };
  benchmark_evidence: false;
};

export type PermissionDecision = "allow" | "deny";

export type HumanDecisionChoice = string;

export type DecisionDeliveryStatus =
  | "delivered"
  | "unsupported"
  | "rejected"
  | "failed"
  | "delivery_uncertain"
  | "dispatching";

export type DecisionFeedback = {
  interventionId: string;
  state: "submitting" | "success" | "error";
  decision: HumanDecisionChoice;
  message: string;
  deliveryStatus?: DecisionDeliveryStatus;
};

export type ProjectOriginView = {
  namespace: string;
  host: string;
};

export type ProjectPhysicalIdentityProofView = {
  provider: string;
  volume_id: string;
  object_id: string;
};

export type ProjectLocatorView = {
  schema: "pex.project-locator.v2";
  kind:
    | "local_path"
    | "remote_path"
    | "repository_uri"
    | "provider_workspace"
    | "workspace_set"
    | "opaque";
  raw: string;
  canonical: string;
  origin: ProjectOriginView;
  platform?: "posix" | "windows" | null;
  members: ProjectLocatorView[];
  physical?: ProjectPhysicalIdentityProofView | null;
};

export type ProjectIdentityView = {
  schema: "pex.project-identity.v2";
  id: string;
  locator_fingerprints: string[];
  created_at: string;
};

export type ProjectIdentityCandidateView = {
  identity: ProjectIdentityView;
  locators: ProjectLocatorView[];
};

export type ProjectIdentityConflictSummary = {
  schema: "pex.project-identity-conflict-summary.v1";
  legacy_project_id: string;
  status: "quarantined";
  candidate_identity_ids: string[];
  candidate_count: number;
  quarantined_at?: string | null;
  updated_at?: string | null;
};

export type ProjectIdentityConflictPage = {
  schema: "pex.project-identity-conflict-page.v1";
  items: ProjectIdentityConflictSummary[];
  total: number;
  offset: number;
  next_offset: number | null;
};

export type ProjectIdentityResolutionReceipt = {
  schema: "pex.project-identity-resolution.v1";
  resolution_id: string;
  legacy_project_id: string;
  selected_identity_id: string;
  candidate_identity_ids: string[];
  resolved_by: string;
  rationale: string;
  resolved_at: string;
  credentials_restored: false;
  resolved_binding: Record<string, unknown>;
};

type ProjectIdentityStatusBase = {
  schema: "pex.project-identity-status.v1";
  legacy_project_id: string;
  credential_reissue_blocked: boolean;
  fresh_credentials_required: boolean;
};

export type ProjectIdentityUnregisteredStatus = ProjectIdentityStatusBase & {
  status: "unregistered";
};

export type ProjectIdentityActiveStatus = ProjectIdentityStatusBase & {
  status: "active";
  identity: ProjectIdentityView;
  locators: ProjectLocatorView[];
  binding: Record<string, unknown>;
  last_resolution: ProjectIdentityResolutionReceipt | null;
};

export type ProjectIdentityQuarantinedStatus = ProjectIdentityStatusBase & {
  status: "quarantined";
  binding: Record<string, unknown>;
  candidate_count: number;
  candidate_offset: number;
  next_candidate_offset: number | null;
  candidates: ProjectIdentityCandidateView[];
};

export type ProjectIdentityStatusView =
  | ProjectIdentityUnregisteredStatus
  | ProjectIdentityActiveStatus
  | ProjectIdentityQuarantinedStatus;

export type ProjectIdentityResolutionResponse = {
  outcome: "resolved" | "replayed";
  current_status: "active" | "quarantined";
  fresh_credentials_required: true;
  identity: ProjectIdentityView;
  binding: Record<string, unknown>;
  resolution: ProjectIdentityResolutionReceipt;
};

export type ProjectIdentityFeedback = {
  state: "submitting" | "success" | "error";
  message: string;
};

export type ContextItem = {
  id: string;
  project_id: string;
  goal_id?: string | null;
  kind: string;
  content: string;
  source_refs?: string[];
  provenance?: string;
  confidence?: number;
  relevance_tags?: string[];
  stale_after?: string | null;
  supersedes?: string | null;
  sensitivity?: string;
};

export type AdapterRow = {
  name: string;
  capabilities?: {
    support_label?: string;
    notes?: string;
    [key: string]: unknown;
  };
};

export type Fingerprint = {
  harness: string;
  observed_sessions: number;
  models?: string[];
  premature_stop_sessions?: number;
  verified_stop_sessions?: number;
  overlay_sessions?: number;
  inspected_stop_sessions?: number;
  premature_stop_rate: number;
  verified_success_rate?: number;
  strengths?: string[];
  failure_modes?: string[];
  recommended_overlays?: string[];
  token_efficiency?: number | string | null;
};

export type DeckData = {
  sessions?: SessionRow[];
  interventions?: Intervention[];
  adapters?: AdapterRow[];
  fingerprints?: Fingerprint[];
};

export type BenchMetrics = {
  task_success_rate?: number;
  human_interventions_per_success?: number;
  useful_interventions?: number;
  harmful_interventions?: number;
  context_handoffs?: number;
  [key: string]: number | string | boolean | null | undefined;
};

export type BenchRun = {
  id: string;
  name?: string;
  status?: string;
  arm?: string;
  harness?: string;
  created_at?: string;
  manifest_hash?: string;
  frozen?: boolean;
  metrics?: BenchMetrics;
};

export type StarterHarnessInventory = {
  running: string[];
  not_running: string[];
};

export type BenchState = {
  loading: boolean;
  runs: BenchRun[];
  message?: string;
  inventory?: StarterHarnessInventory;
};

export type StatusCopy = {
  tone: "quiet" | "work" | "watch" | "need" | "offline";
  label: string;
  detail: string;
};

export type CanonicalResourceKey =
  | "pet"
  | "pets"
  | "goals"
  | "deck"
  | "context"
  | "interventions"
  | "decisions"
  | "completion"
  | "supervisor"
  | "channels";

export type CanonicalResourceStatus = "loading" | "fresh" | "stale" | "unavailable";

export type CanonicalResourceState = {
  status: CanonicalResourceStatus;
  error: string | null;
  lastSuccessAt: string | null;
};

export type CanonicalResourceMap = Record<CanonicalResourceKey, CanonicalResourceState>;

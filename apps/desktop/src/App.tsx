import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { CommandDeck } from "./components/CommandDeck";
import type { GoalDraft } from "./components/GoalEditor";
import {
  BridgeRequestError,
  bridgeRequestError,
  humanDecisionFailurePresentation,
  humanDecisionFeedbackChoice,
  humanDecisionPresentation,
  isRecord,
} from "./decisionContract";
import { Inspector } from "./components/Inspector";
import { PetStage } from "./components/PetStage";
import { SettingsPage, type SettingsSection } from "./components/SettingsPage";
import { SharedConnectionPanel } from "./components/SharedConnectionPanel";
import { OpenCodeConnectionPanel } from "./components/OpenCodeConnectionPanel";
import { createOperatorRequest } from "./operatorRequest";
import { canEditGoalLedger, goalLedgerKey, readGoalDecisions } from "./goalLedger";
import { usePageVisibility } from "./pageVisibility";
import {
  boundedRead, boundedReadBatch, boundedSingleFlightRead, coalesceBackgroundRead,
  startSerialPolling,
} from "./readBudget";
import { firstRunGuidance, statusWithFirstRunGuidance, supervisorAvailability } from "./firstRun";
import { StartupRecovery } from "./components/StartupRecovery";
import { CodexSprite } from "./pets/atlas";
import bundledPexSheet from "./pets/pex/spritesheet.webp";
import { applyPetClickThrough, expandMainSurface, hidePetOverlay, nextPetExpansion, PET_NATIVE_DISMISSED_EVENT, PET_VISIBILITY_EVENT, petClickThroughEnabled, petOverlayVisible, petVisibilityNote, reconcilePetVisibilityNote, releasePetOverlay, setPetOverlayVisible, showPetOverlay } from "./releasePet";
import {
  advanceBridgeBootstrapStatus,
  bridgeBootstrapAvailable,
  bridgeBootstrapPollInterval,
  browserDevelopmentBridgeStatus,
  initialBridgeBootstrapStatus,
  normalizeBridgeBootstrapStatus,
  shouldPollBridgeBootstrap,
  unavailableBridgeBootstrapStatus,
} from "./startupRecovery";
import {
  isSupervisorRevision,
  supervisorActivationRefreshDisposition,
  supervisorCredentialAudience,
  supervisorRequest,
  supervisorSavePayload,
  supervisorDispatchLimitDraft,
  supervisorSaveResponseIsCurrent,
  supervisorSaveConfirmation,
  type SupervisorAuthMode,
  type SupervisorCredentialAction,
  type SupervisorProtocol,
} from "./supervisorDraft";
import type {
  BenchRun,
  BenchState,
  AttentionMetrics,
  BridgeBootstrapStatus,
  CatalogPet,
  CanonicalResourceKey,
  ChannelHubStatus,
  ContextItem,
  CursorInboxRejectionPage,
  DecisionFeedback,
  DeckData,
  DeckView,
  Goal,
  GoalCompletion,
  GoalMutationResponse,
  HandoffAssimilationStatus,
  HumanDecisionChoice,
  Intervention,
  LastAction,
  LedgerDecision,
  PetSnapshot,
  PermissionDecision,
  ProjectIdentityConflictPage,
  ProjectIdentityFeedback,
  ProjectIdentityResolutionResponse,
  ProjectIdentityStatusView,
  SessionRow,
  SessionGoalAttachmentResponse,
  SupervisorInfo,
  Surface,
} from "./types";
import {
  canAttachPersistentGoal,
  canFocusSession,
  canOpenSession,
  canonicalResourceIssue,
  canonicalResourceIsFreshForScope,
  canonicalResourcesAreFresh,
  createGoalPayload,
  currentGoals,
  canonicalEventCursor,
  encodeWebSocketTokenProtocol,
  eventPageResumeCursor,
  goalToDraft,
  newUndoIdempotencyKey,
  isPendingHumanDecision,
  isPendingLifecycleDecision,
  isPendingRequestedHumanDecision,
  moodForState,
  initialCanonicalResources,
  prepareGoalControlAttempt,
  type GoalControlAttempt,
  prepareUndoAttempt,
  projectCompletedOverlayUndo,
  projectIdentityCompletionIsCurrent,
  projectIdentityResolutionMessage,
  type ProjectIdentityResolutionAttempt,
  reconnectDelay,
  selectPrimarySession,
  mergeSessionObservation,
  sessionGoalAttachmentPayload,
  splitPetCatalog,
  settleCanonicalResource,
  sessionExternalUrl,
  starterInventoryFromDiscover,
  statusCopy,
  titleCase,
  type UndoAttempt,
  undoFailureMessage,
  undoResponsePresentation,
  updateGoalPayload,
} from "./viewModel";

const BRIDGE = "http://127.0.0.1:7420";
const EVENT_CURSOR_STORAGE_KEY = "pex.event_cursor.v1";
const PET_RECONCILIATION_INTERVAL_MS = 30_000;
const BASE_STATE_RECONCILIATION_INTERVAL_MS = 30_000;
const SETTINGS_ACTIVITY_RECONCILIATION_INTERVAL_MS = 30_000;
const GOAL_EVIDENCE_RECONCILIATION_INTERVAL_MS = 30_000;
const HANDOFF_ASSIMILATION_RECONCILIATION_INTERVAL_MS = 30_000;
const PROJECT_IDENTITY_RECONCILIATION_INTERVAL_MS = 30_000;
const DETAIL_RECONCILIATION_INTERVAL_MS = 32_000;

function defaultSupervisorAuth(provider: string): SupervisorAuthMode {
  if (["ollama", "lmstudio", "llamacpp", "vllm"].includes(provider)) return "local";
  if (provider === "custom") return "custom";
  if (provider === "bedrock") return "bedrock";
  return "api_key";
}
const TAURI = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
const EMPTY_GOAL: GoalDraft = {
  projectId: "",
  title: "",
  objective: "",
  acceptance: "",
  constraints: "",
  nonGoals: "",
  preferences: "",
  evidence: "",
  decisions: "",
  rejectedApproaches: "",
  unresolvedQuestions: "",
};

type Shell = "main" | "settings" | "pet";
type HookHarness = "cursor" | "claude_code" | "qwen" | "hermes" | "opencode";
type HookBootstrapReceipt = {
  credential_id: string;
  project_id: string;
  harness_type: HookHarness;
  expires_at: string;
  token: string;
};

type UndoResponse = {
  ok?: boolean;
  code?: string;
  state?: string;
  status?: string;
  replayed?: boolean;
  receipt?: {
    operation_id?: string;
    intervention_id?: string;
    state?: string;
    version?: number;
    reserved_at?: string;
    dispatch_started_at?: string;
    finished_at?: string;
    resource_count?: number;
    result?: Record<string, string> | null;
  };
};

const HOOK_ENVIRONMENT: Record<HookHarness, string> = {
  cursor: "PEX_CURSOR_HOOK_TOKEN",
  claude_code: "PEX_HOOK_TOKEN",
  qwen: "PEX_HOOK_TOKEN",
  hermes: "PEX_HERMES_HOOK_TOKEN",
  opencode: "PEX_OPENCODE_HOOK_TOKEN",
};
let bridgeTokenRequest: Promise<string> | null = null;

// Native IPC reads cannot be aborted by fetch's signal. Share one pending call,
// retire a timed-out result, and require a fresh observation after it settles.
const readNativeBridgeBootstrap = boundedSingleFlightRead(async () => {
  const { invoke: call } = await import("@tauri-apps/api/core");
  return call<unknown>("bridge_bootstrap_status");
});

async function readBridgeBootstrapStatus(signal?: AbortSignal): Promise<BridgeBootstrapStatus | null> {
  if (!TAURI) return browserDevelopmentBridgeStatus;
  try {
    const status = normalizeBridgeBootstrapStatus(await readNativeBridgeBootstrap(signal));
    return status.code === "desktop_control_unavailable" || status.code === "desktop_state_unavailable"
      ? null
      : status;
  } catch {
    return null;
  }
}

// A timed-out retry may still be running in native code. Release the UI wait,
// but retain that pending invocation so another click cannot duplicate it.
const retryNativeBridgeBootstrap = boundedSingleFlightRead(async () => {
  const { invoke: call } = await import("@tauri-apps/api/core");
  return call<unknown>("retry_bridge");
});

async function retryDesktopBridge(): Promise<BridgeBootstrapStatus | null> {
  try {
    const status = normalizeBridgeBootstrapStatus(await retryNativeBridgeBootstrap());
    return status.code === "desktop_control_unavailable" || status.code === "desktop_state_unavailable"
      ? null
      : status;
  } catch {
    return null;
  }
}

async function bridgeToken(): Promise<string | null> {
  if (!TAURI) return null;
  if (bridgeTokenRequest) return bridgeTokenRequest;
  const request = import("@tauri-apps/api/core")
    .then(({ invoke: call }) => call<string>("bridge_token"))
    .then((token) => {
      const value = token.trim();
      if (!value) throw new Error("PEX bridge token is empty.");
      return value;
    })
    .catch((error) => {
      bridgeTokenRequest = null;
      throw error;
    });
  bridgeTokenRequest = request;
  // Retain the verified token promise for this desktop bridge generation.
  // Re-probing before every parallel startup fetch can starve the bridge's
  // identity endpoint while a bounded adapter probe is running. The promise is
  // cleared on bridge generation change, WebSocket close, 401, or explicit
  // retry, so a restarted port owner must prove the in-memory token again.
  return request;
}

async function bridgeFetch(path: string, init?: RequestInit): Promise<Response> {
  // The packaged desktop must never downgrade to an unauthenticated request:
  // bridgeToken() first proves that the current port owner knows the secret.
  // Plain Vite/browser development remains tokenless because TAURI is false.
  const token = await bridgeToken();
  const send = (value: string | null) => {
    const headers = new Headers(init?.headers);
    if (value) headers.set("Authorization", `Bearer ${value}`);
    return fetch(`${BRIDGE}${path}`, { ...init, headers });
  };
  const response = await send(token);
  if (response.status !== 401 || !TAURI || !token) return response;

  // The bridge can rotate its local token after a restart. Re-read once and
  // retry the same local request; never persist the token in web storage.
  bridgeTokenRequest = null;
  const refreshed = await bridgeToken();
  return send(refreshed);
}

// Connection/configuration mutations are single-attempt, including auth failure.
// The user reloads canonical status before deciding whether to try again.
const sharedConnectionRequest = createOperatorRequest({ baseUrl: BRIDGE, readToken: bridgeToken });

async function bridgeJson<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (method === "GET") {
    return boundedRead((signal) => readBridgeJson<T>(path, { ...init, signal }), init?.signal);
  }
  // Do not change mutation retry/unknown-outcome semantics with a polling budget.
  return readBridgeJson<T>(path, init);
}

async function readBridgeJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await bridgeFetch(path, init);
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json() as unknown;
    } catch {
      // Keep the HTTP status when the bridge did not return structured JSON.
    }
    throw bridgeRequestError(response.status, response.statusText, payload);
  }
  return response.json() as Promise<T>;
}

function interventionHandoffEffectId(item: Intervention): string | null {
  const deliveryStatus = item.metadata?.handoff_delivery_status;
  if (item.action_taken !== "FRESH_HANDOFF" && typeof deliveryStatus !== "string") {
    return null;
  }
  const effectId = item.metadata?.operator_effect_id;
  return typeof effectId === "string" && effectId.trim() ? effectId.trim() : null;
}

function handoffInterventionFingerprint(interventions: Intervention[]): string {
  return Array.from(new Set(
    interventions
      .map(interventionHandoffEffectId)
      .filter((effectId): effectId is string => effectId !== null),
  )).join("\n");
}

async function loadHandoffAssimilationStatuses(
  interventions: Intervention[],
  signal?: AbortSignal,
): Promise<Record<string, HandoffAssimilationStatus | "unreachable">> {
  const effectIds = Array.from(new Set(
    interventions
      .map(interventionHandoffEffectId)
      .filter((effectId): effectId is string => effectId !== null),
  ));
  const settled = await boundedReadBatch(
    effectIds, async (effectId, readSignal) => ({
      effectId,
      status: await bridgeJson<HandoffAssimilationStatus>(
        `/v1/handoffs/${encodeURIComponent(effectId)}/assimilation`,
        { signal: readSignal },
      ),
    }), signal,
  );
  const statuses: Record<string, HandoffAssimilationStatus | "unreachable"> = {};
  settled.forEach((result, index) => {
    const effectId = effectIds[index];
    if (result.status === "rejected") {
      statuses[effectId] = "unreachable";
      return;
    }
    statuses[effectId] = result.value.status;
    statuses[result.value.status.handoff_intervention_id] = result.value.status;
  });
  return statuses;
}

function operationError(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim()
    ? `${fallback} ${error.message.trim()}`
    : fallback;
}

export function App() {
  const [pet, setPet] = useState<PetSnapshot | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [bridgeStartup, setBridgeStartup] = useState<BridgeBootstrapStatus>(() => (
    TAURI ? initialBridgeBootstrapStatus : browserDevelopmentBridgeStatus
  ));
  const [bridgeControlAvailable, setBridgeControlAvailable] = useState(true);
  const [bridgeRetrying, setBridgeRetrying] = useState(false);
  const [canonicalResources, setCanonicalResources] = useState(initialCanonicalResources);
  const [shell, setShell] = useState<Shell>(() => shellFromHash());
  const [surface, setSurface] = useState<Surface>(() => surfaceFromHash());
  const [activeView, setActiveView] = useState<DeckView>("now");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [goalDraft, setGoalDraft] = useState<GoalDraft>(EMPTY_GOAL);
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null);
  const [settingsDestination, setSettingsDestination] = useState<SettingsSection | undefined>();
  const [goalFocusRequest, setGoalFocusRequest] = useState(0);
  const [ledgerDecisions, setLedgerDecisions] = useState<LedgerDecision[]>([]);
  const loadedGoalLedgerKey = useRef<string | null>(null);
  const editingGoalLedgerKey = useRef<string | null>(null);
  const [goalCompletion, setGoalCompletion] = useState<GoalCompletion | null>(null);
  const [savingGoal, setSavingGoal] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [builtInRoster, setBuiltInRoster] = useState<CatalogPet[]>([]);
  const [petFleetIssues, setPetFleetIssues] = useState<string[]>([]);
  const [deck, setDeck] = useState<DeckData>({});
  const [contextItems, setContextItems] = useState<ContextItem[]>([]);
  const [contextProjectId, setContextProjectId] = useState<string | null>(null);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [handoffAssimilation, setHandoffAssimilation] =
    useState<Record<string, HandoffAssimilationStatus | "unreachable">>({});
  const [attentionMetrics, setAttentionMetrics] = useState<AttentionMetrics | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [decisionFeedback, setDecisionFeedback] = useState<DecisionFeedback | null>(null);
  const [identityConflicts, setIdentityConflicts] =
    useState<ProjectIdentityConflictPage | null>(null);
  const [identityTargetProjectId, setIdentityTargetProjectId] = useState<string | null>(null);
  const [identityStatus, setIdentityStatus] = useState<ProjectIdentityStatusView | null>(null);
  const [identityConflictLoading, setIdentityConflictLoading] = useState(false);
  const [identityConflictError, setIdentityConflictError] = useState<string | null>(null);
  const [identityStatusLoading, setIdentityStatusLoading] = useState(false);
  const [identityStatusError, setIdentityStatusError] = useState<string | null>(null);
  const [identityResolving, setIdentityResolving] = useState(false);
  const [identityFeedback, setIdentityFeedback] = useState<ProjectIdentityFeedback | null>(null);
  const [bench, setBench] = useState<BenchState>({ loading: false, runs: [] });
  const [scale, setScale] = useState(1);
  const [nickname, setNickname] = useState("");
  const [clickThrough, setClickThrough] = useState(false);
  const [petVisible, setPetVisible] = useState(petOverlayVisible);
  const pageVisible = usePageVisibility();
  const observationActive = pageVisible && (shell !== "pet" || petVisible);

  useEffect(() => {
    const acceptVisibility = (visible: boolean) => {
      setPetVisible(visible);
      setNote((current) => reconcilePetVisibilityNote(current, visible));
    };
    const syncVisibility = () => acceptVisibility(petOverlayVisible());
    const syncDirectVisibility = (event: Event) => acceptVisibility(Boolean((event as CustomEvent).detail));
    window.addEventListener("storage", syncVisibility);
    window.addEventListener(PET_VISIBILITY_EVENT, syncDirectVisibility);
    return () => {
      window.removeEventListener("storage", syncVisibility);
      window.removeEventListener(PET_VISIBILITY_EVENT, syncDirectVisibility);
    };
  }, []);

  useEffect(() => {
    if (observationActive) return;
    // Hidden webviews and a user-hidden native pet release their readers below.
    // Their last snapshots remain useful for rendering, but cannot retain mutation
    // authority until every relevant canonical resource refreshes after reactivation.
    setCanonicalResources(initialCanonicalResources());
  }, [observationActive]);
  const [hookHarness, setHookHarness] = useState<HookHarness>("cursor");
  const [hookProject, setHookProject] = useState("");
  const [hookBootstrap, setHookBootstrap] = useState<HookBootstrapReceipt | null>(null);
  const [cursorRejections, setCursorRejections] = useState<CursorInboxRejectionPage | null>(null);
  const [provisioningHook, setProvisioningHook] = useState(false);
  const goalControlAttempts = useRef(new Map<string, GoalControlAttempt>());
  const undoAttempts = useRef(new Map<string, UndoAttempt>());
  const undoRequestsInFlight = useRef(new Set<string>());
  const [completedOverlayUndoIds, setCompletedOverlayUndoIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [supervisor, setSupervisor] = useState<SupervisorInfo | null>(null);
  const [channels, setChannels] = useState<ChannelHubStatus | null>(null);
  const [supervisorProvider, setSupervisorProvider] = useState("");
  const [supervisorModel, setSupervisorModel] = useState("");
  const [supervisorAuth, setSupervisorAuth] = useState<SupervisorAuthMode>("api_key");
  const [supervisorProtocol, setSupervisorProtocol] = useState<SupervisorProtocol>("openai");
  const [supervisorBaseUrl, setSupervisorBaseUrl] = useState("");
  const [supervisorDispatchLimit, setSupervisorDispatchLimit] = useState<string | undefined>();
  const [supervisorApiKey, setSupervisorApiKey] = useState("");
  const [supervisorCredentialAction, setSupervisorCredentialAction] =
    useState<SupervisorCredentialAction>("keep");
  const [savingSupervisor, setSavingSupervisor] = useState(false);
  const [refreshingCatalog, setRefreshingCatalog] = useState(false);
  const [attachingGoal, setAttachingGoal] = useState(false);
  const [selectingPet, setSelectingPet] = useState(false);
  const askInput = useRef<HTMLInputElement>(null);
  const petRequestSequence = useRef(0);
  const baseRequestSequence = useRef(0);
  const cursorRejectionRequestSequence = useRef(0);
  const detailRequestSequence = useRef(0);
  const identityConflictRequestSequence = useRef(0);
  const identityStatusRequestSequence = useRef(0);
  const identityResolutionRequestSequence = useRef(0);
  const identitySelectionRevision = useRef(0);
  const identitySelectedProjectIdRef = useRef("");
  const settingsRequestSequence = useRef(0);
  const supervisorDraftRevision = useRef(0);
  const supervisorSaveInFlight = useRef(false);
  const supervisorKeyAudience = useRef<string | null>(null);
  const goalEvidenceKey = useRef<string | null>(null);
  const goalEvidenceRefresh = useRef<(() => Promise<unknown>) | null>(null);
  const handoffInterventions = useRef<Intervention[]>([]);
  const handoffInterventionKey = useRef("");
  const handoffAssimilationRefresh = useRef<(() => Promise<unknown>) | null>(null);
  const detailRefresh = useRef<(() => Promise<unknown>) | null>(null);
  const identityConflictRefresh = useRef<(() => Promise<unknown>) | null>(null);
  const identityStatusRefresh = useRef<(() => Promise<unknown>) | null>(null);
  const bridgeStartupRef = useRef(bridgeStartup);
  const bridgeAvailable = bridgeBootstrapAvailable(
    TAURI,
    shell,
    bridgeControlAvailable,
    bridgeStartup,
  );

  const acceptBridgeStartupStatus = useCallback((incoming: BridgeBootstrapStatus) => {
    const previous = bridgeStartupRef.current;
    const next = advanceBridgeBootstrapStatus(previous, incoming);
    if (next === previous) return;
    bridgeStartupRef.current = next;
    if (previous.phase !== "ready" && next.phase === "ready") {
      // A new bridge generation must earn fresh canonical state before any
      // authoritative control becomes available.
      setCanonicalResources(initialCanonicalResources());
      setBridgeError(null);
    }
    if (previous.phase === "ready" && next.phase !== "ready") {
      bridgeTokenRequest = null;
    }
    setBridgeStartup(next);
  }, []);

  useEffect(() => {
    if (!pageVisible || !shouldPollBridgeBootstrap(TAURI, shell)) return;
    const stopPolling = startSerialPolling(async (signal) => {
      const next = await readBridgeBootstrapStatus(signal);
      if (signal.aborted) return;
      setBridgeControlAvailable(next !== null);
      if (next) acceptBridgeStartupStatus(next);
    }, bridgeBootstrapPollInterval(bridgeStartup.phase));
    return stopPolling;
  }, [acceptBridgeStartupStatus, bridgeStartup.phase, pageVisible, shell]);

  const retryBridgeBootstrap = useCallback(async () => {
    if (!bridgeStartup.retryable || bridgeRetrying) return;
    setBridgeRetrying(true);
    bridgeTokenRequest = null;
    const next = await retryDesktopBridge();
    setBridgeControlAvailable(next !== null);
    if (next) acceptBridgeStartupStatus(next);
    setBridgeRetrying(false);
  }, [acceptBridgeStartupStatus, bridgeRetrying, bridgeStartup.retryable]);

  const markCanonical = useCallback((
    key: CanonicalResourceKey,
    outcome: "fresh" | "failed" | "loading" | "reset",
    error?: string,
  ) => {
    setCanonicalResources((currentState) => settleCanonicalResource(
      currentState,
      key,
      outcome,
      { error },
    ));
  }, []);

  const refreshPet = useCallback(async (signal?: AbortSignal) => {
    const requestSequence = ++petRequestSequence.current;
    try {
      const snapshot = await bridgeJson<PetSnapshot>("/v1/pet", { signal });
      if (requestSequence !== petRequestSequence.current) {
        return { status: "superseded" as const };
      }
      setPet(snapshot);
      setBridgeError(null);
      markCanonical("pet", "fresh");
      return { status: "applied" as const, snapshot };
    } catch {
      if (requestSequence !== petRequestSequence.current) {
        return { status: "superseded" as const };
      }
      setBridgeError("Bridge offline");
      markCanonical("pet", "failed", "Pet state could not be refreshed.");
      return { status: "failed" as const };
    }
  }, [markCanonical]);

  const loadBaseState = useCallback(async (signal?: AbortSignal) => {
    const requestSequence = ++baseRequestSequence.current;
    const [goalsResult, petsResult] = await Promise.allSettled([
      bridgeJson<Goal[]>("/v1/goals", { signal }),
      bridgeJson<{ catalog?: CatalogPet[]; starters?: CatalogPet[] }>("/v1/pets", { signal }),
    ]);
    if (requestSequence !== baseRequestSequence.current) return;
    if (goalsResult.status === "fulfilled" && Array.isArray(goalsResult.value)) {
      setGoals(goalsResult.value);
      markCanonical("goals", "fresh");
    } else {
      markCanonical("goals", "failed", "Persistent goals could not be refreshed.");
    }
    if (petsResult.status === "fulfilled") {
      const partitioned = splitPetCatalog(
        petsResult.value.starters || [],
        petsResult.value.catalog || petsResult.value.starters || [],
      );
      setBuiltInRoster(partitioned.builtIns);
      setPetFleetIssues(partitioned.fleetIssues);
      markCanonical("pets", "fresh");
    } else {
      markCanonical("pets", "failed", "Pet catalog could not be refreshed.");
    }
  }, [markCanonical]);

  const loadCursorRejections = useCallback(async (signal?: AbortSignal) => {
    const requestSequence = ++cursorRejectionRequestSequence.current;
    try {
      const data = await bridgeJson<CursorInboxRejectionPage>(
        "/v1/hooks/cursor/rejections?limit=20",
        { signal },
      );
      if (requestSequence !== cursorRejectionRequestSequence.current) return;
      setCursorRejections(data);
    } catch {
      if (requestSequence !== cursorRejectionRequestSequence.current) return;
      setCursorRejections(null);
    }
  }, []);

  const refreshPetGoals = useCallback(async (signal?: AbortSignal) => {
    const requestSequence = ++baseRequestSequence.current;
    try {
      const refreshed = await bridgeJson<Goal[]>("/v1/goals", { signal });
      if (requestSequence !== baseRequestSequence.current) return;
      if (!Array.isArray(refreshed)) throw new Error("invalid goal list");
      setGoals(refreshed);
      markCanonical("goals", "fresh");
    } catch {
      if (requestSequence !== baseRequestSequence.current) return;
      markCanonical("goals", "failed", "Persistent goals could not be refreshed.");
    }
  }, [markCanonical]);

  useEffect(() => {
    if (!bridgeAvailable || !observationActive) return;
    let cancelled = false;
    const controller = new AbortController();
    // Event bursts share the pending background read; explicit post-mutation
    // refreshes outside this effect still request their own fresh state.
    const refreshBackgroundPet = coalesceBackgroundRead<unknown>(() =>
      cancelled ? Promise.resolve() : refreshPet(controller.signal),
    );
    const stopPolling = startSerialPolling(
      refreshBackgroundPet,
      PET_RECONCILIATION_INTERVAL_MS,
    );
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let retryAttempt = 0;

    const scheduleReconnect = () => {
      if (cancelled || retryTimer != null) return;
      const delay = reconnectDelay(retryAttempt);
      retryAttempt += 1;
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        void connectSocket();
      }, delay);
    };

    const connectSocket = async () => {
      let token: string | null = null;
      try {
        token = await bridgeToken();
      } catch {
        if (!cancelled) setBridgeError("Bridge offline");
        scheduleReconnect();
        return;
      }
      if (cancelled) return;
      try {
        let resumeCursor = "0";
        try {
          resumeCursor = canonicalEventCursor(
            window.localStorage.getItem(EVENT_CURSOR_STORAGE_KEY),
          );
        } catch {
          /* Storage can be disabled; zero remains a safe explicit resync. */
        }
        const url = new URL(`${BRIDGE.replace(/^http/, "ws")}/v1/events`);
        url.searchParams.set("after", resumeCursor);
        const currentSocket = token
          ? new WebSocket(url, ["pex-v1", encodeWebSocketTokenProtocol(token)])
          : new WebSocket(url);
        socket = currentSocket;
        currentSocket.onopen = () => {
          retryAttempt = 0;
        };
        currentSocket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data) as { topic?: string; payload?: unknown };
            if (message.topic === "pet" && isRecord(message.payload) && !cancelled) {
              setPet(message.payload as PetSnapshot);
              setBridgeError(null);
              markCanonical("pet", "fresh");
            } else if (message.topic === "intervention" && !cancelled) {
              void refreshBackgroundPet();
            } else if (
              message.topic === "event_page" &&
              !cancelled &&
              socket === currentSocket
            ) {
              const nextCursor = eventPageResumeCursor(message.payload);
              if (nextCursor !== null) {
                try {
                  window.localStorage.setItem(EVENT_CURSOR_STORAGE_KEY, nextCursor);
                } catch {
                  /* Resume remains available for this live socket. */
                }
                // Canonical commits wake goal evidence immediately. Bursts
                // share each evidence effect's one in-flight reconciliation.
                void goalEvidenceRefresh.current?.();
                void handoffAssimilationRefresh.current?.();
                void detailRefresh.current?.();
                void identityConflictRefresh.current?.();
                void identityStatusRefresh.current?.();
              }
            }
          } catch {
            // Recover this observation immediately; the normal HTTP path is a
            // low-frequency reconciliation while authenticated frames are healthy.
            if (!cancelled) void refreshBackgroundPet();
          }
        };
        currentSocket.onerror = () => currentSocket.close();
        currentSocket.onclose = () => {
          if (socket === currentSocket) socket = null;
          bridgeTokenRequest = null;
          if (!cancelled) void refreshBackgroundPet();
          scheduleReconnect();
        };
      } catch {
        socket = null;
        if (!cancelled) setBridgeError("Bridge offline");
        scheduleReconnect();
      }
    };
    void connectSocket();
    return () => {
      cancelled = true;
      petRequestSequence.current += 1;
      controller.abort();
      stopPolling();
      if (retryTimer != null) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [bridgeAvailable, markCanonical, observationActive, refreshPet]);

  useEffect(() => {
    if (!bridgeAvailable || !pageVisible || shell === "pet") return;
    const stopPolling = startSerialPolling(
      (signal) => {
        return loadBaseState(signal);
      },
      BASE_STATE_RECONCILIATION_INTERVAL_MS,
    );
    return () => {
      baseRequestSequence.current += 1;
      stopPolling();
    };
  }, [bridgeAvailable, loadBaseState, pageVisible, shell]);

  useEffect(() => {
    if (!bridgeAvailable || !pageVisible || shell !== "settings") return;
    const stopPolling = startSerialPolling(
      (signal) => loadCursorRejections(signal),
      SETTINGS_ACTIVITY_RECONCILIATION_INTERVAL_MS,
    );
    return () => {
      cursorRejectionRequestSequence.current += 1;
      stopPolling();
    };
  }, [bridgeAvailable, loadCursorRejections, pageVisible, shell]);

  useEffect(() => {
    if (!bridgeAvailable || !observationActive || shell !== "pet") return;
    const stopPolling = startSerialPolling((signal) => refreshPetGoals(signal), 30000);
    return () => {
      baseRequestSequence.current += 1;
      stopPolling();
    };
  }, [bridgeAvailable, observationActive, refreshPetGoals, shell]);

  useEffect(() => {
    const route = () => {
      const routedShell = shellFromHash();
      setShell(routedShell);
      if (routedShell === "main") setSurface(surfaceFromHash());
    };
    route();
    window.addEventListener("hashchange", route);
    if (TAURI) {
      void import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
        if (getCurrentWindow().label === "pet") setShell("pet");
      });
    }
    return () => window.removeEventListener("hashchange", route);
  }, []);

  useEffect(() => {
    if (shell === "pet") return;
    const frame = window.requestAnimationFrame(() => {
      const selector = shell === "settings"
        ? '[data-settings-root="true"]'
        : `[data-surface-root="${surface}"]`;
      document.querySelector<HTMLElement>(selector)?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [shell, surface]);

  useEffect(() => {
    if (!goalFocusRequest || shell !== "main" || surface !== "inspector") return;
    const frame = window.requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>('[data-goal-setup="true"]');
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [goalFocusRequest, shell, surface]);

  useEffect(() => {
    if (!TAURI || shell === "pet") return;
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    void import("@tauri-apps/api/event").then(async ({ listen }) => {
      const dispose = await listen<Surface | "expand">("pex-open-surface", (event) => {
        if (event.payload === "expand") {
          setSurface((current) => {
            const next = nextPetExpansion(current);
            window.location.hash = next;
            return next;
          });
          setShell("main");
          return;
        }
        if (event.payload === "inspector" || event.payload === "deck" || event.payload === "compact") {
          setSurface(event.payload);
          setShell("main");
          window.location.hash = event.payload;
        }
      });
      if (cancelled) dispose();
      else unlisten = dispose;
    });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [shell]);

  useEffect(() => {
    if (!TAURI) return;
    let unlisten: (() => void) | undefined;
    let cancelled = false;
    void import("@tauri-apps/api/event").then(async ({ listen }) => {
      const dispose = await listen(PET_NATIVE_DISMISSED_EVENT, () => {
        setPetOverlayVisible(false);
      });
      if (cancelled) dispose();
      else unlisten = dispose;
    });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("pet-shell", shell === "pet");
    document.body.classList.toggle("pet-shell", shell === "pet");
    // Native configuration/setup owns the transparent canvas. The installed
    // JS background setter sends `color`, while the Rust plugin expects `value`;
    // that optional missing value resets the webview canvas to opaque white.
  }, [shell]);

  useEffect(() => {
    if (shell !== "pet") return;
    void applyPetClickThrough(petClickThroughEnabled(pet?.settings?.click_through));
  }, [pet?.settings?.click_through, shell]);

  useEffect(() => {
    if (!TAURI || !bridgeAvailable || !pet?.appearance?.id || shell === "pet") return;
    void releasePetOverlay();
  }, [bridgeAvailable, pet?.appearance?.id, shell]);

  useEffect(() => {
    setScale(pet?.settings?.scale ?? pet?.appearance?.scale ?? 1);
    setNickname(pet?.settings?.custom_name ?? "");
    setClickThrough(petClickThroughEnabled(pet?.settings?.click_through));
  }, [pet?.appearance?.scale, pet?.settings?.click_through, pet?.settings?.custom_name, pet?.settings?.scale]);

  const settingsAvailable = canonicalResourcesAreFresh(canonicalResources, ["supervisor"]);
  const loadSettings = useCallback(async () => {
    if (supervisorSaveInFlight.current) return;
    const requestSequence = ++settingsRequestSequence.current;
    const [supervisorResult, channelsResult] = await Promise.allSettled([
      supervisorRequest((signal) => bridgeJson<SupervisorInfo>("/v1/supervisor", { signal })),
      supervisorRequest((signal) => bridgeJson<ChannelHubStatus>("/v1/channels", { signal })),
    ]);
    if (requestSequence !== settingsRequestSequence.current) return;
    if (supervisorResult.status === "fulfilled" && isSupervisorRevision(supervisorResult.value?.revision)) {
      const data = supervisorResult.value;
      setSupervisor(data);
      setSupervisorProvider(data.backend || "");
      setSupervisorModel(data.model_id || "");
      setSupervisorAuth(
        (data.auth_mode as SupervisorAuthMode | null) ||
          defaultSupervisorAuth(data.backend || ""),
      );
      setSupervisorProtocol(data.protocol || "openai");
      setSupervisorBaseUrl(data.base_url || "");
      setSupervisorDispatchLimit(supervisorDispatchLimitDraft(data.dispatch_limit_override));
      setSupervisorApiKey("");
      supervisorKeyAudience.current = null;
      setSupervisorCredentialAction("keep");
      markCanonical("supervisor", "fresh");
    } else {
      markCanonical("supervisor", "failed", "Supervisor settings and their revision could not be refreshed.");
    }
    if (channelsResult.status === "fulfilled") {
      setChannels(channelsResult.value);
      markCanonical("channels", "fresh");
    } else {
      markCanonical("channels", "failed", "Channel settings could not be refreshed.");
    }
  }, [markCanonical]);

  useEffect(() => {
    if (!bridgeAvailable || !pageVisible || shell === "pet") return;
    void loadSettings();
    return () => {
      settingsRequestSequence.current += 1;
    };
  }, [bridgeAvailable, loadSettings, pageVisible, shell]);

  useEffect(() => {
    const loadingRevision = supervisor?.revision;
    if (!bridgeAvailable || !pageVisible || shell === "pet" || !settingsAvailable || savingSupervisor
      || supervisor?.activation_status !== "loading" || !isSupervisorRevision(loadingRevision)) return;
    let cancelled = false;
    const stopPolling = startSerialPolling(async (signal) => {
      if (supervisorSaveInFlight.current) return;
      const requestSequence = settingsRequestSequence.current;
      try {
        const data = await bridgeJson<SupervisorInfo>("/v1/supervisor", { signal });
        if (cancelled) return;
        const disposition = supervisorActivationRefreshDisposition(
          loadingRevision, data?.revision, requestSequence,
          settingsRequestSequence.current, supervisorSaveInFlight.current,
        );
        if (disposition === "ignore") return;
        if (disposition === "reload") {
          markCanonical("supervisor", "failed", "Supervisor configuration changed. Reload settings before saving.");
          stopPolling();
          return;
        }
        // Update observed activation only; preserve every unsaved form input.
        setSupervisor(data);
        if (data.activation_status !== "loading") stopPolling();
      } catch {
        if (cancelled || supervisorSaveInFlight.current
          || requestSequence !== settingsRequestSequence.current) return;
        markCanonical("supervisor", "failed", "Supervisor activation status could not be refreshed. Reload settings.");
        stopPolling();
      }
    }, 4000);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [bridgeAvailable, markCanonical, pageVisible, savingSupervisor, settingsAvailable, shell,
    supervisor?.activation_status, supervisor?.revision]);

  const sessions = useMemo(() => {
    const merged = new Map<string, SessionRow>();
    for (const session of deck.sessions || []) merged.set(session.id, session);
    for (const session of pet?.sessions || []) {
      merged.set(session.id, mergeSessionObservation(merged.get(session.id), session));
    }
    return Array.from(merged.values());
  }, [deck.sessions, pet?.sessions]);
  const availableGoals = useMemo(() => currentGoals(goals), [goals]);
  const current = selectPrimarySession(sessions, selectedId);
  const attachedGoal = availableGoals.find((goal) => goal.id === current?.goal_id);
  const projectId = current?.project_id || attachedGoal?.project_id || current?.cwd || "";
  const identitySelectedProjectId = identityTargetProjectId ?? projectId;
  const identityLoading = identityConflictLoading || identityStatusLoading;
  const identityError = [identityConflictError, identityStatusError]
    .filter((message): message is string => Boolean(message))
    .join(" ") || null;

  useEffect(() => {
    detailRequestSequence.current += 1;
    setContextItems([]);
    setContextProjectId(null);
    markCanonical("context", "reset");
  }, [markCanonical, projectId]);

  useEffect(() => {
    identitySelectionRevision.current += 1;
    identitySelectedProjectIdRef.current = projectId;
    identityStatusRequestSequence.current += 1;
    setIdentityTargetProjectId(null);
    setIdentityStatus(null);
    setIdentityStatusLoading(false);
    setIdentityStatusError(null);
    setIdentityFeedback(null);
  }, [projectId]);

  useEffect(() => {
    if (!bridgeAvailable) {
      goalEvidenceKey.current = null;
      loadedGoalLedgerKey.current = null;
      goalEvidenceRefresh.current = null;
      markCanonical("decisions", "reset");
      markCanonical("completion", "reset");
      return;
    }
    if (!pageVisible) return;
    if (!attachedGoal?.id) {
      goalEvidenceKey.current = null;
      loadedGoalLedgerKey.current = null;
      goalEvidenceRefresh.current = null;
      setLedgerDecisions([]);
      setGoalCompletion(null);
      markCanonical("decisions", "fresh");
      markCanonical("completion", "fresh");
      return;
    }
    const evidenceKey = goalLedgerKey(attachedGoal);
    if (goalEvidenceKey.current !== evidenceKey) {
      goalEvidenceKey.current = evidenceKey;
      loadedGoalLedgerKey.current = null;
      setLedgerDecisions([]);
      setGoalCompletion(null);
      markCanonical("decisions", "reset");
      markCanonical("completion", "reset");
    }
    let cancelled = false;
    const controller = new AbortController();
    const goalId = encodeURIComponent(attachedGoal.id);
    const refreshGoalEvidence = coalesceBackgroundRead(async () => {
      const signal = controller.signal;
      const [decisionsResult, completionResult] = await Promise.allSettled([
        bridgeJson<unknown>(`/v1/goals/${goalId}/decisions`, { signal })
          .then((value) => readGoalDecisions(value, attachedGoal.id)),
        bridgeJson<GoalCompletion>(`/v1/goals/${goalId}/completion`, { signal }),
      ]);
      if (cancelled) return;
      if (decisionsResult.status === "fulfilled") {
        loadedGoalLedgerKey.current = evidenceKey;
        setLedgerDecisions(decisionsResult.value);
      }
      markCanonical(
        "decisions",
        decisionsResult.status === "fulfilled" ? "fresh" : "failed",
        "Goal decisions could not be refreshed.",
      );
      if (completionResult.status === "fulfilled") setGoalCompletion(completionResult.value);
      markCanonical(
        "completion",
        completionResult.status === "fulfilled" ? "fresh" : "failed",
        "Goal completion could not be refreshed.",
      );
    });
    goalEvidenceRefresh.current = refreshGoalEvidence;
    const stopPolling = startSerialPolling(
      refreshGoalEvidence,
      GOAL_EVIDENCE_RECONCILIATION_INTERVAL_MS,
    );
    return () => {
      cancelled = true;
      if (goalEvidenceRefresh.current === refreshGoalEvidence) goalEvidenceRefresh.current = null;
      controller.abort();
      stopPolling();
    };
  }, [attachedGoal?.id, attachedGoal?.intent_revision, bridgeAvailable, markCanonical, pageVisible]);

  const loadDetails = useCallback(async (includeDeck = false, showLoading = false, signal?: AbortSignal) => {
    const requestSequence = ++detailRequestSequence.current;
    if (showLoading) {
      setDetailsLoading(true);
      markCanonical("context", "loading");
      markCanonical("interventions", "loading");
      if (includeDeck) markCanonical("deck", "loading");
    }
    const contextPath = projectId ? `/v1/context?project_id=${encodeURIComponent(projectId)}` : "/v1/context";
    const interventionRequest = bridgeJson<Intervention[]>(
      "/v1/interventions?include_handoff_bundle=true",
      { signal },
    );
    const [deckResult, contextResult, interventionResult, attentionResult, benchResult, discoverResult] = await Promise.allSettled([
      includeDeck ? bridgeJson<DeckData>("/v1/deck", { signal }) : Promise.resolve<DeckData | null>(null),
      bridgeJson<ContextItem[]>(contextPath, { signal }),
      interventionRequest,
      bridgeJson<AttentionMetrics>("/v1/attention/metrics", { signal }),
      includeDeck
        ? bridgeJson<{ runs?: BenchRun[]; message?: string }>("/v1/bench/runs", { signal })
        : Promise.resolve<{ runs?: BenchRun[]; message?: string } | null>(null),
      includeDeck
        ? bridgeJson<{ found?: Array<{ name?: string; kind?: string }>; not_running?: string[] }>("/v1/discover", { signal })
        : Promise.resolve<{ found?: Array<{ name?: string; kind?: string }>; not_running?: string[] } | null>(null),
    ]);
    if (requestSequence !== detailRequestSequence.current) return;
    if (includeDeck) {
      if (deckResult.status === "fulfilled" && deckResult.value) {
        setDeck(deckResult.value);
        markCanonical("deck", "fresh");
      } else {
        markCanonical("deck", "failed", "Command deck state could not be refreshed.");
      }
    }
    if (contextResult.status === "fulfilled" && Array.isArray(contextResult.value)) {
      setContextItems(contextResult.value);
      setContextProjectId(projectId);
      markCanonical("context", "fresh");
    } else {
      markCanonical("context", "failed", "Context could not be refreshed.");
    }
    if (interventionResult.status === "fulfilled" && Array.isArray(interventionResult.value)) {
      const currentInterventions = interventionResult.value;
      setInterventions(currentInterventions);
      handoffInterventions.current = currentInterventions;
      const nextHandoffKey = handoffInterventionFingerprint(currentInterventions);
      if (nextHandoffKey !== handoffInterventionKey.current) {
        handoffInterventionKey.current = nextHandoffKey;
        setHandoffAssimilation({});
        void handoffAssimilationRefresh.current?.();
      }
      markCanonical("interventions", "fresh");
    } else {
      handoffInterventions.current = [];
      handoffInterventionKey.current = "";
      setHandoffAssimilation({});
      markCanonical("interventions", "failed", "Intervention history could not be refreshed.");
    }
    setAttentionMetrics(attentionResult.status === "fulfilled" ? attentionResult.value : null);
    const coreFailed = [contextResult, interventionResult, attentionResult].some((item) => item.status === "rejected") ||
      (includeDeck && deckResult.status === "rejected");
    setDetailsError(coreFailed ? "Some live bridge data is unavailable." : null);

    const inventory =
      discoverResult.status === "fulfilled" && discoverResult.value
        ? starterInventoryFromDiscover(discoverResult.value)
        : undefined;
    if (includeDeck && benchResult.status === "rejected") {
      setBench((state) => ({
        loading: false,
        runs: [],
        message: "Benchmark result endpoint could not be reached.",
        inventory: inventory ?? state.inventory,
      }));
    } else if (benchResult.status === "fulfilled" && benchResult.value) {
      const currentBench = benchResult.value;
      setBench((state) => ({
        loading: false,
        runs: currentBench.runs || [],
        message: currentBench.message,
        inventory: inventory ?? state.inventory,
      }));
    }
    // A mutation-triggered refresh can supersede the first visible read. The
    // newest accepted response owns the loading state even when it did not set it.
    setDetailsLoading(false);
  }, [markCanonical, projectId]);

  const loadProjectIdentityConflicts = useCallback(async (options: {
    signal?: AbortSignal;
    conflictOffset?: number;
    appendConflicts?: boolean;
    showLoading?: boolean;
  } = {}): Promise<ProjectIdentityConflictPage | null> => {
    const requestSequence = ++identityConflictRequestSequence.current;
    if (options.showLoading) setIdentityConflictLoading(true);
    try {
      const nextPage = await bridgeJson<ProjectIdentityConflictPage>(
        `/v1/project-identities/conflicts?limit=200&offset=${options.conflictOffset ?? 0}`,
        { signal: options.signal },
      );
      if (requestSequence !== identityConflictRequestSequence.current) return null;
      setIdentityConflicts((currentPage) => {
        if (!options.appendConflicts || !currentPage) return nextPage;
        const merged = new Map(
          currentPage.items.map((item) => [item.legacy_project_id, item]),
        );
        for (const item of nextPage.items) merged.set(item.legacy_project_id, item);
        return {
          ...nextPage,
          offset: 0,
          items: Array.from(merged.values()),
        };
      });
      setIdentityConflictError(null);
      return nextPage;
    } catch (error) {
      if (requestSequence !== identityConflictRequestSequence.current) return null;
      setIdentityConflictError(operationError(
        error,
        "Live project identity conflicts are unavailable.",
      ));
      return null;
    } finally {
      if (requestSequence === identityConflictRequestSequence.current) {
        setIdentityConflictLoading(false);
      }
    }
  }, []);

  const loadProjectIdentityStatus = useCallback(async (options: {
    signal?: AbortSignal;
    targetProjectId?: string;
    candidateOffset?: number;
    appendCandidates?: boolean;
    showLoading?: boolean;
  } = {}): Promise<ProjectIdentityStatusView | null> => {
    const requestSequence = ++identityStatusRequestSequence.current;
    const exactProjectId = options.targetProjectId ?? identitySelectedProjectId;
    if (!exactProjectId) {
      setIdentityStatus(null);
      setIdentityStatusError(null);
      setIdentityStatusLoading(false);
      return null;
    }
    if (options.showLoading) setIdentityStatusLoading(true);
    try {
      const liveStatus = await bridgeJson<ProjectIdentityStatusView>(
        "/v1/project-identities/status" +
          `?legacy_project_id=${encodeURIComponent(exactProjectId)}` +
          `&candidate_limit=200&candidate_offset=${options.candidateOffset ?? 0}`,
        { signal: options.signal },
      );
      if (requestSequence !== identityStatusRequestSequence.current) return null;
      setIdentityStatus((currentStatus) => {
        if (
          !options.appendCandidates ||
          currentStatus?.status !== "quarantined" ||
          liveStatus?.status !== "quarantined" ||
          currentStatus.legacy_project_id !== liveStatus.legacy_project_id
        ) return liveStatus;
        const merged = new Map(
          currentStatus.candidates.map((candidate) => [candidate.identity.id, candidate]),
        );
        for (const candidate of liveStatus.candidates) {
          merged.set(candidate.identity.id, candidate);
        }
        return {
          ...liveStatus,
          candidate_offset: 0,
          candidates: Array.from(merged.values()),
        };
      });
      setIdentityStatusError(null);
      return liveStatus;
    } catch (error) {
      if (requestSequence !== identityStatusRequestSequence.current) return null;
      setIdentityStatusError(operationError(
        error,
        "Live project identity status is unavailable.",
      ));
      return null;
    } finally {
      if (requestSequence === identityStatusRequestSequence.current) {
        setIdentityStatusLoading(false);
      }
    }
  }, [identitySelectedProjectId]);

  useEffect(() => {
    if (!bridgeAvailable || !pageVisible || surface === "compact" || shell !== "main") return;
    setBench((state) => ({ ...state, loading: state.runs.length === 0 && !state.message }));
    let firstRefresh = true;
    let slowDetailsRequested = false;
    const controller = new AbortController();
    const refreshDetails = coalesceBackgroundRead(async () => {
      while (!controller.signal.aborted) {
        const includeSlowDetails = slowDetailsRequested;
        slowDetailsRequested = false;
        const showLoading = firstRefresh;
        firstRefresh = false;
        await loadDetails(includeSlowDetails, showLoading, controller.signal);
        if (!slowDetailsRequested) return;
      }
    });
    const refreshSlowDetails = () => {
      slowDetailsRequested = true;
      return refreshDetails();
    };
    detailRefresh.current = refreshDetails;
    const stopPolling = startSerialPolling(
      refreshSlowDetails,
      DETAIL_RECONCILIATION_INTERVAL_MS,
    );
    return () => {
      detailRequestSequence.current += 1;
      if (detailRefresh.current === refreshDetails) detailRefresh.current = null;
      controller.abort();
      stopPolling();
    };
  }, [bridgeAvailable, loadDetails, pageVisible, shell, surface]);

  useEffect(() => {
    if (!bridgeAvailable || !pageVisible || surface === "compact" || shell !== "main") return;
    let cancelled = false;
    const controller = new AbortController();
    // A view that was hidden may have missed events. Do not present its prior
    // target-use projection while the immediate reconciliation is in flight.
    setHandoffAssimilation({});
    const refreshHandoffAssimilation = coalesceBackgroundRead(async () => {
      while (!cancelled) {
        const requestedKey = handoffInterventionKey.current;
        const requestedInterventions = handoffInterventions.current;
        if (!requestedKey) {
          setHandoffAssimilation({});
          return;
        }
        const statuses = await loadHandoffAssimilationStatuses(
          requestedInterventions,
          controller.signal,
        );
        if (cancelled) return;
        if (handoffInterventionKey.current !== requestedKey) continue;
        setHandoffAssimilation(statuses);
        return;
      }
    });
    handoffAssimilationRefresh.current = refreshHandoffAssimilation;
    const stopPolling = startSerialPolling(
      refreshHandoffAssimilation,
      HANDOFF_ASSIMILATION_RECONCILIATION_INTERVAL_MS,
    );
    return () => {
      cancelled = true;
      if (handoffAssimilationRefresh.current === refreshHandoffAssimilation) {
        handoffAssimilationRefresh.current = null;
      }
      controller.abort();
      stopPolling();
    };
  }, [bridgeAvailable, pageVisible, shell, surface]);

  useEffect(() => {
    if (!bridgeAvailable || !pageVisible || surface === "compact" || shell !== "main") return;
    let firstRefresh = true;
    const controller = new AbortController();
    const refreshConflicts = coalesceBackgroundRead(() => {
      const showLoading = firstRefresh;
      firstRefresh = false;
      return loadProjectIdentityConflicts({ showLoading, signal: controller.signal });
    });
    identityConflictRefresh.current = refreshConflicts;
    const stopPolling = startSerialPolling(
      refreshConflicts,
      PROJECT_IDENTITY_RECONCILIATION_INTERVAL_MS,
    );
    return () => {
      identityConflictRequestSequence.current += 1;
      setIdentityConflictLoading(false);
      if (identityConflictRefresh.current === refreshConflicts) {
        identityConflictRefresh.current = null;
      }
      controller.abort();
      stopPolling();
    };
  }, [bridgeAvailable, loadProjectIdentityConflicts, pageVisible, shell, surface]);

  useEffect(() => {
    if (!bridgeAvailable || !pageVisible || surface !== "deck" || shell !== "main" || activeView !== "decisions") return;
    let firstRefresh = true;
    const controller = new AbortController();
    const refreshStatus = coalesceBackgroundRead(() => {
      const showLoading = firstRefresh;
      firstRefresh = false;
      return loadProjectIdentityStatus({ showLoading, signal: controller.signal });
    });
    identityStatusRefresh.current = refreshStatus;
    const stopPolling = startSerialPolling(
      refreshStatus,
      PROJECT_IDENTITY_RECONCILIATION_INTERVAL_MS,
    );
    return () => {
      identityStatusRequestSequence.current += 1;
      setIdentityStatusLoading(false);
      if (identityStatusRefresh.current === refreshStatus) {
        identityStatusRefresh.current = null;
      }
      controller.abort();
      stopPolling();
    };
  }, [activeView, bridgeAvailable, loadProjectIdentityStatus, pageVisible, shell, surface]);

  const petState = canonicalResources.pet;
  const sessionStateFresh = !bridgeError
    && canonicalResourcesAreFresh(canonicalResources, ["pet"]);
  const goalStateFresh = canonicalResourcesAreFresh(canonicalResources, ["goals"]);
  const goalMutationAvailable = goalStateFresh && (!current || sessionStateFresh);
  const goalLedgerEditable = goalMutationAvailable && canEditGoalLedger(
    attachedGoal, loadedGoalLedgerKey.current,
    canonicalResourcesAreFresh(canonicalResources, ["decisions"]),
  );
  const goalEvidenceFresh = !attachedGoal || canonicalResourcesAreFresh(
    canonicalResources,
    ["decisions", "completion"],
  );
  const contextStateFresh = canonicalResourceIsFreshForScope(
    canonicalResources,
    "context",
    contextProjectId,
    projectId,
  );
  const inspectorCanonicalStateAvailable = sessionStateFresh
    && goalStateFresh
    && goalEvidenceFresh
    && contextStateFresh;
  const inspectorIssue = contextProjectId !== projectId
    ? "Checking canonical context for the selected project…"
    : canonicalResourceIssue(
        canonicalResources,
        attachedGoal
          ? ["pet", "goals", "context", "decisions", "completion"]
          : ["pet", "goals", "context"],
      );
  const deckMutationsAvailable = canonicalResourcesAreFresh(
    canonicalResources,
    ["deck", "goals"],
  );
  const auditMutationsAvailable = canonicalResourcesAreFresh(
    canonicalResources,
    ["interventions", "goals"],
  );
  const settingsIssue = canonicalResourceIssue(
    canonicalResources,
    ["supervisor", "channels", "pets"],
  );
  const compactGoalIssue = canonicalResourceIssue(canonicalResources, ["goals"]);
  const deckIssue = bridgeError
    ? "Bridge offline. Cached rows below are not current."
    : contextProjectId !== projectId
      ? "Checking canonical context for the selected project…"
      : canonicalResourceIssue(canonicalResources, ["deck", "context", "interventions"])
        || detailsError;
  const status = useMemo(
    () => statusCopy(pet, bridgeError, petState.status),
    [bridgeError, pet, petState.status],
  );
  const setup = firstRunGuidance({
    current,
    attachedGoal,
    sessionFresh: sessionStateFresh,
    goalFresh: goalStateFresh,
  });
  const semanticSupervisor = supervisorAvailability({ supervisor, supervisorFresh: settingsAvailable });
  const homeStatus = statusWithFirstRunGuidance(status, setup, Boolean(pet?.paused));
  const mood = moodForState(pet, bridgeError);
  const bridgeSheet = useBridgeAsset(
    pet?.appearance?.atlas_ready === true ? pet.appearance.spritesheet_url : undefined,
  );
  const sheet = bridgeSheet || bundledPexSheet;
  const petName = pet?.settings?.custom_name?.trim() || pet?.appearance?.display_name || "Pex";
  const reducedMotion = useReducedMotion();
  const displayedInterventions = useMemo(
    () => (interventions.length ? interventions : deck.interventions || [])
      .map((item) => projectCompletedOverlayUndo(item, completedOverlayUndoIds)),
    [completedOverlayUndoIds, deck.interventions, interventions],
  );
  const displayedLastAction = useMemo(() => {
    const item = pet?.last_action;
    if (
      !item
      || item.action !== "APPLY_OVERLAY"
      || !completedOverlayUndoIds.has(item.id)
    ) return item;
    return { ...item, result: "overlay_reverted" };
  }, [completedOverlayUndoIds, pet?.last_action]);
  const action = useMemo(
    () => actionForSession(current, displayedInterventions, displayedLastAction),
    [current, displayedInterventions, displayedLastAction],
  );

  async function openSession(session?: SessionRow) {
    const row = session || current;
    if (!row) return;
    if (canFocusSession(row)) {
      try {
        const focused = await bridgeJson<{ ok?: boolean }>(
          `/v1/sessions/${encodeURIComponent(row.id)}/focus`,
          { method: "POST" },
        );
        setNote(
          focused.ok
            ? `Focused the existing ${titleCase(row.harness_type)} window.`
            : `The existing ${titleCase(row.harness_type)} window could not be focused.`,
        );
      } catch (error) {
        setNote(operationError(error, `The existing ${titleCase(row.harness_type)} window could not be focused.`));
      }
      return;
    }
    const url = sessionExternalUrl(row);
    if (!url || !canOpenSession(row)) {
      setNote(`${titleCase(row.harness_type)} does not expose a truthful window or session link.`);
      return;
    }
    const opened = window.open(url, "_blank", "noopener,noreferrer");
    setNote(
      opened
        ? `Opened the existing ${titleCase(row.harness_type)} session in the browser.`
        : `The existing ${titleCase(row.harness_type)} session link could not be opened.`,
    );
  }

  async function pauseOrResume(session?: SessionRow) {
    const row = session || current;
    if (!row) return;
    const sourceFresh = session
      ? canonicalResourcesAreFresh(canonicalResources, ["deck"])
      : sessionStateFresh;
    if (bridgeError || !sourceFresh) {
      setNote("Current session control state is unavailable. Refresh before changing supervision.");
      return;
    }
    const path = row.supervision_paused ? "resume-supervision" : "pause-supervision";
    try {
      await bridgeJson(`/v1/sessions/${encodeURIComponent(row.id)}/${path}`, { method: "POST" });
      await refreshPet();
    } catch (error) {
      setNote(operationError(error, "Could not update supervision for that session."));
    }
  }

  async function attachGoal(
    sessionId: string,
    goalId: string,
    expectedGoalId: string | null,
    expectedControlRevision: number,
    expectedGoalIntentRevision: number,
  ): Promise<SessionGoalAttachmentResponse> {
    if (!goalId) throw new Error("A goal is required for attachment.");
    const attemptKey = `attach:${sessionId}`;
    const prepared = prepareGoalControlAttempt(
      goalControlAttempts.current.get(attemptKey),
      "attach",
      sessionId,
      sessionGoalAttachmentPayload(
        goalId,
        expectedGoalId,
        expectedControlRevision,
        expectedGoalIntentRevision,
      ),
    );
    goalControlAttempts.current.set(attemptKey, prepared.attempt);
    const result = await bridgeJson<SessionGoalAttachmentResponse>(
      `/v1/sessions/${encodeURIComponent(sessionId)}/attach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(prepared.request),
    });
    if (
      goalControlAttempts.current.get(attemptKey)?.idempotencyKey
      === prepared.attempt.idempotencyKey
    ) goalControlAttempts.current.delete(attemptKey);
    return result;
  }

  async function attachSelectedGoal(goalId: string) {
    if (!goalMutationAvailable) {
      setNote("Canonical goal and session state is unavailable. Refresh before attaching.");
      return;
    }
    if (!current || !goalId || attachingGoal || !canAttachPersistentGoal(current)) return;
    const selectedGoal = availableGoals.find((goal) => goal.id === goalId);
    if (
      !selectedGoal
      || !Number.isSafeInteger(selectedGoal.intent_revision)
      || !Number.isSafeInteger(current.control_revision)
    ) {
      setNote("Canonical goal and session revisions are unavailable. Refresh before attaching.");
      return;
    }
    setAttachingGoal(true);
    try {
      const attachment = await attachGoal(
        current.id,
        goalId,
        current.goal_id ?? null,
        current.control_revision!,
        selectedGoal.intent_revision!,
      );
      const success = attachment.session_goal_attachment_receipt.changed
        ? attachment.session_goal_attachment_receipt.reason === "session_goal_replaced"
          ? "Persistent goal replaced by explicit selection."
          : "Persistent goal attached to this worker."
        : "This persistent goal was already attached; no change was needed.";
      setNote(success);
      const refreshed = await refreshPet();
      if (refreshed.status === "failed") {
        setNote(`${success} The live view could not refresh yet.`);
      }
    } catch (error) {
      setNote(operationError(error, "Could not attach that goal."));
    } finally {
      setAttachingGoal(false);
    }
  }

  async function savePersistentGoal(event: FormEvent) {
    event.preventDefault();
    if (!goalMutationAvailable) {
      setNote("Canonical goal state is unavailable. Refresh before saving changes.");
      return;
    }
    if (editingGoalId && (!goalLedgerEditable || attachedGoal?.id !== editingGoalId
      || editingGoalLedgerKey.current !== goalLedgerKey(attachedGoal))) {
      setNote("The ledger is unavailable or changed since editing began. Your draft is kept; reopen the current ledger before saving.");
      return;
    }
    const goalProjectId = current?.project_id || current?.cwd || goalDraft.projectId.trim();
    if (
      !goalDraft.title.trim() ||
      !goalDraft.objective.trim() ||
      savingGoal
    ) return;
    if (!editingGoalId && !goalProjectId) return;
    setSavingGoal(true);
    try {
      if (editingGoalId) {
        const editingGoal = goals.find((goal) => goal.id === editingGoalId);
        if (
          !editingGoal
          || !Number.isSafeInteger(editingGoal.intent_revision)
          || (editingGoal.intent_revision ?? -1) < 0
        ) {
          setNote("This goal has no canonical intent revision. Refresh it before editing.");
          return;
        }
        const attemptKey = `update:${editingGoalId}`;
        const prepared = prepareGoalControlAttempt(
          goalControlAttempts.current.get(attemptKey),
          "update",
          editingGoalId,
          updateGoalPayload(goalDraft, editingGoal.intent_revision!),
        );
        goalControlAttempts.current.set(attemptKey, prepared.attempt);
        const updated = await bridgeJson<GoalMutationResponse>(
          `/v1/goals/${encodeURIComponent(editingGoalId)}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(prepared.request),
          },
        );
        if (
          goalControlAttempts.current.get(attemptKey)?.idempotencyKey
          === prepared.attempt.idempotencyKey
        ) goalControlAttempts.current.delete(attemptKey);
        setGoals((rows) => [updated, ...rows.filter((row) => row.id !== updated.id)]);
        markCanonical("goals", "fresh");
        setEditingGoalId(null);
        setGoalDraft(EMPTY_GOAL);
        const ledgerNote = updated.goal_mutation_receipt.changed
          ? "Persistent ledger updated."
          : "Persistent ledger already matched; no change was needed.";
        setNote(ledgerNote);
        // The scoped goal-evidence effect refreshes this revision. An unscoped
        // post-save read could overwrite a newly selected goal's decision view.
        markCanonical("decisions", "reset");
        return;
      }
      const attemptKey = "create:new-goal";
      const prepared = prepareGoalControlAttempt(
        goalControlAttempts.current.get(attemptKey),
        "create",
        "new-goal",
        createGoalPayload({
          projectId: goalProjectId,
          title: goalDraft.title,
          objective: goalDraft.objective,
          acceptance: goalDraft.acceptance,
          constraints: goalDraft.constraints,
          nonGoals: goalDraft.nonGoals,
          preferences: goalDraft.preferences,
          evidence: goalDraft.evidence,
          decisions: goalDraft.decisions,
          rejectedApproaches: goalDraft.rejectedApproaches,
          unresolvedQuestions: goalDraft.unresolvedQuestions,
        }),
      );
      goalControlAttempts.current.set(attemptKey, prepared.attempt);
      const created = await bridgeJson<GoalMutationResponse>("/v1/goals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(prepared.request),
      });
      if (
        goalControlAttempts.current.get(attemptKey)?.idempotencyKey
        === prepared.attempt.idempotencyKey
      ) goalControlAttempts.current.delete(attemptKey);
      setGoals((rows) => [created, ...rows.filter((row) => row.id !== created.id)]);
      markCanonical("goals", "fresh");
      setGoalDraft(EMPTY_GOAL);
      if (current && canAttachPersistentGoal(current)) {
        setAttachingGoal(true);
        try {
          if (!Number.isSafeInteger(current.control_revision)) {
            throw new Error(
              "Canonical session control revision is unavailable. Refresh before attaching.",
            );
          }
          await attachGoal(
            current.id,
            created.id,
            current.goal_id ?? null,
            current.control_revision!,
            created.intent_revision!,
          );
          const success =
            "Goal saved and attached with boundaries and evidence requirements intact.";
          setNote(success);
          const refreshed = await refreshPet();
          if (refreshed.status === "failed") {
            setNote(`${success} The live view could not refresh yet.`);
          }
        } catch (error) {
          setNote(operationError(error, "Goal was saved, but it could not be attached."));
        } finally {
          setAttachingGoal(false);
        }
      } else {
        setNote("Goal saved with boundaries and evidence requirements intact.");
      }
    } catch (error) {
      setNote(operationError(error, editingGoalId ? "Could not update the persistent ledger." : "Could not save the persistent goal."));
    } finally {
      setSavingGoal(false);
    }
  }

  async function askPex(event?: FormEvent | null, prompt?: string) {
    event?.preventDefault();
    const query = (prompt ?? question).trim();
    if (!query || asking) return;
    setQuestion(query);
    setAsking(true);
    try {
      const data = await bridgeJson<{ answer?: string }>("/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: query }),
      });
      setAnswer(data.answer || "PEX has no answer in canonical state yet.");
    } catch {
      setAnswer("PEX could not reach canonical local state. No worker was interrupted.");
    } finally {
      setAsking(false);
      askInput.current?.focus();
    }
  }

  async function undoIntervention(intervention?: Intervention) {
    const sourceFresh = intervention ? auditMutationsAvailable : sessionStateFresh;
    if (!sourceFresh) {
      setNote("Current intervention state is unavailable. Refresh before undoing an action.");
      return;
    }
    const id = intervention?.id || action?.id;
    const reversible = intervention?.reversible ?? action?.reversible;
    const actionType = intervention?.action_taken || action?.action;
    const result = intervention?.result || action?.result;
    if (!id || undoRequestsInFlight.current.has(id)) return;
    const attempt = prepareUndoAttempt(
      undoAttempts.current.get(id) || null,
      {
        interventionId: id,
        action: actionType,
        reversible,
        result,
      },
      newUndoIdempotencyKey,
    );
    if (!attempt) {
      undoAttempts.current.delete(id);
      return;
    }
    undoAttempts.current.set(id, attempt);
    undoRequestsInFlight.current.add(id);
    try {
      const response = await bridgeJson<UndoResponse>(
        `/v1/interventions/${encodeURIComponent(id)}/undo`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ idempotency_key: attempt.idempotencyKey }),
        },
      );
      const presentation = undoResponsePresentation(actionType, response);
      setNote(presentation.message);
      await Promise.all([refreshPet(), loadDetails()]);
      if (actionType === "APPLY_OVERLAY" && presentation.completed) {
        setCompletedOverlayUndoIds((currentIds) => {
          if (currentIds.has(id)) return currentIds;
          const nextIds = new Set(currentIds);
          nextIds.add(id);
          return nextIds;
        });
        undoAttempts.current.delete(id);
      }
    } catch (error) {
      const status = error instanceof BridgeRequestError ? error.status : null;
      setNote(
        actionType === "APPLY_OVERLAY"
          ? undoFailureMessage(actionType, status)
          : operationError(error, "That intervention could not be undone."),
      );
      if (status === 409 || status === 502) {
        await Promise.allSettled([refreshPet(), loadDetails()]);
      }
    } finally {
      undoRequestsInFlight.current.delete(id);
    }
  }

  async function resolveHumanDecision(
    intervention: Intervention,
    decision: HumanDecisionChoice,
  ) {
    if (!deckMutationsAvailable) {
      setDecisionFeedback({
        state: "error",
        interventionId: intervention.id,
        decision,
        message: "Current decision authority is unavailable. Refresh before responding.",
      });
      return;
    }
    if (
      !isPendingHumanDecision(intervention) ||
      decisionFeedback?.state === "submitting"
    ) return;
    const requestedDecision = isPendingRequestedHumanDecision(intervention);
    const lifecycleDecision = isPendingLifecycleDecision(intervention);
    if (!requestedDecision && decision !== "allow" && decision !== "deny") return;
    const requestedOptions = intervention.proposed_action?.payload?.options;
    const feedbackDecision = humanDecisionFeedbackChoice(
      requestedDecision ? requestedOptions : undefined,
      decision,
    );
    const permissionDecision = decision as PermissionDecision;
    const verb = requestedDecision
      ? "Delivering"
      : lifecycleDecision
      ? decision === "allow" ? "Approving" : "Declining"
      : decision === "allow" ? "Allowing" : "Denying";
    setDecisionFeedback({
      interventionId: intervention.id,
      state: "submitting",
      decision: feedbackDecision,
      message: requestedDecision
        ? `${verb} this exact answer to the requesting worker…`
        : `${verb} this exact ${lifecycleDecision ? "lifecycle action" : "permission request"}…`,
    });
    try {
      const resolved = await bridgeJson<{
        kind?: "permission" | "lifecycle" | "human_decision";
        delivered?: boolean;
        executed?: boolean;
        replayed?: boolean;
        resolution?: { status?: string };
      }>(
        `/v1/decisions/${encodeURIComponent(intervention.id)}/resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        },
      );
      const requested = resolved.kind === "human_decision";
      const lifecycle = resolved.kind === "lifecycle";
      const lifecycleStatus = resolved.resolution?.status;
      const confirmed = requested
        ? resolved.delivered === true && lifecycleStatus === "delivered"
        : lifecycle
        ? lifecycleStatus === "delivered" || lifecycleStatus === "denied"
        : resolved.delivered === true;
      if (!confirmed) throw new Error("The bridge did not confirm this exact human decision.");
      const requestedPresentation = requested
        ? humanDecisionPresentation("delivered", resolved.replayed)
        : null;
      const message = requestedPresentation?.message ?? (resolved.replayed
        ? `This ${permissionDecision} decision was already recorded; PEX did not apply it twice.`
        : lifecycle
        ? decision === "allow"
          ? "Lifecycle action approved and its result was recorded."
          : "Lifecycle action declined; no action was executed."
        : `Permission ${decision === "allow" ? "allowed" : "denied"} and delivery confirmed.`);
      setDecisionFeedback({
        interventionId: intervention.id,
        state: "success",
        decision: feedbackDecision,
        message,
        deliveryStatus: requestedPresentation?.deliveryStatus,
      });
      setNote(message);
      await Promise.all([refreshPet(), loadDetails()]);
    } catch (error) {
      const requestedPresentation = requestedDecision
        ? humanDecisionFailurePresentation(error)
        : null;
      const message = requestedPresentation?.message ?? (error instanceof Error
        ? error.message
        : "The bridge could not resolve this permission request.");
      setDecisionFeedback({
        interventionId: intervention.id,
        state: "error",
        decision: feedbackDecision,
        message,
        deliveryStatus: requestedPresentation?.deliveryStatus,
      });
      setNote(message);
      await Promise.allSettled([refreshPet(), loadDetails()]);
    }
  }

  function selectIdentityProject(legacyProjectId: string) {
    if (identityResolving) return;
    identitySelectionRevision.current += 1;
    identitySelectedProjectIdRef.current = legacyProjectId;
    identityStatusRequestSequence.current += 1;
    setIdentityTargetProjectId(legacyProjectId);
    setIdentityStatus(null);
    setIdentityStatusLoading(false);
    setIdentityStatusError(null);
    setIdentityFeedback(null);
  }

  function loadMoreIdentityConflicts() {
    const offset = identityConflicts?.next_offset;
    if (offset == null || identityConflictLoading) return;
    void loadProjectIdentityConflicts({
      conflictOffset: offset,
      appendConflicts: true,
      showLoading: true,
    });
  }

  function loadMoreIdentityCandidates() {
    const offset = identityStatus?.status === "quarantined"
      ? identityStatus.next_candidate_offset
      : null;
    if (offset == null || identityStatusLoading) return;
    void loadProjectIdentityStatus({
      targetProjectId: identityStatus?.legacy_project_id,
      candidateOffset: offset,
      appendCandidates: true,
      showLoading: true,
    });
  }

  async function resolveProjectIdentity(attempt: ProjectIdentityResolutionAttempt) {
    if (
      identityResolving ||
      attempt.legacyProjectId !== identitySelectedProjectIdRef.current
    ) return;
    const requestSequence = ++identityResolutionRequestSequence.current;
    const selectionRevision = identitySelectionRevision.current;
    const completionIsCurrent = () => (
      requestSequence === identityResolutionRequestSequence.current
      && projectIdentityCompletionIsCurrent(
        attempt.legacyProjectId,
        identitySelectedProjectIdRef.current,
        selectionRevision,
        identitySelectionRevision.current,
      )
    );
    setIdentityResolving(true);
    setIdentityFeedback({
      state: "submitting",
      message: "Recording this exact project identity resolution…",
    });
    try {
      const response = await bridgeJson<ProjectIdentityResolutionResponse>(
        "/v1/project-identities/resolve",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: attempt.idempotencyKey,
            legacy_project_id: attempt.legacyProjectId,
            selected_identity_id: attempt.selectedIdentityId,
            rationale: attempt.rationale,
          }),
        },
      );
      if (!completionIsCurrent()) return;
      const [liveStatus] = await Promise.all([
        loadProjectIdentityStatus({
          targetProjectId: attempt.legacyProjectId,
          showLoading: true,
        }),
        loadProjectIdentityConflicts(),
      ]);
      if (!completionIsCurrent()) return;
      setIdentityFeedback({
        state: "success",
        message: projectIdentityResolutionMessage(response, liveStatus),
      });
    } catch (error) {
      if (!completionIsCurrent()) return;
      await Promise.all([
        loadProjectIdentityStatus({
          targetProjectId: attempt.legacyProjectId,
          showLoading: true,
        }),
        loadProjectIdentityConflicts(),
      ]);
      if (!completionIsCurrent()) return;
      setIdentityFeedback({
        state: "error",
        message: operationError(
          error,
          "The exact project identity resolution was not confirmed.",
        ),
      });
    } finally {
      if (requestSequence === identityResolutionRequestSequence.current) {
        setIdentityResolving(false);
      }
    }
  }

  async function selectPet(id: string) {
    if (selectingPet) return;
    setSelectingPet(true);
    try {
      try {
        await bridgeJson("/v1/pets/settings", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ selected_id: id }),
        });
      } catch (error) {
        setNote(operationError(error, "Could not select that pet."));
        return;
      }

      let success = "Pet selected.";
      const refreshed = await refreshPet();
      if (refreshed.status === "failed") success += " The live view could not refresh yet.";
      try {
        if (petVisible) await releasePetOverlay();
      } catch {
        success += " Its overlay could not reopen yet.";
      }
      setNote(success);
    } finally {
      setSelectingPet(false);
    }
  }

  async function changePetVisibility(visible: boolean) {
    setPetVisible(visible);
    try {
      if (visible) await showPetOverlay();
      else await hidePetOverlay();
      setNote(petVisibilityNote(petOverlayVisible()));
    } catch (error) {
      setNote(operationError(error, visible ? "Could not show the desktop pet." : "Could not hide the desktop pet."));
    }
  }

  async function saveAppearance() {
    try {
      await bridgeJson("/v1/pets/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ custom_name: nickname, scale, click_through: clickThrough }),
      });
      await refreshPet();
      setNote("Appearance saved.");
    } catch (error) {
      setNote(operationError(error, "Could not save appearance."));
    }
  }

  async function provisionHookCredential() {
    if (provisioningHook || !hookProject.trim()) return;
    setProvisioningHook(true);
    setHookBootstrap(null);
    try {
      const receipt = await bridgeJson<HookBootstrapReceipt>(
        "/v1/hook-credentials/bootstrap",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            harness_type: hookHarness,
            project_id: hookProject.trim(),
          }),
        },
      );
      setHookBootstrap(receipt);
      setNote(
        `Scoped ${titleCase(hookHarness)} hook credential ready. Copy it now; PEX does not store the bearer.`,
      );
    } catch (error) {
      setNote(operationError(error, "Could not provision a scoped hook credential."));
    } finally {
      setProvisioningHook(false);
    }
  }

  async function copyHookCredential() {
    if (!hookBootstrap) return;
    try {
      await navigator.clipboard.writeText(hookBootstrap.token);
      setNote(`Copied ${HOOK_ENVIRONMENT[hookBootstrap.harness_type]}.`);
    } catch {
      setNote("Clipboard access was unavailable. Select and copy the one-time credential manually.");
    }
  }

  async function saveSupervisor() {
    if (supervisorSaveInFlight.current) return;
    if (!settingsAvailable) {
      setNote("Supervisor settings are unavailable. Reload them before saving.");
      return;
    }
    supervisorSaveInFlight.current = true;
    const requestSequence = ++settingsRequestSequence.current;
    const draftRevision = supervisorDraftRevision.current;
    setSavingSupervisor(true);
    try {
      const payload = supervisorSavePayload({
        provider: supervisorProvider,
        modelId: supervisorModel,
        authMode: supervisorAuth,
        protocol: supervisorProtocol,
        baseUrl: supervisorBaseUrl,
        apiKey: supervisorApiKey,
        credentialAction: supervisorCredentialAction,
        dispatchLimit: supervisorDispatchLimit,
      }, supervisor?.revision, supervisorKeyAudience.current);
      const data = await supervisorRequest((signal) => bridgeJson<SupervisorInfo>("/v1/supervisor", {
        method: "PATCH",
        signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }));
      if (!isSupervisorRevision(data.revision) || data.revision !== Number(payload.expected_revision) + 1) {
        throw new Error("The save response did not confirm the next configuration revision. Reload settings.");
      }
      if (!supervisorSaveResponseIsCurrent(
        draftRevision, supervisorDraftRevision.current,
        requestSequence, settingsRequestSequence.current,
      )) {
        markCanonical("supervisor", "failed", "A save completed after the settings view changed. Reload before editing.");
        setNote("Supervisor choice saved. Reload settings to see the committed configuration.");
        return;
      }
      setSupervisor(data);
      markCanonical("supervisor", "fresh");
      setSupervisorProvider(data.backend || "");
      setSupervisorModel(data.model_id || "");
      setSupervisorAuth((data.auth_mode as SupervisorAuthMode | null) || defaultSupervisorAuth(data.backend || ""));
      setSupervisorProtocol(data.protocol || "openai");
      setSupervisorBaseUrl(data.base_url || "");
      setSupervisorDispatchLimit(supervisorDispatchLimitDraft(data.dispatch_limit_override));
      setSupervisorApiKey("");
      supervisorKeyAudience.current = null;
      setSupervisorCredentialAction("keep");
      setNote(supervisorSaveConfirmation(data.model_loaded));
    } catch (error) {
      markCanonical("supervisor", "failed", "The save was not confirmed. Reload the current configuration before another save.");
      setNote(operationError(error, "Could not save supervisor configuration."));
    } finally {
      supervisorSaveInFlight.current = false;
      setSavingSupervisor(false);
    }
  }

  function changeSupervisorDraft<T>(current: T, next: T, setter: (value: T) => void, audience = false) {
    if (supervisorSaveInFlight.current || current === next) return;
    supervisorDraftRevision.current += 1;
    settingsRequestSequence.current += 1;
    if (audience) {
      supervisorKeyAudience.current = null;
      setSupervisorApiKey("");
      setSupervisorCredentialAction("keep");
      setNote("Credential destination changed. Any pasted key was cleared; select credentials for this destination.");
    }
    setter(next);
  }

  async function refreshSupervisorCatalog() {
    if (refreshingCatalog || supervisorSaveInFlight.current || !settingsAvailable) return;
    const requestSequence = settingsRequestSequence.current;
    setRefreshingCatalog(true);
    try {
      const data = await supervisorRequest((signal) => bridgeJson<{
        provider: string;
        catalog: NonNullable<SupervisorInfo["catalog"]>;
        count: number;
        inference_calls: number;
      }>("/v1/supervisor/catalog/refresh", {
        method: "POST",
        signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: supervisorProvider.trim() || undefined }),
      }));
      if (requestSequence !== settingsRequestSequence.current) return;
      setSupervisor((current) => current ? { ...current, catalog: data.catalog } : current);
      setNote(`Listed ${data.count} models from ${data.provider}; no inference call was made.`);
    } catch (error) {
      if (requestSequence !== settingsRequestSequence.current) return;
      setNote(operationError(error, "Could not refresh this provider's model list."));
    } finally {
      setRefreshingCatalog(false);
    }
  }

  function openInspector(sessionId?: string) {
    if (sessionId) setSelectedId(sessionId);
    setSurface("inspector");
    window.location.hash = "inspector";
  }

  function showSurface(next: Surface) {
    setSurface(next);
    window.location.hash = next;
  }

  function openSettings(section?: SettingsSection) {
    setSettingsDestination(section);
    window.location.hash = "settings";
  }

  function openGoalSetup() {
    openInspector();
    setGoalFocusRequest((request) => request + 1);
  }

  if (shell === "pet") {
    return (
      <main className={`pet-desktop tone-${status.tone}`}>
        <PetStage
          overlay
          active={petVisible}
          name={petName}
          sheet={sheet}
          mood={mood}
          scale={scale}
          reducedMotion={reducedMotion}
          status={homeStatus}
          statusIdentity={pet?.last_action?.id}
          onActivate={() => void expandMainSurface()}
          onDismiss={() => void changePetVisibility(false)}
        />
      </main>
    );
  }

  if (!bridgeAvailable) {
    return (
      <StartupRecovery
        status={bridgeControlAvailable
          ? bridgeStartup
          : unavailableBridgeBootstrapStatus(bridgeStartup.attempt)}
        retrying={bridgeRetrying}
        onRetry={() => void retryBridgeBootstrap()}
      />
    );
  }

  if (shell === "settings") {
    return (
      <SettingsPage
        initialSection={settingsDestination}
        goals={availableGoals}
        note={note}
        nickname={nickname}
        scale={scale}
        clickThrough={clickThrough}
        petVisible={petVisible}
        supervisor={supervisor}
        supervisorProvider={supervisorProvider}
        supervisorModel={supervisorModel}
        supervisorAuth={supervisorAuth}
        supervisorProtocol={supervisorProtocol}
        supervisorBaseUrl={supervisorBaseUrl}
        supervisorDispatchLimit={supervisorDispatchLimit}
        supervisorApiKey={supervisorApiKey}
        supervisorCredentialAction={supervisorCredentialAction}
        cursorRejections={cursorRejections}
        channels={channels}
        settingsAvailable={settingsAvailable}
        settingsIssue={settingsIssue}
        savingSupervisor={savingSupervisor}
        refreshingCatalog={refreshingCatalog}
        hookHarness={hookHarness}
        hookProject={hookProject}
        hookEnvironment={HOOK_ENVIRONMENT[hookHarness]}
        hookCredential={hookBootstrap?.token || ""}
        hookCredentialExpiresAt={hookBootstrap?.expires_at || ""}
        provisioningHook={provisioningHook}
        workerConnection={<><OpenCodeConnectionPanel request={sharedConnectionRequest} /><SharedConnectionPanel request={sharedConnectionRequest} /></>}
        onBack={() => { window.location.hash = surface; }}
        onNickname={setNickname}
        onScale={setScale}
        onClickThrough={setClickThrough}
        onPetVisible={(visible) => void changePetVisibility(visible)}
        onSaveAppearance={() => void saveAppearance()}
        onSupervisorProvider={(value) => changeSupervisorDraft(supervisorProvider, value, (next) => {
          setSupervisorProvider(next);
          setSupervisorAuth(defaultSupervisorAuth(next));
          setSupervisorProtocol("openai");
          setSupervisorBaseUrl("");
          setSupervisorCredentialAction(next ? "keep" : "environment");
        }, true)}
        onSupervisorModel={(value) => changeSupervisorDraft(supervisorModel, value, setSupervisorModel)}
        onSupervisorAuth={(value) => changeSupervisorDraft(supervisorAuth, value, setSupervisorAuth, true)}
        onSupervisorProtocol={(value) => changeSupervisorDraft(supervisorProtocol, value, setSupervisorProtocol, true)}
        onSupervisorBaseUrl={(value) => changeSupervisorDraft(supervisorBaseUrl, value, setSupervisorBaseUrl, true)}
        onSupervisorDispatchLimit={(value) => changeSupervisorDraft(supervisorDispatchLimit ?? "", value, setSupervisorDispatchLimit)}
        onSupervisorApiKey={(value) => changeSupervisorDraft(supervisorApiKey, value, (next) => {
          supervisorKeyAudience.current = next ? supervisorCredentialAudience({
            provider: supervisorProvider,
            authMode: supervisorAuth,
            protocol: supervisorProtocol,
            baseUrl: supervisorBaseUrl,
          }) : null;
          setSupervisorApiKey(next);
        })}
        onSupervisorCredentialAction={(value) => changeSupervisorDraft(supervisorCredentialAction, value, setSupervisorCredentialAction)}
        onSaveSupervisor={() => void saveSupervisor()}
        onReloadSettings={() => void loadSettings()}
        onRefreshCatalog={() => void refreshSupervisorCatalog()}
        onHookHarness={(value) => {
          setHookHarness(value);
          setHookBootstrap(null);
        }}
        onHookProject={(value) => {
          setHookProject(value);
          setHookBootstrap(null);
        }}
        onProvisionHook={() => void provisionHookCredential()}
        onCopyHook={() => void copyHookCredential()}
        onClearHook={() => setHookBootstrap(null)}
        companionRoster={(
          <section className="pet-roster" aria-label="PEX pet roster">
            <header>
              <div>
                <p className="eyebrow">
                  Built-in companions · {builtInRoster.filter((item) => item.atlas_ready === true).length}/2 available
                </p>
                <h2>Your companion</h2>
              </div>
              <p>Pex the watchful owl or Von the focused cat. Same supervision, your choice.</p>
            </header>
            {petFleetIssues.length ? (
              <p className="pet-roster-unavailable" role="alert">
                Built-in fleet mismatch: {petFleetIssues.join(" ")}
              </p>
            ) : null}
            <PetRosterButtons
              pets={builtInRoster}
              selectedId={pet?.appearance?.id}
              selecting={selectingPet}
              reducedMotion={reducedMotion}
              onSelect={(id) => void selectPet(id)}
            />
          </section>
        )}
      />
    );
  }

  const supervisorNotice = (
    <div className="supervisor-notice" role="status">
      <span>{semanticSupervisor.copy}</span>
      <button type="button" className="ghost" onClick={() => openSettings("supervisor")}>
        Supervisor settings
      </button>
    </div>
  );

  return (
    <main className={`main-shell tone-${status.tone}`}>
      <header className="topbar">
        <span className="wordmark">PEX</span>
        <span className="topbar-state" role="status" aria-live="polite">
          <span className="status-dot" aria-hidden="true" />{surface === "compact" ? homeStatus.label : status.label}
        </span>
        <nav className="surface-switch" aria-label="Progressive PEX surfaces">
          {(["compact", "inspector", "deck"] as Surface[]).map((item) => (
            <button
              type="button"
              className={surface === item ? "active" : ""}
              aria-current={surface === item ? "page" : undefined}
              onClick={() => showSurface(item)}
              key={item}
            >
              {item === "compact" ? "Home" : titleCase(item)}
            </button>
          ))}
        </nav>
        <button type="button" className="ghost topbar-settings" onClick={() => openSettings()}>Settings</button>
      </header>

      {surface === "compact" ? (
        <section
          className="compact-surface surface-focus-target"
          data-surface-root="compact"
          aria-label="PEX compact companion"
          tabIndex={-1}
        >
          <aside className="worker-rail" aria-label="Your workers">
            <p className="eyebrow">Your workers</p>
            {sessions.slice(0, 8).map((session) => (
              <button key={session.id} type="button" className="worker-choice"
                aria-pressed={current?.id === session.id}
                onClick={() => setSelectedId(session.id)}>
                <strong>{titleCase(session.harness_type)}</strong>
                <small>{session.label || session.cwd?.split(/[\\/]/).filter(Boolean).pop() || "Existing session"}</small>
                <small>{titleCase(session.status)}</small>
              </button>
            ))}
            <button type="button" className="ghost" onClick={() => openSettings("connections")}>Connect a worker</button>
          </aside>
          <div className="compact-companion">
            <div className="workspace-heading">
              <p className="eyebrow">{current ? `${titleCase(current.harness_type)} workspace` : "Your workspace"}</p>
              <h1>{attachedGoal?.title || "What are we working toward?"}</h1>
              <p>{current?.cwd || "Connect OpenCode or Codex, then give PEX a goal to supervise."}</p>
            </div>
            <PetStage
              name={petName}
              sheet={sheet}
              mood={mood}
              scale={0.78}
              reducedMotion={reducedMotion}
              status={setup ? undefined : homeStatus}
              statusIdentity={pet?.last_action?.id}
              onActivate={() => openInspector()}
            />
            <div
              className="compact-metrics"
              aria-label={sessionStateFresh ? "Live PEX counts" : "PEX counts unavailable"}
            >
              <span><strong>{sessionStateFresh ? pet?.working || 0 : "—"}</strong> working</span>
              <span><strong>{sessionStateFresh ? pet?.needs_you || 0 : "—"}</strong> need you</span>
              <span><strong>{sessionStateFresh ? pet?.drifting || 0 : "—"}</strong> drifting</span>
            </div>
          {attachedGoal ? (
            <p className="compact-goal">
              <span>{goalStateFresh ? "Persistent goal" : "Cached persistent goal"}</span>
              <strong>{attachedGoal.title}</strong>
            </p>
          ) : null}
            {setup ? (
              <div className="compact-setup">
                <p className="eyebrow">Your next step</p>
                <h1>{setup.title}</h1>
                <p>{setup.detail}</p>
                <div className="button-row">
                  {setup.cta ? (
                    <button type="button" className="solid" onClick={() => {
                      if (setup.cta?.intent === "goal") openGoalSetup();
                      else openSettings("connections");
                    }}>{setup.cta.label}</button>
                  ) : null}
                  <button type="button" className="ghost" onClick={() => openInspector()}>Inspect current state</button>
                </div>
              </div>
            ) : (
              <button type="button" className="solid compact-open" onClick={() => openInspector()}>
                Inspect what PEX knows
              </button>
            )}
            {setup?.state !== "unavailable" ? supervisorNotice : null}
          </div>
          {compactGoalIssue && setup?.state !== "unavailable" ? (
            <p className="canonical-state-warning compact-state-warning" role="status" aria-live="polite">
              {compactGoalIssue} Goal controls stay unavailable until refresh succeeds.
            </p>
          ) : null}
          {!sessions.length && sessionStateFresh ? (
            <p className="empty-copy compact-empty">
              Already-open Cursor, Codex, OpenCode, Hermes, and Claude Code sessions are
              listed in place. A closed harness stays unavailable until its app or API is
              actually running.
            </p>
          ) : null}
        </section>
      ) : null}

      {surface === "inspector" ? (
        <Inspector
          current={current}
          sessions={sessions}
          goal={attachedGoal}
          ledgerDecisions={ledgerDecisions}
          completion={goalCompletion}
          goals={availableGoals}
          action={action}
          status={status}
          supervisorNotice={supervisorNotice}
          evidenceOpen={evidenceOpen}
          question={question}
          answer={answer}
          asking={asking}
          askInput={askInput}
          goalDraft={goalDraft}
          savingGoal={savingGoal}
          attachingGoal={attachingGoal}
          editingGoal={Boolean(editingGoalId)}
          note={note}
          canonicalStateAvailable={inspectorCanonicalStateAvailable}
          canonicalStateIssue={inspectorIssue}
          sessionActionsAvailable={sessionStateFresh}
          goalActionsAvailable={goalMutationAvailable}
          onEvidence={() => setEvidenceOpen((open) => !open)}
          onOpen={() => void openSession()}
          onPause={() => void pauseOrResume()}
          onUndo={() => void undoIntervention()}
          onAttachGoal={(goalId) => void attachSelectedGoal(goalId)}
          onGoalChange={(field, value) => setGoalDraft((draft) => ({ ...draft, [field]: value }))}
          onCreateGoal={(event) => void savePersistentGoal(event)}
          onEditGoal={
            attachedGoal
              ? () => {
                  if (!goalLedgerEditable) {
                    setNote("The decision ledger is still loading or unavailable. Refresh before editing.");
                    return;
                  }
                  editingGoalLedgerKey.current = goalLedgerKey(attachedGoal);
                  setEditingGoalId(attachedGoal.id);
                  setGoalDraft(
                    goalToDraft(
                      attachedGoal,
                      current?.project_id || current?.cwd || "",
                      ledgerDecisions,
                    ),
                  );
                }
              : undefined
          }
          onCancelEdit={() => {
            setEditingGoalId(null);
            setGoalDraft(EMPTY_GOAL);
          }}
          onQuestion={setQuestion}
          onAsk={(event) => void askPex(event)}
          onAskPrompt={(prompt) => void askPex(null, prompt)}
          onOpenDeck={() => showSurface("deck")}
          onSelectSession={(sessionId) => setSelectedId(sessionId)}
        />
      ) : null}

      {surface === "deck" ? (
        <CommandDeck
          activeView={activeView}
          sessions={sessions}
          goals={goals}
          interventions={(deck.interventions || [])
            .map((item) => projectCompletedOverlayUndo(item, completedOverlayUndoIds))}
          pendingInterventions={
            attentionMetrics?.current_pending.items || deck.interventions || []
          }
          pendingInterventionsTruncated={attentionMetrics?.current_pending.items_truncated === true}
          auditInterventions={displayedInterventions}
          handoffAssimilation={handoffAssimilation}
          attentionMetrics={attentionMetrics}
          contextItems={contextProjectId === projectId ? contextItems : []}
          fingerprints={deck.fingerprints || []}
          adapters={deck.adapters || []}
          bench={bench}
          selectedSessionId={current?.id}
          loading={detailsLoading}
          error={deckIssue}
          mutationsAvailable={deckMutationsAvailable}
          auditMutationsAvailable={auditMutationsAvailable}
          decisionFeedback={decisionFeedback}
          identityConflicts={identityConflicts}
          identityConflictsLoading={identityConflictLoading}
          identityConflictsError={identityConflictError}
          identitySelectedProjectId={identitySelectedProjectId}
          identityStatus={identityStatus}
          identityLoading={identityLoading}
          identityError={identityError}
          identityResolving={identityResolving}
          identityFeedback={identityFeedback}
          question={question}
          answer={answer}
          asking={asking}
          onView={setActiveView}
          onSelectSession={(sessionId) => openInspector(sessionId)}
          onOpenSession={(session) => void openSession(session)}
          onPauseSession={(session) => void pauseOrResume(session)}
          onUndo={(item) => void undoIntervention(item)}
          onResolveDecision={(item, decision) => void resolveHumanDecision(item, decision)}
          onSelectIdentityProject={selectIdentityProject}
          onResolveIdentity={(attempt) => void resolveProjectIdentity(attempt)}
          onLoadMoreIdentityConflicts={loadMoreIdentityConflicts}
          onLoadMoreIdentityCandidates={loadMoreIdentityCandidates}
          onQuestion={setQuestion}
          onAsk={(event) => void askPex(event)}
          onAskPrompt={(prompt) => void askPex(null, prompt)}
        />
      ) : null}
    </main>
  );
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reduced;
}

function useBridgeAsset(path?: string): string {
  const [source, setSource] = useState("");

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setSource("");
    if (!path) return;
    const controller = new AbortController();
    void boundedRead(async (signal) => {
        const response = await bridgeFetch(path, { signal });
        if (!response.ok) throw new Error(`Asset request failed (${response.status}).`);
        return response.blob();
      }, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (cancelled) URL.revokeObjectURL(objectUrl);
        else setSource(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setSource("");
      });
    return () => {
      cancelled = true;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  return source;
}

function BridgePetSprite({
  path,
  mood,
  scale,
  reducedMotion,
  active,
}: {
  path: string;
  mood: PetSnapshot["mood"];
  scale: number;
  reducedMotion: boolean;
  active: boolean;
}) {
  const source = useBridgeAsset(path);
  return source && mood ? (
    <CodexSprite
      active={active}
      src={source}
      mood={mood}
      scale={scale}
      reducedMotion={reducedMotion}
    />
  ) : (
    <span className="pet-fallback" aria-hidden="true">P</span>
  );
}

function PetRosterButtons({
  pets,
  selectedId,
  selecting,
  reducedMotion,
  onSelect,
}: {
  pets: CatalogPet[];
  selectedId?: string;
  selecting: boolean;
  reducedMotion: boolean;
  onSelect: (id: string) => void;
}) {
  if (!pets.length) {
    return <p className="pet-roster-unavailable">No validated pet atlas is available from the bridge.</p>;
  }
  return (
    <div className="pet-roster-row">
      {pets.map((item) => {
        const ready = item.atlas_ready === true;
        const selected = item.id === selectedId;
        return (
          <button
            type="button"
            className={selected ? "active" : ""}
            aria-pressed={selected}
            aria-label={`${item.display_name}, ${item.species || "companion"}${ready ? "" : ", art unavailable"}`}
            disabled={selecting || !ready}
            onClick={() => onSelect(item.id)}
            key={item.id}
          >
            <span className="pet-thumb">
              {ready ? (
                <BridgePetSprite
                  active={selected}
                  path={`/v1/pets/${encodeURIComponent(item.id)}/spritesheet`}
                  mood="idle"
                  scale={0.72}
                  reducedMotion={reducedMotion}
                />
              ) : (
                <span className="pet-fallback" aria-hidden="true">P</span>
              )}
            </span>
            <strong>{item.display_name}</strong>
            <small>{ready ? selected ? "Selected" : item.species || "companion" : "art unavailable"}</small>
          </button>
        );
      })}
    </div>
  );
}

function shellFromHash(): Shell {
  if (window.location.pathname.replaceAll("\\", "/").endsWith("/pet.html")) return "pet";
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash === "pet" || hash === "settings") return hash;
  return "main";
}

function surfaceFromHash(): Surface {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash === "inspector" || hash === "deck") return hash;
  return "compact";
}

function actionForSession(
  session: SessionRow | undefined,
  interventions: Intervention[],
  fallback?: LastAction | null,
): LastAction | null | undefined {
  const item = interventions.find((row) => row.session_id === session?.id);
  if (!item) return fallback?.session_id === session?.id ? fallback : null;
  const metadata = item.metadata || {};
  const verification = metadata.verification;
  const verification_status =
    verification && typeof verification === "object" && verification !== null && "status" in verification
      ? String((verification as { status?: unknown }).status || "") || undefined
      : fallback?.verification_status;
  const evidence_tools = Array.isArray(metadata.evidence_tools)
    ? metadata.evidence_tools.filter((row): row is string => typeof row === "string").slice(0, 12)
    : fallback?.evidence_tools;
  return {
    id: item.id,
    session_id: item.session_id,
    action: item.action_taken,
    diagnosis: item.diagnosis,
    rationale: item.proposed_action?.rationale,
    inference_status: typeof metadata.inference_status === "string" ? metadata.inference_status : undefined,
    evidence: item.evidence,
    result: item.action_taken === "CLEANUP" ? item.result : item.outcome || item.result,
    reversible: item.reversible,
    confidence: item.confidence,
    verification_status,
    evidence_tools,
  };
}

import assert from "node:assert/strict";
import test from "node:test";

import { animationFrameIndex } from "./pets/atlasMath.ts";
import {
  BridgeRequestError,
  bridgeRequestError,
  decisionDeliveryStatus,
  FREEFORM_DECISION_LABEL,
  humanDecisionFailurePresentation,
  humanDecisionFeedbackChoice,
  humanDecisionPresentation,
  prepareFreeformDecision,
} from "./decisionContract.ts";

import {
  BUILT_IN_PET_IDS,
  HATCH_BASE_CANDIDATE_CONFIRMATION,
  HATCH_BASE_CANDIDATE_DISCLOSURE,
  HATCH_EXTERNAL_IMPORT_DISCLOSURE,
  canAttachPersistentGoal,
  canFocusSession,
  canOpenSession,
  safeExternalUrl,
  createGoalPayload,
  goalToDraft,
  hatchIntentRequiresFreshAcknowledgement,
  hatchResponseMatchesCurrentAttempt,
  updateGoalPayload,
  currentGoals,
  canonicalEventCursor,
  encodeWebSocketTokenProtocol,
  eventPageResumeCursor,
  partitionLedgerDecisions,
  isStale,
  isPendingHumanDecision,
  isPendingLifecycleDecision,
  isPendingPermissionDecision,
  isPendingRequestedHumanDecision,
  isSafelyUndoable,
  meaningfulEvidence,
  newGoalControlIdempotencyKey,
  moodForState,
  permissionRequestDetails,
  prepareGoalControlAttempt,
  prepareHatchBaseCandidateAttempt,
  prepareUndoAttempt,
  prepareProjectIdentityResolutionAttempt,
  projectCompletedOverlayUndo,
  projectIdentityCompletionIsCurrent,
  projectIdentityPresentation,
  projectIdentityResolutionMessage,
  requestedHumanDecisionDetails,
  fingerprintCompletionReliability,
  fingerprintFailureModes,
  fingerprintPrematureRate,
  fingerprintStrengths,
  fingerprintSuggestedConfig,
  fingerprintTokenBehavior,
  contextHealthCopy,
  channelStatusCopy,
  reconnectDelay,
  selectPrimarySession,
  sessionGoalAttachmentPayload,
  splitPetCatalog,
  ASK_PEX_QUESTIONS,
  askPexQuestions,
  companionHeadline,
  canonicalResourceIssue,
  canonicalResourceIsFreshForScope,
  canonicalResourcesAreFresh,
  contextItemMarks,
  initialCanonicalResources,
  supervisorHonestyCopy,
  statusCopy,
  settleCanonicalResource,
  starterHarnessInventoryCopy,
  starterInventoryFromDiscover,
  STARTER_HARNESS_IDS,
  supportsCapability,
  undoFailureMessage,
  undoResponsePresentation,
} from "./viewModel.ts";

import type {
  Intervention,
  ProjectIdentityResolutionResponse,
  ProjectIdentityStatusView,
} from "./types.ts";

test("goal replacement binds exact goal and control authority", () => {
  assert.deepEqual(sessionGoalAttachmentPayload("goal-next", "goal-current", 4, 7), {
    goal_id: "goal-next",
    replace_existing: true,
    expected_goal_id: "goal-current",
    expected_control_revision: 4,
    expected_goal_intent_revision: 7,
  });
  assert.deepEqual(sessionGoalAttachmentPayload("goal-current", "goal-current", 4, 7), {
    goal_id: "goal-current",
    replace_existing: false,
    expected_goal_id: null,
    expected_control_revision: 4,
    expected_goal_intent_revision: 7,
  });
  assert.deepEqual(sessionGoalAttachmentPayload("goal-first", null, 0, 1), {
    goal_id: "goal-first",
    replace_existing: false,
    expected_goal_id: null,
    expected_control_revision: 0,
    expected_goal_intent_revision: 1,
  });
  assert.throws(() => sessionGoalAttachmentPayload("goal-first", null, -1, 1));
  assert.throws(() => sessionGoalAttachmentPayload("goal-first", null, 0, -1));
  assert.deepEqual(
    sessionGoalAttachmentPayload("goal-next", "goal-current", 4, 7, "goal-attach-fixed-0001"),
    {
      idempotency_key: "goal-attach-fixed-0001",
      goal_id: "goal-next",
      replace_existing: true,
      expected_goal_id: "goal-current",
      expected_control_revision: 4,
      expected_goal_intent_revision: 7,
    },
  );
  assert.match(newGoalControlIdempotencyKey("attach"), /^goal-attach-[0-9a-f-]{36}$/);
});

test("goal control retries retain identity only for the same logical request", () => {
  let issued = 0;
  const nextKey = () => `goal-update-attempt-${++issued}`;
  const request = updateGoalPayload({
    title: "Durable goal",
    objective: "Replay the exact request",
    acceptance: "one operation",
    constraints: "no duplicate mutation",
    nonGoals: "fresh key on retry",
    evidence: "stable receipt",
  }, 3);
  const first = prepareGoalControlAttempt(
    undefined,
    "update",
    "goal-durable",
    request,
    nextKey,
  );
  const exactRetry = prepareGoalControlAttempt(
    first.attempt,
    "update",
    "goal-durable",
    request,
    nextKey,
  );
  const changedRequest = prepareGoalControlAttempt(
    first.attempt,
    "update",
    "goal-durable",
    { ...request, objective: "A genuinely different request" },
    nextKey,
  );
  const changedScope = prepareGoalControlAttempt(
    first.attempt,
    "update",
    "goal-other",
    request,
    nextKey,
  );

  assert.equal(exactRetry.attempt.idempotencyKey, first.attempt.idempotencyKey);
  assert.equal(exactRetry.request.idempotency_key, first.request.idempotency_key);
  assert.notEqual(changedRequest.attempt.idempotencyKey, first.attempt.idempotencyKey);
  assert.notEqual(changedScope.attempt.idempotencyKey, first.attempt.idempotencyKey);
  assert.equal(issued, 3);
});

test("goal payload keeps constraints and non-goals separate", () => {
  const payload = createGoalPayload({
    projectId: "pex",
    title: " Ship ",
    objective: " Win honestly ",
    acceptance: "build passes\n demo works",
    constraints: "no fake benchmark\nno secrets",
    nonGoals: "rewrite every adapter\nsubmit automatically",
    evidence: "full suite exits 0\nlive recovery trace exists",
    idempotencyKey: "goal-create-fixed-0001",
  });

  assert.equal(payload.idempotency_key, "goal-create-fixed-0001");
  assert.deepEqual(payload.constraints, ["no fake benchmark", "no secrets"]);
  assert.deepEqual(payload.non_goals, ["rewrite every adapter", "submit automatically"]);
  assert.deepEqual(payload.evidence_requirements, ["full suite exits 0", "live recovery trace exists"]);
  assert.deepEqual(payload.preferences, []);
  assert.deepEqual(payload.decisions, []);
  assert.deepEqual(payload.rejected_approaches, []);
  assert.deepEqual(payload.unresolved_questions, []);
  assert.notDeepEqual(payload.constraints, payload.non_goals);
});

test("the built-in fleet is exactly eight and custom imports remain separate", () => {
  assert.deepEqual(BUILT_IN_PET_IDS, [
    "pex",
    "ledger",
    "mesh",
    "nudge",
    "drift",
    "quiet",
    "ember",
    "von",
  ]);
  const starters = BUILT_IN_PET_IDS.map((id) => ({
    id,
    display_name: id,
    description: "",
    source: "starter" as const,
    atlas_ready: false,
  }));
  const catalog = [
    ...starters.map((pet) => ({ ...pet, atlas_ready: true })),
    {
      id: "import:nori",
      display_name: "Nori",
      description: "Custom",
      source: "imported" as const,
      atlas_ready: true,
    },
  ];

  const partitioned = splitPetCatalog(starters, catalog);
  assert.deepEqual(partitioned.builtIns.map((pet) => pet.id), BUILT_IN_PET_IDS);
  assert.equal(partitioned.builtIns.every((pet) => pet.atlas_ready), true);
  assert.deepEqual(partitioned.custom.map((pet) => pet.id), ["import:nori"]);
  assert.deepEqual(partitioned.fleetIssues, []);
});

test("base-candidate hatch retries preserve one bounded idempotency key", () => {
  let issued = 0;
  const nextKey = () => `hatch-base-request-${String(++issued).padStart(4, "0")}`;
  const input = {
    displayName: " Nori ",
    description: " Ink-navy fox ",
    stylePreset: " plush ",
    petNotes: " Cream belly ",
  };

  const first = prepareHatchBaseCandidateAttempt(null, input, nextKey);
  assert.ok(first);
  assert.deepEqual(first.request, {
    display_name: "Nori",
    description: "Ink-navy fox",
    style_preset: "plush",
    pet_notes: "Cream belly",
    idempotency_key: "hatch-base-request-0001",
    confirm_one_base_candidate_call: true,
  });

  const exactRetry = prepareHatchBaseCandidateAttempt(first.attempt, input, nextKey);
  assert.ok(exactRetry);
  assert.equal(exactRetry.attempt.idempotencyKey, first.attempt.idempotencyKey);
  assert.equal(issued, 1);

  const changed = prepareHatchBaseCandidateAttempt(
    exactRetry.attempt,
    { ...input, petNotes: "Cream belly and blue scarf" },
    nextKey,
  );
  assert.ok(changed);
  assert.equal(changed.attempt.idempotencyKey, "hatch-base-request-0002");
  assert.equal(issued, 2);
});

test("material hatch intent changes require a fresh acknowledgement", async () => {
  assert.equal(hatchIntentRequiresFreshAcknowledgement("Nori", "Nori"), false);
  assert.equal(hatchIntentRequiresFreshAcknowledgement("Nori", "Nori II"), true);
  assert.equal(hatchIntentRequiresFreshAcknowledgement("plush", "clay"), true);
  assert.equal(
    hatchIntentRequiresFreshAcknowledgement("ink navy", "ink navy, cream belly"),
    true,
  );

  const { readFile } = await import("node:fs/promises");
  const appSource = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(
    appSource,
    /onHatchName=\{\(value\) => changeHatchIntent\(hatchName, value, setHatchName\)\}/u,
  );
  assert.match(
    appSource,
    /onHatchNotes=\{\(value\) => changeHatchIntent\(hatchNotes, value, setHatchNotes\)\}/u,
  );
  assert.match(
    appSource,
    /onHatchStyle=\{\(value\) => changeHatchIntent\(hatchStyle, value, setHatchStyle\)\}/u,
  );
  assert.match(appSource, /setHatchOneCallConfirmed\(false\);/u);
  assert.match(appSource, /hatchAttempt\.current = null;/u);
});

test("an old hatch response cannot clear a newer draft attempt", async () => {
  const submitted = {
    idempotencyKey: "hatch-base-request-0001",
    requestSignature: '["Nori","navy","plush","navy"]',
  };
  assert.equal(hatchResponseMatchesCurrentAttempt(submitted, submitted), true);
  assert.equal(hatchResponseMatchesCurrentAttempt(submitted, null), false);
  assert.equal(
    hatchResponseMatchesCurrentAttempt(submitted, {
      ...submitted,
      idempotencyKey: "hatch-base-request-0002",
    }),
    false,
  );
  assert.equal(
    hatchResponseMatchesCurrentAttempt(submitted, {
      ...submitted,
      requestSignature: '["Mori","cream","clay","cream"]',
    }),
    false,
  );

  const { readFile } = await import("node:fs/promises");
  const appSource = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(
    appSource,
    /if \(hatchResponseMatchesCurrentAttempt\(submittedAttempt, hatchAttempt\.current\)\)/u,
  );
});

test("base-candidate hatch request and import copy stay honest", () => {
  assert.match(HATCH_BASE_CANDIDATE_DISCLOSURE, /exactly one potentially billable/u);
  assert.match(HATCH_BASE_CANDIDATE_DISCLOSURE, /unverified base candidate/u);
  assert.match(HATCH_BASE_CANDIDATE_DISCLOSURE, /not an atlas or playable pet/u);
  assert.doesNotMatch(HATCH_BASE_CANDIDATE_DISCLOSURE, /13/u);
  assert.match(HATCH_BASE_CANDIDATE_CONFIRMATION, /exactly one potentially billable/u);
  assert.match(HATCH_EXTERNAL_IMPORT_DISCLOSURE, /externally assembled Codex v2 pet/u);
  assert.match(HATCH_EXTERNAL_IMPORT_DISCLOSURE, /independent QA/u);

  assert.equal(
    prepareHatchBaseCandidateAttempt(
      null,
      {
        displayName: "Nori\u0000",
        description: "fox",
        stylePreset: "plush",
        petNotes: "",
      },
      () => "hatch-base-request-0001",
    ),
    null,
  );
  assert.equal(
    prepareHatchBaseCandidateAttempt(
      null,
      {
        displayName: "Nori",
        description: "fox",
        stylePreset: "plush",
        petNotes: "",
      },
      () => "short",
    ),
    null,
  );
});

test("pet catalog reports backend fleet drift instead of classifying it as custom", () => {
  const catalog = [
    ...BUILT_IN_PET_IDS.map((id) => ({
      id,
      display_name: id,
      description: "",
      source: "starter" as const,
      atlas_ready: true,
    })),
    {
      id: "ninth",
      display_name: "Ninth",
      description: "",
      source: "starter" as const,
      atlas_ready: true,
    },
  ];

  const partitioned = splitPetCatalog(catalog, catalog);
  assert.deepEqual(partitioned.custom, []);
  assert.deepEqual(partitioned.builtIns.map((pet) => pet.id), BUILT_IN_PET_IDS);
  assert.deepEqual(partitioned.fleetIssues, ["Unexpected built-in pet ninth."]);
});

test("animation frames are clamped synchronously when a shorter row becomes active", () => {
  assert.equal(animationFrameIndex(7, 4), 3);
  assert.equal(animationFrameIndex(8, 4), 0);
  assert.equal(animationFrameIndex(-1, 4), 3);
  assert.equal(animationFrameIndex(Number.NaN, 4), 0);
});

test("superseded goals are not offered for new attachments", () => {
  const active = currentGoals([
    { id: "old", title: "Old", objective: "Old" },
    { id: "new", title: "New", objective: "New", supersedes: "old" },
  ]);
  assert.deepEqual(active.map((goal) => goal.id), ["new"]);
});

test("channel status copy does not invent a connected messenger", () => {
  assert.equal(
    channelStatusCopy({
      label: "Telegram",
      configured: false,
      connected: false,
      notes: "No bot token. Will not fake a connected Telegram bot.",
    }),
    "Telegram is not configured. No bot token. Will not fake a connected Telegram bot.",
  );
  assert.equal(
    channelStatusCopy({
      label: "Local inbox",
      configured: true,
      connected: true,
      notes: "Writes attention notices to ~/.pex/channels/inbox.jsonl.",
    }),
    "Local inbox is delivering attention notices locally. Writes attention notices to ~/.pex/channels/inbox.jsonl.",
  );
});

test("observe-only desktop tiles cannot attach a persistent goal", () => {
  assert.equal(canAttachPersistentGoal({
    id: "codex:desktop",
    harness_type: "codex",
    status: "discovered",
    metadata: { source: "desktop" },
  }), false);
  assert.equal(canAttachPersistentGoal({
    id: "cursor:desktop",
    harness_type: "cursor",
    status: "discovered",
    metadata: { source: "desktop" },
  }), false);
  assert.equal(canAttachPersistentGoal({
    id: "cursor:conv-1",
    harness_type: "cursor",
    status: "working",
    metadata: { source: "hook" },
  }), true);
  assert.equal(canAttachPersistentGoal({
    id: "codex:thread-1",
    harness_type: "codex",
    status: "working",
    metadata: { isolated: true },
  }), true);
});

test("Codex App Server sessions never claim ChatGPT desktop focus", () => {
  assert.equal(canFocusSession({
    id: "codex:thread-1",
    harness_type: "codex",
    status: "working",
    capabilities: { focus_ui: true },
  }), false);
  assert.equal(canFocusSession({
    id: "codex:desktop",
    harness_type: "codex",
    status: "discovered",
    capabilities: { focus_ui: true },
  }), true);
});

test("Open agent uses a local window or an allowlisted existing Devin link", () => {
  assert.equal(safeExternalUrl("javascript:alert(1)"), null);
  assert.equal(safeExternalUrl("https://evil.example/sessions/devin-1"), null);
  assert.equal(safeExternalUrl("https://app.devin.ai/sessions/new"), null);
  assert.equal(
    safeExternalUrl("https://app.devin.ai/sessions/devin-1"),
    "https://app.devin.ai/sessions/devin-1",
  );
  assert.equal(canOpenSession({
    id: "devin:devin-1",
    harness_type: "devin",
    status: "working",
    capabilities: { focus_ui: false },
    external_url: "https://app.devin.ai/sessions/devin-1",
  }), true);
  assert.equal(canFocusSession({
    id: "devin:devin-1",
    harness_type: "devin",
    status: "working",
    capabilities: { focus_ui: false },
    external_url: "https://app.devin.ai/sessions/devin-1",
  }), false);
  assert.equal(canOpenSession({
    id: "devin:devin-1",
    harness_type: "devin",
    status: "working",
    capabilities: { focus_ui: false },
    external_url: "https://evil.example/sessions/devin-1",
  }), false);
});

test("WebSocket reconnect backoff is bounded", () => {
  assert.equal(reconnectDelay(0), 1_000);
  assert.equal(reconnectDelay(3), 8_000);
  assert.equal(reconnectDelay(99), 15_000);
  assert.equal(reconnectDelay(-3), 1_000);
});

test("event resume cursors stay canonical and recover retention gaps exactly", () => {
  assert.equal(canonicalEventCursor("0"), "0");
  assert.equal(canonicalEventCursor("9223372036854775807"), "9223372036854775807");
  assert.equal(canonicalEventCursor("01"), "0");
  assert.equal(canonicalEventCursor(4), "0");
  assert.equal(
    eventPageResumeCursor({ next: "9223372036854775807", gap: { detected: false } }),
    "9223372036854775807",
  );
  assert.equal(
    eventPageResumeCursor({
      next: "99",
      gap: { detected: true, earliest_available: "1000000000000000000" },
    }),
    "999999999999999999",
  );
  assert.equal(eventPageResumeCursor({ next: "01", gap: { detected: false } }), null);
  assert.equal(eventPageResumeCursor({ gap: { detected: true } }), null);
});

test("WebSocket bearer protocol is valid for every printable configured token", () => {
  const token = `${"x".repeat(31)},`;
  const protocol = encodeWebSocketTokenProtocol(token);

  assert.match(protocol, /^pex-token\.[A-Za-z0-9_-]+$/u);
  assert.equal(
    Buffer.from(protocol.slice("pex-token.".length), "base64url").toString("ascii"),
    token,
  );
  assert.throws(() => encodeWebSocketTokenProtocol("short"), /token is invalid/u);
});

test("primary session prioritizes a human decision", () => {
  const selected = selectPrimarySession([
    { id: "working", harness_type: "codex", status: "working" },
    { id: "decision", harness_type: "cursor", status: "needs_decision" },
  ]);

  assert.equal(selected?.id, "decision");
});

test("offline status never presents stale state as current", () => {
  const copy = statusCopy(
    { headline: "1 working", working: 1, drifting: 0, needs_you: 0, sessions: [] },
    "Bridge offline",
  );

  assert.equal(copy.tone, "offline");
  assert.match(copy.detail, /will not invent/i);
});

test("initial companion state is checking until canonical pet state is observed", () => {
  const resources = initialCanonicalResources();
  const copy = statusCopy(null, null, resources.pet.status);

  assert.equal(resources.pet.status, "loading");
  assert.equal(copy.label, "Checking local state");
  assert.match(copy.detail, /has not observed canonical local state/i);
  assert.doesNotMatch(`${copy.label} ${copy.detail}`, /all quiet|nothing needs babysitting/i);
});

test("canonical resource failures stay independent and preserve only same-resource cache", () => {
  assert.equal(statusCopy(null, "Bridge offline").label, "Bridge offline");
  const initial = initialCanonicalResources();
  const petFresh = settleCanonicalResource(initial, "pet", "fresh", {
    observedAt: "2026-09-05T10:00:00.000Z",
  });
  const partialFailure = settleCanonicalResource(
    petFresh,
    "goals",
    "failed",
    { error: "Persistent goals could not be refreshed." },
  );

  assert.equal(partialFailure.pet.status, "fresh");
  assert.equal(partialFailure.pets.status, "loading");
  assert.equal(partialFailure.goals.status, "unavailable");
  assert.equal(canonicalResourcesAreFresh(partialFailure, ["pet"]), true);
  assert.equal(canonicalResourcesAreFresh(partialFailure, ["pet", "goals"]), false);
  assert.match(canonicalResourceIssue(partialFailure, ["goals"]) || "", /unavailable/i);

  const goalsFresh = settleCanonicalResource(partialFailure, "goals", "fresh", {
    observedAt: "2026-09-05T10:01:00.000Z",
  });
  const cached = settleCanonicalResource(goalsFresh, "goals", "failed", {
    error: "Persistent goals could not be refreshed.",
  });
  assert.equal(cached.goals.status, "stale");
  assert.equal(cached.goals.lastSuccessAt, "2026-09-05T10:01:00.000Z");
  assert.match(canonicalResourceIssue(cached, ["goals"]) || "", /cached state/i);
  assert.equal(canonicalResourcesAreFresh(cached, ["goals"]), false);

  const catalogFailure = settleCanonicalResource(cached, "pets", "failed", {
    error: "Pet catalog could not be refreshed.",
  });
  assert.equal(catalogFailure.pets.status, "unavailable");
  assert.equal(catalogFailure.pet.status, "fresh");
  assert.equal(catalogFailure.goals.status, "stale");

  const interventionFailure = settleCanonicalResource(
    catalogFailure,
    "interventions",
    "failed",
    { error: "Intervention history could not be refreshed." },
  );
  assert.equal(interventionFailure.interventions.status, "unavailable");
  assert.equal(canonicalResourcesAreFresh(interventionFailure, ["pet"]), true);

  const contextFresh = settleCanonicalResource(interventionFailure, "context", "fresh", {
    observedAt: "2026-09-05T10:02:00.000Z",
  });
  assert.equal(canonicalResourceIsFreshForScope(contextFresh, "context", "project-a", "project-a"), true);
  assert.equal(canonicalResourceIsFreshForScope(contextFresh, "context", "project-a", "project-b"), false);
});

test("stale goal and settings authority disable revision-dependent controls", async () => {
  const { readFile } = await import("node:fs/promises");
  const app = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const inspector = await readFile(new URL("./components/Inspector.tsx", import.meta.url), "utf8");
  const settings = await readFile(new URL("./components/SettingsPage.tsx", import.meta.url), "utf8");

  assert.match(app, /goalMutationAvailable = goalStateFresh && \(!current \|\| sessionStateFresh\)/u);
  assert.match(app, /if \(!goalMutationAvailable\) \{[\s\S]*?Refresh before attaching/u);
  assert.match(app, /if \(!settingsAvailable\) \{[\s\S]*?Reload them before saving/u);
  assert.match(inspector, /disabled=\{attachingGoal \|\| !canAttach \|\| !goalActionsAvailable\}/u);
  assert.match(inspector, /disabled=\{savingGoal \|\| !goalActionsAvailable\}/u);
  assert.match(settings, /disabled=\{!settingsAvailable \|\| savingSupervisor\}/u);
  assert.match(settings, /Retry settings/u);
});

test("settings fetch failure cannot submit the empty fallback form", async () => {
  const { readFile } = await import("node:fs/promises");
  const app = await readFile(new URL("./App.tsx", import.meta.url), "utf8");

  assert.match(
    app,
    /Promise\.allSettled\(\[\s*bridgeJson<SupervisorInfo>\("\/v1\/supervisor"\),\s*bridgeJson<ChannelHubStatus>\("\/v1\/channels"\)/u,
  );
  assert.match(
    app,
    /supervisorResult\.status === "fulfilled"[\s\S]*?markCanonical\("supervisor", "fresh"\)[\s\S]*?markCanonical\("supervisor", "failed"/u,
  );
  assert.match(app, /settingsAvailable=\{settingsAvailable\}/u);
  assert.match(app, /onReloadSettings=\{\(\) => void loadSettings\(\)\}/u);
});

test("intervention mutations and context stay bound to their actual live source", async () => {
  const { readFile } = await import("node:fs/promises");
  const app = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const deck = await readFile(new URL("./components/CommandDeck.tsx", import.meta.url), "utf8");

  assert.match(
    app,
    /interventionResult\.status === "fulfilled" && Array\.isArray\(interventionResult\.value\)[\s\S]*?markCanonical\("interventions", "fresh"\)[\s\S]*?markCanonical\("interventions", "failed"/u,
  );
  assert.match(
    app,
    /auditMutationsAvailable = canonicalResourcesAreFresh\([\s\S]*?\["interventions", "goals"\]/u,
  );
  assert.match(app, /sourceFresh = intervention \? auditMutationsAvailable : sessionStateFresh/u);
  assert.match(deck, /mutationsAvailable=\{auditMutationsAvailable\}/u);
  assert.match(
    app,
    /useEffect\(\(\) => \{\s*detailRequestSequence\.current \+= 1;\s*setContextItems\(\[\]\);\s*setContextProjectId\(null\);\s*markCanonical\("context", "reset"\);\s*\}, \[markCanonical, projectId\]\)/u,
  );
  assert.match(app, /canonicalResourceIsFreshForScope\([\s\S]*?contextProjectId,[\s\S]*?projectId/u);
  assert.match(app, /contextItems=\{contextProjectId === projectId \? contextItems : \[\]\}/u);
});

test("offline state immediately suppresses stale agent prompts", async () => {
  const { readFile } = await import("node:fs/promises");
  const app = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const inspector = await readFile(new URL("./components/Inspector.tsx", import.meta.url), "utf8");
  const deck = await readFile(new URL("./components/CommandDeck.tsx", import.meta.url), "utf8");

  assert.match(app, /currentSocket\.onclose = \(\) => \{[\s\S]*?void refreshPet\(\)/);
  assert.match(app, /canonicalStateAvailable=\{inspectorCanonicalStateAvailable\}/);
  assert.match(app, /attentionMetrics\?\.current_pending\.items \|\| deck\.interventions \|\| \[\]/);
  assert.match(inspector, /canonicalStateAvailable \? askPexQuestions\(sessions, action\) : \[\]/);
  assert.match(inspector, /Verified complete for the current persistent intent\./);
  assert.match(inspector, /PEX will not infer it from narration\./);
  assert.match(app, /\/v1\/goals\/\$\{goalId\}\/completion/);
  assert.match(deck, /questions=\{error \? \[\] : askPexQuestions\(sessions, interventions\[0\]\)\}/);
  assert.match(deck, /Cached · last observed/);
  assert.match(deck, /sessionObservationCopy\(session, degraded\)/);
});

test("malformed context expiry fails closed as stale", () => {
  assert.equal(isStale("not-a-timestamp"), true);
  assert.equal(isStale(null), false);
});

test("blocked state is never presented as quiet", () => {
  const pet = {
    headline: "1 blocked",
    working: 0,
    drifting: 0,
    blocked: 1,
    needs_you: 0,
    sessions: [],
  };
  const copy = statusCopy(pet, null);

  assert.equal(copy.tone, "watch");
  assert.match(copy.label, /blocked/i);
  assert.equal(moodForState(pet, null), "warning");
  assert.equal(moodForState(pet, "offline"), "degraded");
});

test("companion headline names the harness and does not invent token savings", () => {
  assert.equal(
    companionHeadline({
      headline: "codex needs a decision",
      working: 0,
      drifting: 0,
      needs_you: 1,
      sessions: [],
    }),
    "Codex needs a decision",
  );
  assert.equal(
    companionHeadline({
      headline: "quiet",
      working: 3,
      drifting: 0,
      needs_you: 0,
      sessions: [],
    }),
    "3 working · 0 need you",
  );
  assert.equal(ASK_PEX_QUESTIONS.length, 7);
  assert.match(
    supervisorHonestyCopy({ model_loaded: false, auth_mode: "api_key", login_implemented: false }),
    /not implemented/i,
  );
  assert.doesNotMatch(
    supervisorHonestyCopy({ model_loaded: true, auth_mode: "api_key" }),
    /saved \d+k/i,
  );
});

test("compact companion is the one-line pet, not a worker catalog", async () => {
  const { readFile } = await import("node:fs/promises");
  const { dirname, join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const app = await readFile(
    join(dirname(fileURLToPath(import.meta.url)), "App.tsx"),
    "utf8",
  );
  const compactStart = app.indexOf('aria-label="PEX compact companion"');
  const compactEnd = app.indexOf('surface === "inspector"');
  const compact = app.slice(compactStart, compactEnd);
  assert.match(compact, /Live PEX counts/);
  assert.match(compact, /Inspect what PEX knows/);
  assert.doesNotMatch(compact, /Active agents/);
  assert.doesNotMatch(compact, /AskPex/);
  assert.doesNotMatch(compact, /Choose your PEX pet/);
  const settings = await readFile(
    join(dirname(fileURLToPath(import.meta.url)), "components/SettingsPage.tsx"),
    "utf8",
  );
  assert.match(settings, /supervisorHonestyCopy/);
  assert.match(settings, /API key · write only/);
  assert.match(settings, /Custom base URL/);
  assert.match(settings, /OpenAI-compatible/);
  assert.match(settings, /Anthropic-compatible/);
  assert.match(settings, /OS vault/);
  const ask = await readFile(
    join(dirname(fileURLToPath(import.meta.url)), "components/AskPex.tsx"),
    "utf8",
  );
  assert.match(ask, /questions\.map/);
  assert.match(ask, /Inspects attached workspaces/);
  const inspector = await readFile(
    join(dirname(fileURLToPath(import.meta.url)), "components/Inspector.tsx"),
    "utf8",
  );
  assert.match(inspector, /askPexQuestions/);
});

test("ask chips name attached harnesses and do not invent missing vendors", () => {
  const empty = askPexQuestions([]);
  assert.equal(empty.some((prompt) => /codex|cursor|devin/i.test(prompt)), false);
  assert.match(empty.join("\n"), /what needs me right now/i);
  assert.doesNotMatch(empty.join("\n"), /why did you message/i);
  const idle = askPexQuestions([
    { id: "devin:old", harness_type: "devin", status: "idle" },
  ]);
  assert.doesNotMatch(idle.join("\n"), /Devin/);
  const questions = askPexQuestions(
    [
      { id: "cursor:1", harness_type: "cursor", status: "working" },
      { id: "opencode:1", harness_type: "opencode", status: "idle" },
    ],
    { action: "SEND_NUDGE" },
  );
  assert.match(questions.join("\n"), /what is Cursor doing/i);
  assert.match(questions.join("\n"), /why did you message Cursor/i);
  assert.doesNotMatch(questions.join("\n"), /OpenCode|Opencode|Devin/);
});

test("recent handoff and approval moods animate without hiding higher-priority states", () => {
  const pet = {
    headline: "Context moved → Codex",
    working: 1,
    drifting: 0,
    needs_you: 0,
    blocked: 0,
    sessions: [],
    mood: "handoff" as const,
  };

  assert.equal(moodForState(pet, null), "handoff");
  assert.equal(moodForState({ ...pet, mood: "approved" }, null), "approved");
  assert.equal(moodForState({ ...pet, needs_you: 1 }, null), "decision");
  assert.equal(moodForState({ ...pet, blocked: 1 }, null), "warning");
  assert.equal(moodForState(pet, "offline"), "degraded");
});

test("capability controls and evidence labels fail closed", () => {
  const session = {
    id: "codex:one",
    harness_type: "codex",
    status: "discovered",
    activity: "Ready for a prompt",
    capabilities: { focus_ui: false, send_message: true },
  };

  assert.equal(supportsCapability(session, "focus_ui"), false);
  assert.equal(supportsCapability(session, "send_message"), true);
  assert.equal(meaningfulEvidence(session), "No meaningful evidence observed yet.");
});

test("only an exact unresolved permission response is actionable", () => {
  const pending = {
    id: "int-permission",
    session_id: "codex:one",
    action_taken: "RESPOND_PERMISSION",
    policy_verdict: "ask_human",
    result: "permission_awaiting_human",
    proposed_action: {
      type: "RESPOND_PERMISSION",
      payload: {
        request_id: "req-7",
        command: "python deploy.py",
        file_paths: ["deploy.py"],
      },
    },
  };

  assert.equal(isPendingPermissionDecision(pending), true);
  assert.deepEqual(permissionRequestDetails(pending), {
    requestId: "req-7",
    command: "python deploy.py",
    toolName: null,
    approvalMethod: null,
    filePaths: ["deploy.py"],
  });
  assert.equal(
    isPendingPermissionDecision({
      ...pending,
      id: "int-general",
      action_taken: "ASK_HUMAN",
      proposed_action: { type: "ASK_HUMAN", payload: { request_id: "req-7" } },
    }),
    false,
  );
  assert.equal(isPendingPermissionDecision({ ...pending, result: "permission_allow" }), false);
  assert.equal(
    isPendingPermissionDecision({
      ...pending,
      proposed_action: { ...pending.proposed_action, payload: {} },
    }),
    false,
  );
});

test("only exact pending lifecycle actions are actionable", () => {
  const pending = {
    id: "int-start",
    session_id: "codex:one",
    action_taken: "START_AGENT",
    policy_verdict: "ask_human",
    result: "awaiting_human",
    proposed_action: {
      type: "START_AGENT",
      payload: { project: "C:/work", prompt: "Run the bounded task" },
    },
  };

  assert.equal(isPendingLifecycleDecision(pending), true);
  assert.equal(isPendingHumanDecision(pending), true);
  assert.equal(isPendingLifecycleDecision({ ...pending, result: "agent_started:new" }), false);
  assert.equal(
    isPendingLifecycleDecision({
      ...pending,
      action_taken: "ASK_HUMAN",
      proposed_action: { ...pending.proposed_action, type: "START_AGENT" },
    }),
    false,
  );
});

test("typed worker decision requests expose exact options and are human-resolvable", () => {
  const pending = {
    id: "int-worker-decision",
    session_id: "codex:thread-7",
    action_taken: "ASK_HUMAN",
    policy_verdict: "ask_human",
    result: "awaiting_human",
    metadata: { decision_kind: "mcp_human_request" },
    proposed_action: {
      type: "ASK_HUMAN",
      rationale: "The worker needs a consequential product choice.",
      payload: {
        question: "Which release strategy should I use?",
        context: "Blue-green costs more but keeps rollback immediate.",
        options: ["Blue-green", "Rolling"],
        urgency: "blocking",
      },
    },
  };

  assert.equal(isPendingRequestedHumanDecision(pending), true);
  assert.equal(isPendingHumanDecision(pending), true);
  assert.deepEqual(requestedHumanDecisionDetails(pending), {
    question: "Which release strategy should I use?",
    context: "Blue-green costs more but keeps rollback immediate.",
    options: ["Blue-green", "Rolling"],
    urgency: "blocking",
  });
  assert.equal(
    isPendingRequestedHumanDecision({
      ...pending,
      metadata: { decision_kind: "permission" },
    }),
    false,
  );
  assert.equal(
    isPendingRequestedHumanDecision({ ...pending, result: "human_decision_delivered" }),
    false,
  );
});

test("typed decision errors preserve distinct honest delivery outcomes", () => {
  const messages = new Set<string>();
  for (const [status, http] of [
    ["unsupported", 409],
    ["rejected", 409],
    ["delivery_uncertain", 502],
  ] as const) {
    const error = bridgeRequestError(http, "delivery failed", {
      detail: {
        code: `human_decision_${status}`,
        message: "The answer was recorded with an honest delivery result.",
        resolution: {
          delivered: false,
          delivery_status: status,
          resolution: { status },
        },
      },
    });
    assert.equal(error instanceof BridgeRequestError, true);
    assert.equal(error.status, http);
    assert.equal(error.code, `human_decision_${status}`);
    assert.equal(decisionDeliveryStatus(error), status);
    const presentation = humanDecisionFailurePresentation(error);
    assert.equal(presentation.state, "error");
    assert.equal(presentation.deliveryStatus, status);
    messages.add(presentation.message);
  }
  const delivered = humanDecisionPresentation("delivered");
  assert.equal(delivered.state, "success");
  assert.equal(delivered.deliveryStatus, "delivered");
  messages.add(delivered.message);
  assert.equal(messages.size, 4);
});

test("freeform decision submission is exact-once, cleared, and masked from feedback", async () => {
  const raw = "swordfish-private-desktop-answer";
  assert.equal(humanDecisionFeedbackChoice([], raw), FREEFORM_DECISION_LABEL);
  assert.equal(humanDecisionFeedbackChoice(["ship", "iterate"], "iterate"), "iterate");
  const prepared = prepareFreeformDecision(raw, false);
  assert.deepEqual(prepared, { decision: raw, nextValue: "" });
  assert.equal(prepareFreeformDecision(prepared?.nextValue ?? "", false), null);
  assert.equal(prepareFreeformDecision(raw, true), null);
  assert.equal(prepareFreeformDecision(` ${raw}`, false), null);
  for (const status of [
    "delivered",
    "unsupported",
    "rejected",
    "delivery_uncertain",
  ] as const) {
    assert.equal(humanDecisionPresentation(status).message.includes(raw), false);
  }

  const { readFile } = await import("node:fs/promises");
  const source = await readFile(
    new URL("./components/CommandDeck.tsx", import.meta.url),
    "utf8",
  );
  const guarded = source.indexOf("freeformSubmission.current = true;");
  const domCleared = source.indexOf('freeformInput.current.value = "";', guarded);
  const cleared = source.indexOf("setFreeform(prepared.nextValue);", domCleared);
  const dispatched = source.indexOf("onResolve(intervention, prepared.decision);", cleared);
  assert.ok(
    guarded >= 0 && domCleared > guarded && cleared > domCleared && dispatched > cleared,
  );
  assert.equal(source.includes("data-delivery-status={feedback.deliveryStatus}"), true);
});

test("undo is offered only for locally reversible action classes", () => {
  assert.equal(isSafelyUndoable("APPLY_OVERLAY", true, "overlay_applied"), true);
  assert.equal(isSafelyUndoable("CLEANUP", true, "cleanup_quarantined:2"), true);
  assert.equal(isSafelyUndoable("APPLY_OVERLAY", true, "overlay_failed"), false);
  assert.equal(
    isSafelyUndoable("APPLY_OVERLAY", true, "overlay_apply_delivery_uncertain"),
    false,
  );
  assert.equal(isSafelyUndoable("CLEANUP", true, "cleanup_refused_not_ready"), false);
  assert.equal(isSafelyUndoable("CLEANUP", true, "cleanup_restored:2"), false);
  assert.equal(
    isSafelyUndoable("CLEANUP", true, "cleanup_restore_delivery_uncertain:restored=1"),
    false,
  );
  assert.equal(isSafelyUndoable("RESPOND_PERMISSION", true, "permission_allow"), false);
  assert.equal(isSafelyUndoable("SEND_NUDGE", true, "sent"), false);
  assert.equal(isSafelyUndoable("APPLY_OVERLAY", undefined, "overlay_applied"), false);
});

test("Undo retries reuse one bounded key until canonical intent changes", async () => {
  let issued = 0;
  const nextKey = () => `undo-request-${String(++issued).padStart(4, "0")}`;
  const input = {
    interventionId: "int-cleanup",
    action: "CLEANUP",
    reversible: true,
    result: "cleanup_quarantined:2",
  };

  const first = prepareUndoAttempt(null, input, nextKey);
  assert.ok(first);
  const retry = prepareUndoAttempt(first, input, nextKey);
  assert.equal(retry, first);
  assert.equal(issued, 1);

  const otherIntervention = prepareUndoAttempt(
    retry,
    { ...input, interventionId: "int-cleanup-other" },
    nextKey,
  );
  assert.ok(otherIntervention);
  assert.notEqual(otherIntervention.idempotencyKey, first.idempotencyKey);
  assert.equal(issued, 2);

  assert.equal(
    prepareUndoAttempt(
      first,
      { ...input, result: "cleanup_restored:2" },
      nextKey,
    ),
    null,
  );
  assert.equal(issued, 2);

  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /undoAttempts\.current\.get\(id\)/u);
  assert.match(source, /body: JSON\.stringify\(\{ idempotency_key: attempt\.idempotencyKey \}\)/u);
  assert.match(source, /await Promise\.all\(\[refreshPet\(\), loadDetails\(\)\]\)/u);
  assert.match(
    source,
    /result: item\.action_taken === "CLEANUP" \? item\.result : item\.outcome \|\| item\.result/u,
  );
});

test("overlay Undo claims completion only from a delivered canonical projection", async () => {
  const pending = undoResponsePresentation("APPLY_OVERLAY", {
    ok: false,
    code: "overlay_revert_in_progress",
    state: "dispatching",
  });
  assert.equal(pending.completed, false);
  assert.match(pending.message, /does not yet claim/u);

  const completed = undoResponsePresentation("APPLY_OVERLAY", {
    ok: true,
    code: "overlay_reverted",
    state: "delivered",
  });
  assert.equal(completed.completed, true);
  assert.match(completed.message, /canonical overlay projection is reverted/u);

  const replayed = undoResponsePresentation("APPLY_OVERLAY", {
    ok: true,
    code: "overlay_already_reverted",
    state: "delivered",
    replayed: true,
  });
  assert.equal(replayed.completed, true);
  assert.match(replayed.message, /did not revert it twice/u);

  assert.match(undoFailureMessage("APPLY_OVERLAY", 409), /conflicted|refused/u);
  assert.match(undoFailureMessage("APPLY_OVERLAY", 502), /uncertain/u);
  assert.notEqual(
    undoFailureMessage("APPLY_OVERLAY", 409),
    undoFailureMessage("APPLY_OVERLAY", 502),
  );

  const original: Intervention = {
    id: "int-overlay-completed",
    session_id: "session-one",
    action_taken: "APPLY_OVERLAY",
    reversible: true,
    result: "overlay_applied",
  };
  assert.equal(
    projectCompletedOverlayUndo(original, new Set()).result,
    "overlay_applied",
  );
  const projected = projectCompletedOverlayUndo(
    original,
    new Set([original.id]),
  );
  assert.equal(projected.result, "overlay_reverted");
  assert.equal(projected.outcome, "overlay_reverted_by_human");
  assert.equal(original.result, "overlay_applied");
  assert.equal(isSafelyUndoable(projected.action_taken, projected.reversible, projected.result), false);

  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /undoResponsePresentation\(actionType, response\)/u);
  assert.match(source, /presentation\.completed/u);
  assert.match(source, /undoAttempts\.current\.delete\(id\)/u);
  assert.match(source, /error instanceof BridgeRequestError \? error\.status : null/u);
  assert.match(source, /status === 409 \|\| status === 502/u);
  assert.match(source, /Promise\.allSettled\(\[refreshPet\(\), loadDetails\(\)\]\)/u);
  assert.match(source, /auditInterventions=\{displayedInterventions\}/u);
  assert.match(source, /interventions=\{\(deck\.interventions \|\| \[\]\)/u);
  assert.match(source, /bridgeJson<AttentionMetrics>\("\/v1\/attention\/metrics"\)/u);
  assert.match(source, /setAttentionMetrics\(attentionResult\.status === "fulfilled"/u);
});

test("pet overlay expands inspector first, then the command deck", async () => {
  const { nextPetExpansion } = await import("./releasePet.ts");
  assert.equal(nextPetExpansion(""), "inspector");
  assert.equal(nextPetExpansion("compact"), "inspector");
  assert.equal(nextPetExpansion("settings"), "inspector");
  assert.equal(nextPetExpansion("inspector"), "deck");
  assert.equal(nextPetExpansion("deck"), "deck");
});

test("interventions expose honest handoff target-use evidence without claiming assimilation", async () => {
  const { readFile } = await import("node:fs/promises");
  const appSource = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  const deckSource = await readFile(
    new URL("./components/CommandDeck.tsx", import.meta.url),
    "utf8",
  );
  const typesSource = await readFile(new URL("./types.ts", import.meta.url), "utf8");

  assert.match(appSource, /metadata\?\.operator_effect_id/u);
  assert.match(appSource, /\/v1\/handoffs\/\$\{encodeURIComponent\(effectId\)\}\/assimilation/u);
  assert.match(appSource, /statuses\[result\.value\.status\.handoff_intervention_id\]/u);
  assert.match(appSource, /handoffAssimilation=\{handoffAssimilation\}/u);
  assert.match(deckSource, /Context delivered · target use not observed/u);
  assert.match(deckSource, /Target-use check unreachable/u);
  assert.match(deckSource, /this is not evidence that the target ignored the context/u);
  assert.match(appSource, /statuses\[effectId\] = "unreachable"/u);
  assert.match(deckSource, /Target acknowledged receipt · self-attested/u);
  assert.match(deckSource, /Relevant target action observed · behavioral evidence/u);
  assert.match(deckSource, /Context delivered · legacy monitoring unavailable/u);
  assert.match(deckSource, /predates the immutable typed-evidence candidate index/u);
  assert.match(deckSource, /predates the causal target-action watermark/u);
  assert.doesNotMatch(deckSource, /predates the target evidence watermark/u);
  assert.match(deckSource, /Handoff not delivered · no target-use evidence/u);
  assert.match(deckSource, /Assimilation evidence unavailable/u);
  assert.match(deckSource, /possible failure; that observation is not proof/u);
  assert.match(deckSource, /Exact delivered bundle/u);
  assert.match(deckSource, /item\.proposed_action\?\.payload\?\.bundle/u);
  assert.match(appSource, /\/v1\/interventions\?include_handoff_bundle=true/u);
  assert.match(deckSource, /Verified: false · Not proof of understanding or correct use\./u);
  assert.match(typesSource, /typed_evidence_monitoring/u);
  assert.match(typesSource, /immutable_dispatch_candidate_index/u);
  assert.match(typesSource, /capacity_limited: false/u);
});

test("pet overlay click-through is off unless settings explicitly enable it", async () => {
  const { petClickThroughEnabled } = await import("./releasePet.ts");
  assert.equal(petClickThroughEnabled(undefined), false);
  assert.equal(petClickThroughEnabled(false), false);
  assert.equal(petClickThroughEnabled("true"), false);
  assert.equal(petClickThroughEnabled(true), true);
});

test("goal editor objective is a textarea so a full task can be pasted", async () => {
  const { readFile } = await import("node:fs/promises");
  const { dirname, join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const source = await readFile(
    join(dirname(fileURLToPath(import.meta.url)), "components/GoalEditor.tsx"),
    "utf8",
  );
  assert.match(source, /Objective[\s\S]*<textarea/);
  assert.doesNotMatch(source, /Objective[\s\S]*<input[\s\S]*What outcome should persist/);
});

test("ledger edit maps the stored goal onto a PATCH update payload", () => {
  const draft = goalToDraft(
    {
      id: "goal_1",
      project_id: "pex",
      title: "Ship",
      objective: "Win honestly\n\nAcceptance criteria:\n- report.txt contains shipped",
      acceptance_criteria: ["report.txt contains shipped"],
      constraints: ["no fake benchmark"],
      non_goals: ["submit automatically"],
      preferences: ["smallest reversible change"],
      evidence_requirements: ["full suite exits 0"],
      intent_revision: 7,
      intent_hash: "a".repeat(64),
    },
    "pex",
  );
  assert.equal(draft.acceptance, "report.txt contains shipped");
  assert.equal(draft.constraints, "no fake benchmark");
  const payload = updateGoalPayload({
    ...draft,
    acceptance: "",
  }, 7);
  assert.equal(payload.mode, "update");
  assert.equal(payload.expected_intent_revision, 7);
  assert.deepEqual(payload.acceptance_criteria, []);
  assert.deepEqual(payload.constraints, ["no fake benchmark"]);
  assert.deepEqual(payload.non_goals, ["submit automatically"]);
  assert.deepEqual(payload.preferences, ["smallest reversible change"]);
});

test("ledger decisions are partitioned without inventing personality", () => {
  const partitioned = partitionLedgerDecisions([
    {
      id: "d1",
      goal_id: "g",
      statement: "Use PostgreSQL for the durable ledger",
      status: "active",
      metadata: { kind: "decision" },
    },
    {
      id: "d2",
      goal_id: "g",
      statement: "Do not rewrite the evaluator as a new service",
      status: "active",
      metadata: { kind: "rejected_approach" },
    },
    {
      id: "d3",
      goal_id: "g",
      statement: "Which checkpoint format should survive?",
      status: "uncertain",
      metadata: { kind: "unresolved_question" },
    },
  ]);
  assert.deepEqual(
    partitioned.decisions.map((item) => item.statement),
    ["Use PostgreSQL for the durable ledger"],
  );
  assert.deepEqual(
    partitioned.rejected.map((item) => item.statement),
    ["Do not rewrite the evaluator as a new service"],
  );
  assert.deepEqual(
    partitioned.unresolved.map((item) => item.statement),
    ["Which checkpoint format should survive?"],
  );
});

test("goal mutations preserve committed success across refresh failures", async () => {
  const { readFile } = await import("node:fs/promises");
  const { dirname, join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const root = dirname(fileURLToPath(import.meta.url));
  const inspector = await readFile(join(root, "components/Inspector.tsx"), "utf8");
  const app = await readFile(join(root, "App.tsx"), "utf8");
  assert.match(inspector, /Edit this ledger/);
  assert.match(inspector, /Rejected approaches/);
  assert.match(app, /\/v1\/goals\/\$\{encodeURIComponent\(editingGoalId\)\}/);
  assert.match(app, /method:\s*"PATCH"/);
  assert.match(
    app,
    /prepareGoalControlAttempt\([\s\S]*?goalControlAttempts\.current\.get\(attemptKey\),[\s\S]*?"update",[\s\S]*?updateGoalPayload\(goalDraft, editingGoal\.intent_revision!\)/,
  );
  assert.match(app, /goalControlAttempts\.current\.set\(attemptKey, prepared\.attempt\)/);
  assert.match(app, /goalControlAttempts\.current\.delete\(attemptKey\)/);
  assert.match(app, /updated\.goal_mutation_receipt\.changed/);
  assert.match(app, /Persistent ledger already matched; no change was needed\./);
  assert.match(app, /setNote\(`\$\{ledgerNote\} Its decision view could not refresh yet\.`\)/);
  assert.match(app, /The live view could not refresh yet\./);
  assert.match(
    app,
    /const refreshed = await refreshPet\(\);\s*if \(refreshed\.status === "failed"\) \{\s*setNote\(`\$\{success\} The live view could not refresh yet\.`\);/,
  );
  assert.match(app, /Pet selected\.";[\s\S]*?Its overlay could not reopen yet\./);
  assert.match(
    app,
    /if \(requestSequence !== petRequestSequence\.current\) \{\s*return \{ status: "superseded" as const \};\s*\}\s*setPet\(snapshot\);/,
  );
  assert.match(app, /attachment\.session_goal_attachment_receipt\.changed/);
  assert.match(app, /This persistent goal was already attached; no change was needed\./);
  assert.doesNotMatch(app, /\/v1\/goals\/\$\{editingGoalId\}/);
  const attachGoalBody = app.slice(
    app.indexOf("  async function attachGoal("),
    app.indexOf("  async function attachSelectedGoal("),
  );
  assert.ok(attachGoalBody.length > 0);
  assert.doesNotMatch(attachGoalBody, /refreshPet/);
  assert.match(app, /canAttachPersistentGoal\(current\)/);
  assert.match(inspector, /canAttachPersistentGoal/);
});

test("inspector shows inspected STOP state without inventing a verdict", async () => {
  const { readFile } = await import("node:fs/promises");
  const { dirname, join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const inspector = await readFile(
    join(dirname(fileURLToPath(import.meta.url)), "components/Inspector.tsx"),
    "utf8",
  );
  assert.match(inspector, /Inspected state/);
  assert.match(inspector, /verification_status/);
  assert.match(inspector, /evidence_tools/);
});

test("Agents fingerprints render counted STOP evidence instead of invented personality", () => {
  const empty = undefined;
  assert.equal(fingerprintStrengths(empty), "Insufficient observed evidence");
  assert.equal(fingerprintFailureModes(empty), "Not established from STOP inspections");
  assert.equal(fingerprintSuggestedConfig(empty), "No measured overlay recommendation yet");
  assert.equal(fingerprintCompletionReliability(empty), "Not established by this endpoint");
  assert.equal(fingerprintPrematureRate(empty), "Insufficient data");
  assert.equal(fingerprintTokenBehavior(empty), "Not exposed by this endpoint");

  const counted = {
    harness: "cursor",
    observed_sessions: 3,
    premature_stop_rate: 1 / 3,
    verified_success_rate: 1 / 3,
    inspected_stop_sessions: 3,
    strengths: ["1 inspected STOP supported by the verifier"],
    failure_modes: ["1 inspected STOP contradicted or left an acceptance gap"],
    recommended_overlays: ["evidence-before-done"],
    token_efficiency: null,
  };
  assert.equal(fingerprintStrengths(counted), "1 inspected STOP supported by the verifier");
  assert.equal(
    fingerprintFailureModes(counted),
    "1 inspected STOP contradicted or left an acceptance gap",
  );
  assert.equal(fingerprintSuggestedConfig(counted), "evidence-before-done");
  assert.equal(fingerprintCompletionReliability(counted), "0.33 from 3 inspected STOPs");
  assert.equal(fingerprintPrematureRate(counted), "0.33");
  assert.equal(fingerprintTokenBehavior(counted), "Not exposed by this endpoint");
});

test("context health copy keeps unmeasured token fields unavailable", () => {
  const empty = contextHealthCopy(undefined, 0);
  assert.equal(empty.label, "Context health not yet measured");
  assert.equal(empty.warning, false);

  const degraded = contextHealthCopy(
    {
      id: "synthetic:health",
      harness_type: "synthetic",
      status: "working",
      context_health: 0.41,
      metadata: {
        context_health_signals: {
          token_utilization: null,
          compaction_count: 2,
          forgotten_fact_count: 1,
          summary_depth: null,
        },
      },
    },
    0,
  );
  assert.match(degraded.label, /41%/);
  assert.match(degraded.label, /forgotten fact/);
  assert.match(degraded.label, /token utilization unavailable/);
  assert.equal(degraded.warning, true);

  const conflicting = contextHealthCopy(
    {
      id: "synthetic:conflict",
      harness_type: "synthetic",
      status: "working",
      context_health: 0.7,
      context_health_signals: { contradiction_count: 2 },
    },
    0,
  );
  assert.match(conflicting.label, /2 conflicting facts/);
  assert.equal(conflicting.warning, true);
});

test("context items mark superseded facts without inventing a graph", () => {
  const prior = { id: "fact-1", project_id: "pex", kind: "fact", content: "old" };
  const next = {
    id: "fact-2",
    project_id: "pex",
    kind: "fact",
    content: "new",
    supersedes: "fact-1",
  };
  assert.equal(contextItemMarks(prior, [prior, next]).superseded, true);
  assert.equal(contextItemMarks(next, [prior, next]).replacesPrior, true);
  assert.equal(contextItemMarks(prior, [prior]).superseded, false);
});

test("starter harness inventory copy stays generic and is never a freeze", () => {
  assert.deepEqual([...STARTER_HARNESS_IDS], [
    "cursor",
    "codex",
    "opencode",
    "hermes",
    "claude_code",
  ]);
  const empty = starterHarnessInventoryCopy({
    running: [],
    not_running: [...STARTER_HARNESS_IDS],
  });
  assert.equal(
    empty.running,
    "None of the starter harnesses currently have a desktop process.",
  );
  assert.match(empty.closed, /Cursor/);
  assert.match(empty.closed, /Claude Code/);
  assert.doesNotMatch(empty.closed, /Grok Bot/);
  assert.match(empty.note, /never a freeze blocker/);
  assert.doesNotMatch(empty.note, /this Cursor|this machine/i);

  const mixed = starterHarnessInventoryCopy({
    running: ["cursor"],
    not_running: ["codex"],
  });
  assert.equal(mixed.running, "Cursor");
  assert.equal(mixed.closed, "Codex");

  const missing = starterHarnessInventoryCopy();
  assert.equal(missing.running, "Starter desktop inventory is unavailable.");
  assert.match(missing.note, /never a freeze blocker/);

  const fromDiscover = starterInventoryFromDiscover({
    found: [
      { name: "cursor", kind: "desktop" },
      { name: "grok_bot", kind: "desktop" },
      { name: "opencode", kind: "http" },
    ],
    not_running: ["codex", "opencode", "hermes", "claude_code", "grok_bot"],
  });
  assert.deepEqual(fromDiscover.running, ["cursor"]);
  assert.deepEqual(fromDiscover.not_running, [
    "claude_code",
    "codex",
    "hermes",
    "opencode",
  ]);
});

const IDENTITY_ONE = `prj_${"1".repeat(32)}`;
const IDENTITY_TWO = `prj_${"2".repeat(32)}`;

function identityStatus(
  status: "unregistered" | "active" | "quarantined",
): ProjectIdentityStatusView {
  const base = {
    schema: "pex.project-identity-status.v1" as const,
    legacy_project_id: "C:\\Work\\Project ",
  };
  if (status === "unregistered") {
    return {
      ...base,
      status,
      credential_reissue_blocked: false,
      fresh_credentials_required: false,
    };
  }
  if (status === "active") {
    return {
      ...base,
      status,
      credential_reissue_blocked: false,
      fresh_credentials_required: true,
      identity: {
        schema: "pex.project-identity.v2",
        id: IDENTITY_ONE,
        locator_fingerprints: [`ploc_${"a".repeat(64)}`],
        created_at: "2026-08-31T10:00:00Z",
      },
      locators: [],
      binding: { status: "active" },
      last_resolution: null,
    };
  }
  return {
    ...base,
    status,
    credential_reissue_blocked: true,
    fresh_credentials_required: true,
    binding: {
      status: "quarantined",
      resolution_id: "historical-resolution",
      resolved_at: "2026-08-31T10:01:00Z",
    },
    candidate_count: 2,
    candidate_offset: 0,
    next_candidate_offset: null,
    candidates: [],
  };
}

test("project identity presentation distinguishes live status and keeps credential warning", () => {
  const missing = projectIdentityPresentation(null);
  const unregistered = projectIdentityPresentation(identityStatus("unregistered"));
  const active = projectIdentityPresentation(identityStatus("active"));
  const quarantined = projectIdentityPresentation(identityStatus("quarantined"));

  assert.equal(missing.canResolve, false);
  assert.match(unregistered.title, /not registered/i);
  assert.equal(unregistered.canResolve, false);
  assert.equal(active.tone, "active");
  assert.match(active.freshCredentialWarning || "", /not restored/i);
  assert.equal(quarantined.tone, "quarantined");
  assert.equal(quarantined.canResolve, true);
  assert.match(quarantined.detail, /reissue remains blocked/i);
});

test("historical resolution never overrides live project requarantine", () => {
  const response: ProjectIdentityResolutionResponse = {
    outcome: "replayed",
    current_status: "active",
    fresh_credentials_required: true,
    identity: {
      schema: "pex.project-identity.v2",
      id: IDENTITY_ONE,
      locator_fingerprints: [`ploc_${"a".repeat(64)}`],
      created_at: "2026-08-31T10:00:00Z",
    },
    binding: { status: "active" },
    resolution: {
      schema: "pex.project-identity-resolution.v1",
      resolution_id: "resolution-one",
      legacy_project_id: "C:\\Work\\Project ",
      selected_identity_id: IDENTITY_ONE,
      candidate_identity_ids: [IDENTITY_ONE, IDENTITY_TWO],
      resolved_by: "local_bridge_operator",
      rationale: "Confirmed exact workspace.",
      resolved_at: "2026-08-31T10:01:00Z",
      credentials_restored: false,
      resolved_binding: { status: "active" },
    },
  };
  const message = projectIdentityResolutionMessage(
    response,
    identityStatus("quarantined"),
  );
  assert.match(message, /live binding is quarantined again/i);
  assert.doesNotMatch(message, /live binding is active/i);
  assert.match(message, /no credential was restored/i);
});

test("project identity resolution requires explicit intent and reuses only an identical key", () => {
  let generated = 0;
  const nextKey = () => `resolve-project-key-${++generated}`;
  const base = {
    legacyProjectId: "C:\\Work\\Project ",
    selectedIdentityId: IDENTITY_ONE,
    rationale: "  Confirmed exact workspace.  ",
  };

  assert.equal(
    prepareProjectIdentityResolutionAttempt(null, { ...base, selectedIdentityId: "" }, nextKey),
    null,
  );
  assert.equal(
    prepareProjectIdentityResolutionAttempt(null, { ...base, rationale: "   " }, nextKey),
    null,
  );
  assert.equal(generated, 0);

  const first = prepareProjectIdentityResolutionAttempt(null, base, nextKey);
  assert.ok(first);
  assert.equal(first.legacyProjectId, "C:\\Work\\Project ");
  assert.equal(first.rationale, "Confirmed exact workspace.");
  const retry = prepareProjectIdentityResolutionAttempt(first, base, nextKey);
  assert.equal(retry, first);
  assert.equal(generated, 1);

  const changedRationale = prepareProjectIdentityResolutionAttempt(
    first,
    { ...base, rationale: "Confirmed a different exact workspace." },
    nextKey,
  );
  const changedCandidate = prepareProjectIdentityResolutionAttempt(
    first,
    { ...base, selectedIdentityId: IDENTITY_TWO },
    nextKey,
  );
  assert.notEqual(changedRationale?.idempotencyKey, first.idempotencyKey);
  assert.notEqual(changedCandidate?.idempotencyKey, first.idempotencyKey);
  assert.equal(generated, 3);
});

test("project identity completion is bound to the selected key and revision", () => {
  assert.equal(projectIdentityCompletionIsCurrent("project-a", "project-a", 4, 4), true);
  assert.equal(projectIdentityCompletionIsCurrent("project-a", "project-b", 4, 4), false);
  assert.equal(projectIdentityCompletionIsCurrent("project-a", "project-a", 4, 5), false);
});

test("project identity panel exposes exact typed evidence and explicit resolution", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(
    new URL("./components/ProjectIdentityPanel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /<fieldset[\s\S]*<legend>Confirmed project identity<\/legend>/);
  assert.match(source, /type="radio"/);
  assert.doesNotMatch(source, /defaultChecked|candidates\[0\]/);
  assert.match(source, /<textarea[\s\S]*maxLength=\{2000\}/);
  assert.match(source, /aria-describedby/);
  assert.match(source, /role=\{feedback\?\.state === "error" \? "alert" : "status"\}/);
  assert.match(source, /locator\.raw/);
  assert.match(source, /locator\.canonical/);
  assert.match(source, /locator\.origin\.namespace/);
  assert.match(source, /locator\.origin\.host/);
  assert.match(source, /locator\.physical\.volume_id/);
  assert.match(source, /locator\.physical\.object_id/);
  assert.match(source, /locator\.members\.map/);
  assert.match(source, /does not restore old MCP or hook credentials/i);
  assert.match(source, /disabled=\{resolving\}/);
  assert.match(source, /live quarantine list is unavailable; no empty-state conclusion/i);
  assert.match(source, /last successful live conflict query returned no project identity quarantines/i);
  assert.doesNotMatch(source, />No live project identity quarantines are listed\.</);
});

test("project identity App flow separates summary polling from active candidate status", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("./App.tsx", import.meta.url), "utf8");

  assert.match(source, /const loadProjectIdentityConflicts = useCallback/);
  assert.match(source, /const loadProjectIdentityStatus = useCallback/);
  assert.match(source, /requestSequence !== identityConflictRequestSequence\.current/);
  assert.match(source, /requestSequence !== identityStatusRequestSequence\.current/);
  assert.match(source, /legacy_project_id=\$\{encodeURIComponent\(exactProjectId\)\}/);
  assert.match(
    source,
    /surface !== "deck" \|\| shell !== "main" \|\| activeView !== "decisions"/,
  );
  assert.match(source, /idempotency_key: attempt\.idempotencyKey/);
  assert.match(source, /projectIdentityCompletionIsCurrent/);
  assert.match(source, /const \[liveStatus\] = await Promise\.all\(\[/);
  assert.match(source, /projectIdentityResolutionMessage\(response, liveStatus\)/);
});

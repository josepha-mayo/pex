import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  isSupervisorRevision,
  supervisorCredentialAudience,
  supervisorRequest,
  supervisorReviewLimitCopy,
  supervisorDispatchLimitDraft,
  supervisorSavePayload,
  supervisorSaveResponseIsCurrent,
  type SupervisorDraft,
} from "./supervisorDraft.ts";

const custom: SupervisorDraft = {
  provider: "custom",
  modelId: "example-model",
  authMode: "custom",
  protocol: "openai",
  baseUrl: "https://models.example.test/v1",
  apiKey: "fixture-key-not-a-real-credential",
  credentialAction: "keep",
};

test("saved review cap is explicit, bounded and omitted for unsupported bridges", () => {
  const draft = { ...custom, apiKey: "" };
  assert.equal(supervisorSavePayload(draft, 1, null).dispatch_limit_override, undefined);
  assert.equal(supervisorSavePayload({ ...draft, dispatchLimit: "20" }, 1, null).dispatch_limit_override, 20);
  assert.equal(supervisorSavePayload({ ...draft, dispatchLimit: "" }, 1, null).dispatch_limit_override, null);
  for (const dispatchLimit of ["0", "-1", "1.5", "1e2", "100001", "NaN"]) {
    assert.throws(() => supervisorSavePayload({ ...draft, dispatchLimit }, 1, null), /whole-number/u);
  }
  assert.equal(supervisorDispatchLimitDraft(null), "");
  assert.equal(supervisorDispatchLimitDraft(20), "20");
  for (const value of [undefined, "20", true, 0, 1.5, 100001]) {
    assert.equal(supervisorDispatchLimitDraft(value), undefined);
  }
});

test("review limit copy distinguishes unknown, uncapped and bounded dispatches", () => {
  assert.match(supervisorReviewLimitCopy(null), /No per-session dispatch cap/u);
  assert.match(supervisorReviewLimitCopy(20), /20 semantic dispatches per session/u);
  for (const value of [undefined, true, "20", 0, -1, 1.5, 100001, NaN]) {
    assert.match(supervisorReviewLimitCopy(value), /unavailable/u);
    assert.doesNotMatch(supervisorReviewLimitCopy(value), /No per-session/u);
  }
});

test("a pasted key is sent only with its exact selected destination and current revision", () => {
  assert.deepEqual(supervisorSavePayload(custom, 7, supervisorCredentialAudience(custom)), {
    expected_revision: 7,
    provider: "custom",
    model_id: "example-model",
    auth_mode: "custom",
    protocol: "openai",
    base_url: "https://models.example.test/v1",
    api_key: custom.apiKey,
  });
});

for (const [field, value] of [
  ["provider", "openai"],
  ["authMode", "api_key"],
  ["protocol", "anthropic"],
  ["baseUrl", "https://another.example.test/v1"],
] as const) {
  test(`changing ${field} cannot carry a previously pasted key`, () => {
    const changed = { ...custom, [field]: value };
    assert.throws(() => supervisorSavePayload(changed, 7, supervisorCredentialAudience(custom)), {
      message: "The credential destination changed. Paste a key for the selected destination.",
    });
    // Explicitly pasting a credential for the new destination restores the save path.
    assert.equal(supervisorSavePayload(changed, 7, supervisorCredentialAudience(changed)).api_key, custom.apiKey);
  });
}

test("floating pet uses canonical first-run status instead of raw quiet copy", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  for (const newline of ["\n", "\r\n"]) {
    const app = source.replace(/\r?\n/gu, newline);
    const start = app.search(/if \(shell === "pet"\) \{\s+return \(/u);
    assert.ok(start >= 0, "floating pet route must exist");
    const end = app.indexOf("if (!bridgeAvailable)", start);
    assert.ok(end > start, "floating pet route boundary must exist");
    const petRoute = app.slice(start, end);

    assert.match(petRoute, /<PetStage[\s\S]*?status=\{homeStatus\}/u);
    assert.doesNotMatch(petRoute, /<PetStage[\s\S]*?status=\{status\}/u);
  }
});

test("floating pet refreshes canonical goals without loading heavy settings state", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

  assert.match(
    app,
    /const refreshPetGoals = useCallback\([\s\S]*?bridgeJson<Goal\[\]>\("\/v1\/goals"\)[\s\S]*?markCanonical\("goals", "fresh"\)/u,
  );
  assert.match(
    app,
    /if \(!bridgeAvailable \|\| shell !== "pet"\) return;[\s\S]*?refreshPetGoals\(\)[\s\S]*?baseRequestSequence\.current \+= 1/u,
  );
});

test("a missing credential binding cannot dispatch a key or expose it in errors", () => {
  assert.throws(() => supervisorSavePayload(custom, 7, null), (error: unknown) => {
    assert.ok(error instanceof Error);
    assert.ok(!error.message.includes(custom.apiKey));
    assert.ok(!error.message.includes(custom.baseUrl));
    return true;
  });
});

test("model selection is not a credential destination change", () => {
  const changed = { ...custom, modelId: "different-model" };
  assert.equal(supervisorSavePayload(changed, 7, supervisorCredentialAudience(custom)).model_id, "different-model");
});

test("audience normalization matches the trimmed payload destination", () => {
  const padded = { ...custom, provider: " custom ", baseUrl: ` ${custom.baseUrl} ` };
  assert.equal(supervisorCredentialAudience(padded), supervisorCredentialAudience(custom));
  assert.equal(supervisorSavePayload(padded, 7, supervisorCredentialAudience(custom)).base_url, custom.baseUrl);
});

test("named provider overrides are explicit and bound, not hidden inherited endpoints", () => {
  const named = { ...custom, provider: "openai", authMode: "api_key" as const };
  const payload = JSON.parse(JSON.stringify(supervisorSavePayload(named, 7, supervisorCredentialAudience(named))));
  assert.equal(payload.base_url, named.baseUrl);
  assert.ok(!("protocol" in payload));
  assert.throws(() => supervisorSavePayload({ ...named, baseUrl: "https://other.example.test/v1" }, 7, supervisorCredentialAudience(named)), /destination changed/);
  const registryDefault = { ...named, baseUrl: "" };
  assert.equal(supervisorSavePayload(registryDefault, 7, supervisorCredentialAudience(registryDefault)).base_url, null);
});

for (const authMode of ["login", "local", "bedrock", "agentcore"] as const) {
  test(`${authMode} rejects a pasted key even if the audience matches`, () => {
    const changed = { ...custom, authMode };
    assert.throws(() => supervisorSavePayload(changed, 7, supervisorCredentialAudience(changed)), /does not accept a pasted API key/);
  });
}

test("auto-detect never dispatches a pasted key to an unspecified provider", () => {
  const changed = { ...custom, provider: "" };
  assert.throws(() => supervisorSavePayload(changed, 7, supervisorCredentialAudience(changed)), /does not accept a pasted API key/);
});

test("empty-key credential actions are explicit, mutually exclusive, and retain revision", () => {
  for (const credentialAction of ["keep", "environment", "clear"] as const) {
    const payload = supervisorSavePayload({ ...custom, apiKey: "", credentialAction }, 7, null);
    assert.equal(payload.expected_revision, 7);
    assert.ok(!("api_key" in payload));
    assert.equal(payload.use_environment_credentials, credentialAction === "environment" ? true : undefined);
    assert.equal(payload.clear_api_key, credentialAction === "clear" ? true : undefined);
  }
});

test("the empty-box action does not override an explicitly pasted destination-bound key", () => {
  for (const credentialAction of ["environment", "clear"] as const) {
    const payload = supervisorSavePayload({ ...custom, credentialAction }, 7, supervisorCredentialAudience(custom));
    assert.equal(payload.api_key, custom.apiKey);
    assert.ok(!("clear_api_key" in payload));
    assert.ok(!("use_environment_credentials" in payload));
  }
});

test("initial auto-detect opts into environment credentials without treating later keep as reset", () => {
  const draft = { ...custom, provider: "", apiKey: "" };
  assert.equal(supervisorSavePayload(draft, 0, null).use_environment_credentials, true);
  assert.equal(supervisorSavePayload(draft, 7, null).use_environment_credentials, undefined);
});

test("invalid revisions cannot silently become a first-run write", () => {
  for (const revision of [undefined, -1, 0.5, NaN, Infinity, 2_147_483_648]) {
    assert.throws(() => supervisorSavePayload(custom, revision, supervisorCredentialAudience(custom)), /revision is unavailable/);
  }
});

test("canonical revision validation rejects missing, coerced and out-of-contract authority", () => {
  for (const value of [undefined, null, false, "0", {}, [], -1, 0.5, NaN, Infinity, 2_147_483_648]) {
    assert.equal(isSupervisorRevision(value), false);
  }
  for (const value of [0, 1, 2_147_483_647]) assert.equal(isSupervisorRevision(value), true);
});

test("save responses must still own both the submitted draft and settings view", () => {
  assert.equal(supervisorSaveResponseIsCurrent(3, 3, 8, 8), true);
  assert.equal(supervisorSaveResponseIsCurrent(3, 4, 8, 8), false);
  assert.equal(supervisorSaveResponseIsCurrent(3, 3, 8, 9), false);
  assert.equal(supervisorSaveResponseIsCurrent(3, 4, 8, 9), false);
});

test("a stalled settings request aborts once without replaying an uncertain write", async () => {
  let calls = 0;
  let seenSignal: AbortSignal | undefined;
  let finish: ((value: string) => void) | undefined;
  const pending = supervisorRequest((signal) => {
    calls += 1;
    seenSignal = signal;
    return new Promise<string>((resolve) => { finish = resolve; });
  }, 5);
  await assert.rejects(pending, /Reload settings to check its outcome before retrying/);
  assert.equal(calls, 1);
  assert.equal(seenSignal?.aborted, true);
  finish?.("late backend commit");
  await assert.rejects(pending, /timed out/);
  assert.equal(calls, 1);
});

test("a completed or failed settings request clears its deadline without retry", async () => {
  let seenSignal: AbortSignal | undefined;
  const value = await supervisorRequest(async (signal) => {
    seenSignal = signal;
    return "canonical";
  }, 5);
  assert.equal(value, "canonical");
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(seenSignal?.aborted, false);
  let calls = 0;
  await assert.rejects(supervisorRequest(async () => {
    calls += 1;
    throw new Error("fixture failure");
  }), /fixture failure/);
  assert.equal(calls, 1);
});

test("source contract wires destination guards and disables every supervisor input during save", () => {
  // Wiring contract only: this does not claim a rendered React or native UI test.
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const settings = readFileSync(new URL("./components/SettingsPage.tsx", import.meta.url), "utf8");
  for (const field of ["Auth", "Protocol", "BaseUrl"]) {
    assert.ok(app.includes(`changeSupervisorDraft(supervisor${field}, value, setSupervisor${field}, true)`));
  }
  assert.match(app, /supervisorKeyAudience\.current = next \? supervisorCredentialAudience\(/);
  assert.match(app, /if \(supervisorSaveInFlight\.current \|\| current === next\) return/);
  const form = settings.slice(settings.indexOf('<p className="eyebrow">Supervisor inference</p>'), settings.indexOf('<p className="eyebrow">Attention</p>'));
  const controls = form.match(/<(?:input|select)\b[^>]*>/g) || [];
  assert.equal(controls.length, 10);
  for (const control of controls) assert.match(control, /disabled=\{!settingsAvailable \|\| savingSupervisor(?: \|\| supervisorDispatchLimit === undefined)?\}/);
  assert.match(app, /changeSupervisorDraft\(supervisorDispatchLimit \?\? "", value, setSupervisorDispatchLimit\)/);
  assert.match(app, /if \(supervisorSaveInFlight\.current\) return;\s+const requestSequence = \+\+settingsRequestSequence\.current/);
});

test("settings sections expose an accessible keyboard-operated tab contract", () => {
  // Wiring contract only: native WebView QA separately exercises the rendered tabs.
  const settings = readFileSync(new URL("./components/SettingsPage.tsx", import.meta.url), "utf8");
  assert.match(settings, /role="tablist"/);
  assert.match(settings, /role="tab"/);
  assert.match(settings, /aria-selected=\{section === item\}/);
  assert.match(settings, /aria-controls="settings-panel"/);
  assert.match(settings, /tabIndex=\{section === item \? 0 : -1\}/);
  assert.match(settings, /\["ArrowLeft", "ArrowRight", "Home", "End"\]/);
  assert.match(settings, /role="tabpanel"/);
  assert.match(settings, /aria-labelledby=\{`settings-tab-\$\{section\}`\}/);
  assert.match(settings, /settingsAvailable && !settingsIssue && supervisor\?\.model_loaded \? "companion" : "supervisor"/);
  // An explicit Home setup destination must survive background settings loading.
  assert.match(settings, /initialSection \?\? \(settingsAvailable/);
  assert.match(settings, /if \(!initialSection && \(settingsIssue \|\| !settingsAvailable\)\) setSection\("supervisor"\)/);
});

test("Home setup routes reuse guarded connection and goal flows without writing on navigation", () => {
  // Source wiring only; native route observations are recorded separately.
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  const inspector = readFileSync(new URL("./components/Inspector.tsx", import.meta.url), "utf8");
  assert.match(app, /firstRunGuidance\(\{[\s\S]*?sessionFresh: sessionStateFresh,[\s\S]*?goalFresh: goalStateFresh/);
  assert.match(app, /if \(setup\.cta\?\.intent === "goal"\) openGoalSetup\(\)/);
  assert.match(app, /else openSettings\("connections"\)/);
  assert.match(app, /initialSection=\{settingsDestination\}/);
  assert.match(app, /supervisorNotice=\{supervisorNotice\}/);
  assert.match(app, /supervisorAvailability\(\{ supervisor, supervisorFresh: settingsAvailable \}\)/);
  const route = app.slice(app.indexOf("function openGoalSetup()"), app.indexOf('if (shell === "pet")', app.indexOf("function openGoalSetup()")));
  assert.match(route, /openInspector\(\)/);
  assert.doesNotMatch(route, /bridgeJson|POST|PATCH|setGoalDraft|setEditingGoalId/);
  assert.match(inspector, /data-goal-setup="true" tabIndex=\{-1\}/);
  assert.match(app, /statusWithFirstRunGuidance\(status, setup, Boolean\(pet\?\.paused\)\)/);
});

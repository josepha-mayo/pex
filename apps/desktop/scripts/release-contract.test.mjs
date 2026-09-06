import assert from "node:assert/strict";
import test from "node:test";

import {
  EXPECTED_BUNDLE_ICONS,
  EXPECTED_BRIDGE_RECOVERY_PERMISSION,
  EXPECTED_FOCUS_PERMISSION,
  EXPECTED_MAIN_PERMISSIONS,
  EXPECTED_PET_PERMISSIONS,
  EXPECTED_SIDECAR_BINS,
  assertCanonicalRepoRelativePath,
  assertFrozenBundleInventory,
  assertSchema2EvidenceClosure,
  classifyGitReleaseInputs,
  parseFrozenBundleInventory,
  preflightSnapshotIsStable,
  sidecarBuildPolicy,
  sidecarStampMatches,
  tauriReleaseWiringMatches,
  toolchainsMatch,
} from "./release-contract.mjs";

const hash = (character) => character.repeat(64);

function wiringFixture() {
  const packageJson = {
    version: "0.1.0",
    scripts: {
      "prepare:sidecar": "node scripts/build-sidecar.mjs",
      "prepare:sidecar:release": "node scripts/build-sidecar.mjs --release-build",
      "preflight:release": "node scripts/build-sidecar.mjs --preflight-release",
      build: "tsc && vite build",
      tauri: "tauri",
    },
  };
  return {
    packageJson,
    tauri: {
      version: packageJson.version,
      build: {
        beforeBuildCommand: "npm run prepare:sidecar:release && npm run build",
        frontendDist: "../dist",
      },
      app: {
        windows: [
          { label: "main", visible: true },
          { label: "pet", url: "pet.html", visible: false },
        ],
      },
      bundle: {
        active: true,
        targets: "all",
        externalBin: [...EXPECTED_SIDECAR_BINS],
        icon: [...EXPECTED_BUNDLE_ICONS],
      },
    },
    mainCapability: {
      identifier: "main",
      windows: ["main"],
      permissions: [...EXPECTED_MAIN_PERMISSIONS],
    },
    petCapability: {
      identifier: "pet",
      windows: ["pet"],
      permissions: [...EXPECTED_PET_PERMISSIONS],
    },
    cargoVersion: packageJson.version,
    focusPermission: EXPECTED_FOCUS_PERMISSION,
    bridgeRecoveryPermission: EXPECTED_BRIDGE_RECOVERY_PERMISSION,
  };
}

function evidenceFixture() {
  const builtInPets = ["pex", "ledger", "mesh", "nudge", "drift", "quiet", "ember", "von"];
  const requiredPlaybackStates = [
    "idle",
    "waving",
    "jumping",
    "running",
    "running-left",
    "running-right",
    "failed",
    "waiting",
    "review",
  ];
  const auditPath = "_audit/release/manifest.json";
  const playbackPath = "_audit/release/current-20260831/direct-playback-qa.json";
  const directPlayback = { path: playbackPath, bytes: 11397, sha256: hash("b") };
  const release = {
    schema_version: 2,
    built_in_pet_ids: builtInPets,
    fleet_audit: { path: auditPath, bytes: 2727, sha256: hash("a") },
    direct_playback: directPlayback,
    pets: builtInPets.map((id) => ({
      id,
      manifest_sha256: hash("c"),
      spritesheet_sha256: hash("d"),
      receipt: `_audit/release/${id}.json`,
      receipt_sha256: hash("e"),
    })),
  };
  const audit = {
    schema_version: 2,
    status: "approved",
    built_in_pet_count: builtInPets.length,
    custom_imports_included: false,
    direct_playback: { ...directPlayback },
    pets: release.pets.map((pet) => ({
      id: pet.id,
      spritesheet_sha256: pet.spritesheet_sha256,
      release_record: pet.receipt,
      release_record_sha256: pet.receipt_sha256,
    })),
  };
  const playback = {
    schema_version: 1,
    review_kind: "exact-eight-direct-animated-playback",
    verdict: "pass",
    scope: {
      pet_ids: builtInPets,
      required_states: requiredPlaybackStates,
      display_cell: "192x208",
      gif_count: 72,
    },
    browser_playback_method: {
      network_or_provider: false,
      server: false,
      sessions_closed: true,
      canvas_status_used_as_evidence: false,
    },
    qualitative_review: { verdict: "pass" },
  };
  return { release, audit, playback, builtInPets, requiredPlaybackStates, auditPath, playbackPath };
}

test("canonical release paths reject traversal and aliases while preserving filename namespaces", () => {
  assert.equal(
    assertCanonicalRepoRelativePath(
      "_audit/release/evidence/pex-blind-a.json",
      "_audit/release/evidence/pex-",
      "Evidence",
      "prefix",
    ),
    "_audit/release/evidence/pex-blind-a.json",
  );
  assert.equal(
    assertCanonicalRepoRelativePath(
      "_audit/release/manifest.json",
      "_audit/release/manifest.json",
    ),
    "_audit/release/manifest.json",
  );
  for (const candidate of [
    "../manifest.json",
    "_audit/release/../manifest.json",
    "_audit//release/manifest.json",
    "_audit\\release\\manifest.json",
    "/_audit/release/manifest.json",
    "C:/_audit/release/manifest.json",
    "_AUDIT/release/manifest.json",
    "_audit/release/manifest.json.alias",
  ]) {
    assert.throws(
      () => assertCanonicalRepoRelativePath(candidate, "_audit/release/manifest.json"),
      /canonical|segments|stay under/u,
      candidate,
    );
  }
});

test("Git index classification rejects every non-normal flag without losing unusual paths", () => {
  const inputs = ["normal", "skip", "assumed", "space name", "line\nbreak", "missing"];
  const result = classifyGitReleaseInputs(
    inputs,
    "H normal\0S skip\0h assumed\0H space name\0H line\nbreak\0",
  );
  assert.deepEqual(result.untrackedInputs, ["missing"]);
  assert.deepEqual(result.hiddenIndexInputs, ["skip", "assumed"]);
  assert.equal(result.trackedFlags.get("line\nbreak"), "H");
  assert.throws(() => classifyGitReleaseInputs(["a"], "malformed\0"), /Malformed/u);
  assert.throws(() => classifyGitReleaseInputs(["a"], "H a\0S a\0"), /Duplicate/u);
});

test("toolchain verification rejects each active-versus-pinned or locked mismatch", () => {
  const fixture = {
    pins: { node: "22.14.0", python: "3.13.2", rust: "1.85.0" },
    active: {
      node: "22.14.0",
      python: "3.13.2",
      rust: "rustc 1.85.0 (hash 2025-02-17)",
      pyinstaller: "6.12.0",
    },
    uvLock: 'version = 1\n\n[[package]]\nname = "pyinstaller"\nversion = "6.12.0"\nsource = { registry = "x" }\n',
  };
  assert.equal(toolchainsMatch(fixture), true);
  for (const mutate of [
    (value) => { value.active.node = "22.14.1"; },
    (value) => { value.active.python = "3.13.3"; },
    (value) => { value.active.rust = "rustc 1.85.1 (hash)"; },
    (value) => { value.active.pyinstaller = "6.13.0"; },
    (value) => { value.uvLock = value.uvLock.replace('version = "6.12.0"', 'version = "6.11.0"'); },
  ]) {
    const adversarial = structuredClone(fixture);
    mutate(adversarial);
    assert.equal(toolchainsMatch(adversarial), false);
  }
});

test("Tauri release wiring rejects capability widening and window-scope widening", () => {
  const fixture = wiringFixture();
  assert.equal(tauriReleaseWiringMatches(fixture), true);

  const widenedMain = structuredClone(fixture);
  widenedMain.mainCapability.permissions.push("shell:allow-execute");
  assert.equal(tauriReleaseWiringMatches(widenedMain), false);

  const widenedPet = structuredClone(fixture);
  widenedPet.petCapability.windows.push("main");
  assert.equal(tauriReleaseWiringMatches(widenedPet), false);

  const resourceAlias = structuredClone(fixture);
  resourceAlias.tauri.bundle.resources = ["../secrets"];
  assert.equal(tauriReleaseWiringMatches(resourceAlias), false);

  const hiddenMain = structuredClone(fixture);
  hiddenMain.tauri.app.windows[0].visible = false;
  assert.equal(tauriReleaseWiringMatches(hiddenMain), false);

  const visiblePet = structuredClone(fixture);
  visiblePet.tauri.app.windows[1].visible = true;
  assert.equal(tauriReleaseWiringMatches(visiblePet), false);

  const widenedRecovery = structuredClone(fixture);
  widenedRecovery.bridgeRecoveryPermission += '\ncommands.allow = ["bridge_token"]';
  assert.equal(tauriReleaseWiringMatches(widenedRecovery), false);

  const cachedPackageBuild = structuredClone(fixture);
  cachedPackageBuild.tauri.build.beforeBuildCommand = "npm run prepare:sidecar && npm run build";
  assert.equal(tauriReleaseWiringMatches(cachedPackageBuild), false);

  const nonCleanReleaseCommand = structuredClone(fixture);
  nonCleanReleaseCommand.packageJson.scripts["prepare:sidecar:release"] =
    "node scripts/build-sidecar.mjs";
  assert.equal(tauriReleaseWiringMatches(nonCleanReleaseCommand), false);
});

test("release sidecar mode always bypasses cache and cleans PyInstaller", () => {
  assert.deepEqual(sidecarBuildPolicy([]), {
    releaseBuild: false,
    preflightRelease: false,
    validatePetsOnly: false,
    allowCachedHelpers: true,
    pyinstallerCleanArgs: [],
  });
  assert.deepEqual(sidecarBuildPolicy(["--release-build"]), {
    releaseBuild: true,
    preflightRelease: false,
    validatePetsOnly: false,
    allowCachedHelpers: false,
    pyinstallerCleanArgs: ["--clean"],
  });
  assert.throws(
    () => sidecarBuildPolicy(["--release-build", "--preflight-release"]),
    /mutually exclusive/u,
  );
  assert.throws(() => sidecarBuildPolicy([42]), /must be text/u);
});

test("sidecar stamp is exact and rejects stale, forged, malformed, and extended records", () => {
  const expected = {
    inputSha256: hash("a"),
    bridgeSha256: hash("b"),
    cursorHookSha256: hash("c"),
    cursorObserveSha256: hash("d"),
  };
  const stamp = {
    version: 3,
    input_sha256: expected.inputSha256,
    bridge_sha256: expected.bridgeSha256,
    cursor_hook_sha256: expected.cursorHookSha256,
    cursor_observe_sha256: expected.cursorObserveSha256,
  };
  assert.equal(sidecarStampMatches({ stamp, ...expected }), true);
  assert.equal(sidecarStampMatches({ stamp: { ...stamp, input_sha256: hash("d") }, ...expected }), false);
  assert.equal(sidecarStampMatches({ stamp: { ...stamp, bridge_sha256: hash("d") }, ...expected }), false);
  assert.equal(sidecarStampMatches({ stamp: { ...stamp, trusted: true }, ...expected }), false);
  assert.equal(sidecarStampMatches({ stamp, ...expected, bridgeSha256: null }), false);
  assert.equal(sidecarStampMatches({ stamp: { ...stamp, cursor_hook_sha256: "B".repeat(64) }, ...expected }), false);
  assert.equal(sidecarStampMatches({ stamp: { ...stamp, cursor_observe_sha256: hash("e") }, ...expected }), false);
  assert.equal(sidecarStampMatches({ stamp: { ...stamp, version: 2 }, ...expected }), false);
});

test("frozen bundle inventory rejects corrupt, incomplete, reordered, or extended smoke output", () => {
  const expected = {
    version: 1,
    pets: ["pex", "ledger"].map((id, index) => ({
      id,
      manifest_sha256: hash(index === 0 ? "a" : "b"),
      spritesheet_sha256: hash(index === 0 ? "c" : "d"),
      spritesheet_bytes: 100 + index,
    })),
  };
  assert.doesNotThrow(() => assertFrozenBundleInventory(structuredClone(expected), expected));
  assert.deepEqual(parseFrozenBundleInventory(`${JSON.stringify(expected)}\n`), expected);
  assert.throws(() => parseFrozenBundleInventory(""), /invalid bundle inventory/u);
  assert.throws(() => parseFrozenBundleInventory("not-json"), /invalid bundle inventory/u);
  for (const mutate of [
    (value) => { value.version = 2; },
    (value) => { value.pets.reverse(); },
    (value) => { value.pets[0].spritesheet_bytes += 1; },
    (value) => { value.pets.pop(); },
    (value) => { value.pets[0].unexpected = true; },
    (value) => { value.unexpected = true; },
  ]) {
    const actual = structuredClone(expected);
    mutate(actual);
    assert.throws(() => assertFrozenBundleInventory(actual, expected), /inventory mismatch/u);
  }
});

test("preflight snapshot comparison rejects release, source, and status TOCTOU independently", () => {
  const stable = {
    releaseInputSha256Before: hash("a"),
    releaseInputSha256After: hash("a"),
    sourceInputSha256Before: hash("b"),
    sourceInputSha256After: hash("b"),
    statusBefore: [" M one"],
    statusAfter: [" M one"],
  };
  assert.equal(preflightSnapshotIsStable(stable), true);
  for (const mutate of [
    (value) => { value.releaseInputSha256After = hash("c"); },
    (value) => { value.sourceInputSha256After = hash("c"); },
    (value) => { value.statusAfter.push("?? two"); },
    (value) => { value.statusAfter = []; },
  ]) {
    const changed = structuredClone(stable);
    mutate(changed);
    assert.equal(preflightSnapshotIsStable(changed), false);
  }
});

test("schema-2 evidence closure rejects corrupt links and forged playback authority", () => {
  const fixture = evidenceFixture();
  assert.doesNotThrow(() => assertSchema2EvidenceClosure(fixture));
  for (const mutate of [
    (value) => { value.release.schema_version = 1; },
    (value) => { value.release.built_in_pet_ids.reverse(); },
    (value) => { value.release.fleet_audit.path += ".alias"; },
    (value) => { value.release.direct_playback.bytes = 0; },
    (value) => { value.release.direct_playback.sha256 = "forged"; },
    (value) => { value.audit.direct_playback.sha256 = hash("f"); },
    (value) => { value.audit.pets[0].release_record = "_audit/release/ledger.json"; },
    (value) => { value.playback.scope.pet_ids.reverse(); },
    (value) => { value.playback.scope.required_states.pop(); },
    (value) => { value.playback.browser_playback_method.network_or_provider = true; },
    (value) => { value.playback.browser_playback_method.canvas_status_used_as_evidence = true; },
    (value) => { value.playback.qualitative_review.verdict = "loading"; },
  ]) {
    const corrupted = structuredClone(fixture);
    mutate(corrupted);
    assert.throws(() => assertSchema2EvidenceClosure(corrupted));
  }
});

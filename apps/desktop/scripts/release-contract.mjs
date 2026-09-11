import { assertBridgeRuntimeMatches } from "./bridge-runtime-contract.mjs";

const SHA256 = /^[0-9a-f]{64}$/u;

// This is the release allowlist, not the historical-review corpus.
export const RELEASE_BUILT_IN_PET_IDS = Object.freeze(["pex", "von"]);

// These retired implementation modules are deliberately absent from the two-pet
// runtime even though PyInstaller collects the rest of pex_bridge for adapters.
export const RETIRED_BRIDGE_MODULES = Object.freeze([
  "pex_bridge.pets.hatch",
  "pex_bridge.pets.hatch_store",
  "pex_bridge.pets.imagegen",
]);

export const RETIRED_BRIDGE_DATA_FILES = Object.freeze(
  RETIRED_BRIDGE_MODULES.map((moduleName) => `${moduleName.replaceAll(".", "/")}.py`),
);

// A secondary Windows file-lock failure must not replace the verification error.
export function withSynchronousCleanup(operation, cleanup) {
  let result;
  let failed = false;
  let primaryError;
  try {
    result = operation();
  } catch (error) {
    failed = true;
    primaryError = error;
  }
  try {
    cleanup();
  } catch (cleanupError) {
    if (failed) {
      throw new AggregateError(
        [primaryError, cleanupError],
        "Verification and cleanup both failed",
        { cause: primaryError },
      );
    }
    throw cleanupError;
  }
  if (failed) throw primaryError;
  return result;
}

export const EXPECTED_SIDECAR_BINS = [
  "binaries/pex-cursor-hook",
  "binaries/pex-cursor-observe",
];

export const EXPECTED_BRIDGE_RESOURCES = {
  "binaries/pex-bridge-runtime/": "pex-bridge-runtime/",
};

export const EXPECTED_BUNDLE_ICONS = [
  "icons/32x32.png",
  "icons/128x128.png",
  "icons/128x128@2x.png",
  "icons/icon.icns",
  "icons/icon.ico",
];

export const EXPECTED_MAIN_PERMISSIONS = [
  "core:default",
  "core:window:allow-close",
  "core:window:allow-show",
  "core:window:allow-hide",
  "core:window:allow-set-position",
  "core:window:allow-outer-position",
  "core:window:allow-outer-size",
  "core:window:allow-set-background-color",
  "allow-bridge-token",
  "allow-bridge-recovery",
];

export const EXPECTED_PET_PERMISSIONS = [
  "core:default",
  "core:window:allow-start-dragging",
  "core:window:allow-show",
  "core:window:allow-hide",
  "core:window:allow-set-focus",
  "core:window:allow-set-ignore-cursor-events",
  "core:webview:allow-set-webview-background-color",
  "allow-bridge-token",
];

export const EXPECTED_FOCUS_PERMISSION = [
  "[[permission]]",
  'identifier = "allow-bridge-token"',
  'description = "Read the in-memory bearer for the desktop-owned, identity-proven local PEX bridge"',
  'commands.allow = ["bridge_token"]',
].join("\n");

export const EXPECTED_BRIDGE_RECOVERY_PERMISSION = [
  "[[permission]]",
  'identifier = "allow-bridge-recovery"',
  'description = "Read and retry the serialized desktop-owned PEX bridge bootstrap"',
  'commands.allow = ["bridge_bootstrap_status", "retry_bridge"]',
].join("\n");

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function exactKeys(value, expected) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && sameJson(Object.keys(value).sort(), [...expected].sort());
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
}

export function assertCanonicalRepoRelativePath(
  relativePath,
  expectedPrefix,
  label = "Manifest path",
  prefixMode = "exact",
) {
  if (
    typeof relativePath !== "string"
    || relativePath.length === 0
    || relativePath.includes("\\")
    || relativePath.includes("\0")
    || relativePath.startsWith("/")
    || /^[A-Za-z]:/u.test(relativePath)
  ) {
    throw new Error(`${label} must be a canonical repository-relative POSIX path`);
  }
  const parts = relativePath.split("/");
  if (parts.some((part) => part === "" || part === "." || part === "..")) {
    throw new Error(`${label} must not contain empty, dot, or parent path segments`);
  }
  if (prefixMode !== "exact" && prefixMode !== "prefix") {
    throw new TypeError(`Unknown manifest path match mode: ${prefixMode}`);
  }
  const isUnderPrefix = prefixMode === "prefix"
    ? relativePath.startsWith(expectedPrefix)
    : relativePath === expectedPrefix;
  if (!isUnderPrefix) throw new Error(`${label} must stay under ${expectedPrefix}`);
  return relativePath;
}

export function assertPublicReleaseEvidence(text, label = "Release evidence") {
  if (typeof text !== "string") throw new TypeError(`${label} must be text`);
  const privatePattern = /(?:file:\/\/\/|[A-Za-z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+|(?:^|\s)\/(?:[^\s/]+\/)+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:api[_-]?key|authorization|bearer|password)\b|\b(?:sk-[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{12,}|AKIA[A-Z0-9]{16})\b)/iu;
  if (privatePattern.test(text)) {
    throw new Error(`${label} contains a machine path or sensitive value`);
  }
  return text;
}

export function classifyGitReleaseInputs(relativeInputs, gitLsFilesVerboseZ) {
  if (!Array.isArray(relativeInputs) || typeof gitLsFilesVerboseZ !== "string") {
    throw new TypeError("Release inputs and Git index output are required");
  }
  const trackedFlags = new Map();
  for (const entry of gitLsFilesVerboseZ.split("\0").filter(Boolean)) {
    if (entry.length < 3 || entry[1] !== " ") throw new Error("Malformed git ls-files -v -z output");
    const path = entry.slice(2);
    if (trackedFlags.has(path)) throw new Error(`Duplicate Git index entry for ${path}`);
    trackedFlags.set(path, entry[0]);
  }
  return {
    trackedFlags,
    untrackedInputs: relativeInputs.filter((path) => !trackedFlags.has(path)),
    hiddenIndexInputs: relativeInputs.filter(
      (path) => trackedFlags.has(path) && trackedFlags.get(path) !== "H",
    ),
  };
}

export function tauriReleaseWiringMatches({
  packageJson,
  tauri,
  mainCapability,
  petCapability,
  cargoVersion,
  focusPermission,
  bridgeRecoveryPermission,
}) {
  const windows = tauri?.app?.windows ?? [];
  return packageJson?.scripts?.["prepare:sidecar"] === "node scripts/build-sidecar.mjs"
    && packageJson?.scripts?.["prepare:sidecar:release"] === "node scripts/build-sidecar.mjs --release-build"
    && packageJson?.scripts?.["preflight:release"] === "node scripts/build-sidecar.mjs --preflight-release"
    && packageJson?.scripts?.build === "tsc && vite build"
    && packageJson?.scripts?.tauri === "tauri"
    && tauri?.build?.beforeBuildCommand === "npm run prepare:sidecar:release && npm run build"
    && tauri?.build?.frontendDist === "../dist"
    && tauri?.bundle?.active === true
    && tauri?.bundle?.targets === "all"
    && sameJson(tauri?.bundle?.externalBin, EXPECTED_SIDECAR_BINS)
    && sameJson(tauri?.bundle?.icon, EXPECTED_BUNDLE_ICONS)
    && sameJson(tauri?.bundle?.resources, EXPECTED_BRIDGE_RESOURCES)
    && sameJson(windows.map((window) => window?.label), ["main", "pet"])
    && windows[0]?.visible === true
    && windows[1]?.visible === false
    && windows[1]?.url === "pet.html"
    && mainCapability?.identifier === "main"
    && sameJson(mainCapability?.windows, ["main"])
    && sameJson(mainCapability?.permissions, EXPECTED_MAIN_PERMISSIONS)
    && petCapability?.identifier === "pet"
    && sameJson(petCapability?.windows, ["pet"])
    && sameJson(petCapability?.permissions, EXPECTED_PET_PERMISSIONS)
    && focusPermission.trim().replaceAll("\r\n", "\n") === EXPECTED_FOCUS_PERMISSION
    && bridgeRecoveryPermission.trim().replaceAll("\r\n", "\n") === EXPECTED_BRIDGE_RECOVERY_PERMISSION
    && cargoVersion === packageJson?.version
    && tauri?.version === packageJson?.version;
}

export function sidecarBuildPolicy(args) {
  if (!Array.isArray(args) || args.some((arg) => typeof arg !== "string")) {
    throw new TypeError("Sidecar build arguments must be text");
  }
  const releaseBuild = args.includes("--release-build");
  const preflightRelease = args.includes("--preflight-release");
  const validatePetsOnly = args.includes("--validate-pets-only");
  if ([releaseBuild, preflightRelease, validatePetsOnly].filter(Boolean).length > 1) {
    throw new Error("Sidecar build modes are mutually exclusive");
  }
  return {
    releaseBuild,
    preflightRelease,
    validatePetsOnly,
    requireCleanWorktree: releaseBuild,
    allowCachedHelpers: !releaseBuild,
    pyinstallerCleanArgs: releaseBuild ? ["--clean"] : [],
  };
}

export function assertReleaseBuildSourceClean(required, gitStatus) {
  if (typeof required !== "boolean" || typeof gitStatus !== "string") {
    throw new TypeError("Release source cleanliness requires a boolean policy and Git status text");
  }
  if (required && gitStatus !== "") {
    throw new Error(
      "Release sidecars require a clean worktree before PyInstaller; review and resolve Git status first",
    );
  }
}

export function toolchainsMatch({ pins, active, uvLock }) {
  if (
    typeof pins?.node !== "string"
    || typeof pins?.python !== "string"
    || typeof pins?.rust !== "string"
    || typeof active?.node !== "string"
    || typeof active?.python !== "string"
    || typeof active?.rust !== "string"
    || typeof active?.pyinstaller !== "string"
    || typeof uvLock !== "string"
  ) return false;
  const pyinstallerBlock = new RegExp(
    `(?:^|\\n)\\[\\[package\\]\\]\\r?\\n(?:(?!\\n\\[\\[package\\]\\]).*\\r?\\n)*?name = "pyinstaller"\\r?\\nversion = "${escapeRegex(active.pyinstaller)}"(?:\\r?\\n|$)`,
    "u",
  );
  return pins.node === active.node
    && pins.python === active.python
    && active.rust.startsWith(`rustc ${pins.rust} `)
    && pyinstallerBlock.test(uvLock);
}

export function sidecarStampMatches({
  stamp,
  inputSha256,
  bridgeSha256,
  cursorHookSha256,
  cursorObserveSha256,
  bridgeRuntimeManifest,
}) {
  try {
    assertBridgeRuntimeMatches(stamp?.bridge_runtime_manifest, bridgeRuntimeManifest);
  } catch {
    return false;
  }
  return exactKeys(stamp, [
    "version",
    "input_sha256",
    "bridge_sha256",
    "cursor_hook_sha256",
    "cursor_observe_sha256",
    "bridge_runtime_manifest",
  ])
    && stamp.version === 4
    && [inputSha256, bridgeSha256, cursorHookSha256, cursorObserveSha256].every(
      (value) => typeof value === "string" && SHA256.test(value),
    )
    && stamp.input_sha256 === inputSha256
    && stamp.bridge_sha256 === bridgeSha256
    && stamp.cursor_hook_sha256 === cursorHookSha256
    && stamp.cursor_observe_sha256 === cursorObserveSha256;
}

export function assertFrozenBundleInventory(actual, expected) {
  const valid = exactKeys(actual, ["version", "pets"])
    && actual.version === expected?.version
    && Array.isArray(actual.pets)
    && Array.isArray(expected?.pets)
    && actual.pets.length === expected.pets.length
    && expected.pets.every((pet, index) => {
      const observed = actual.pets[index];
      return exactKeys(observed, ["id", "manifest_sha256", "spritesheet_sha256", "spritesheet_bytes"])
        && observed.id === pet.id
        && observed.manifest_sha256 === pet.manifest_sha256
        && observed.spritesheet_sha256 === pet.spritesheet_sha256
        && observed.spritesheet_bytes === pet.spritesheet_bytes;
    });
  if (!valid) {
    throw new Error(
      `Frozen bridge pet inventory mismatch: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    );
  }
}

export function parseFrozenBundleInventory(stdout) {
  if (typeof stdout !== "string" || stdout.trim().length === 0) {
    throw new Error("Frozen bridge emitted an invalid bundle inventory: empty output");
  }
  try {
    return JSON.parse(stdout.trim());
  } catch (error) {
    throw new Error(`Frozen bridge emitted an invalid bundle inventory: ${error.message}`);
  }
}

export function preflightSnapshotIsStable({
  releaseInputSha256Before,
  releaseInputSha256After,
  sourceInputSha256Before,
  sourceInputSha256After,
  statusBefore,
  statusAfter,
}) {
  return releaseInputSha256After === releaseInputSha256Before
    && sourceInputSha256After === sourceInputSha256Before
    && sameJson(statusAfter, statusBefore);
}

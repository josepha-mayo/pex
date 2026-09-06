import { createHash } from "node:crypto";

const SHA256 = /^[0-9a-f]{64}$/u;
const COMMIT = /^[0-9a-f]{40}$/u;
const BUNDLE_MARKER_PREFIX = Buffer.from("__TAURI_BUNDLE_TYPE_VAR_", "ascii");

function exactKeys(value, expected) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

export const PACKAGE_BINARIES = [
  "pex-desktop.exe",
  "pex-bridge.exe",
  "pex-cursor-hook.exe",
  "pex-cursor-observe.exe",
];

function uniqueMarkerOffset(value, label) {
  const first = value.indexOf(BUNDLE_MARKER_PREFIX);
  if (first < 0 || value.indexOf(BUNDLE_MARKER_PREFIX, first + 1) >= 0) {
    throw new Error(`${label} must contain exactly one Tauri bundle marker`);
  }
  return first;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function verifyDesktopBundleVariants(canonical, msi, nsis) {
  if (![canonical, msi, nsis].every(Buffer.isBuffer)) {
    throw new TypeError("Desktop bundle variants must be Buffers");
  }
  if (canonical.length !== msi.length || canonical.length !== nsis.length) {
    throw new Error("Desktop bundle variants must have identical lengths");
  }
  const markerOffset = uniqueMarkerOffset(canonical, "Canonical desktop");
  if (uniqueMarkerOffset(msi, "MSI desktop") !== markerOffset
    || uniqueMarkerOffset(nsis, "NSIS desktop") !== markerOffset) {
    throw new Error("Desktop bundle markers must have the same offset");
  }
  const valueOffset = markerOffset + BUNDLE_MARKER_PREFIX.length;
  if (canonical.subarray(valueOffset, valueOffset + 3).toString("ascii") !== "UNK"
    || msi.subarray(valueOffset, valueOffset + 3).toString("ascii") !== "MSI"
    || nsis.subarray(valueOffset, valueOffset + 4).toString("ascii") !== "NSIS") {
    throw new Error("Desktop binaries do not contain the expected UNK/MSI/NSIS bundle markers");
  }
  const width = 4;
  const normalized = [];
  for (const value of [canonical, msi, nsis]) {
    const copy = Buffer.from(value);
    canonical.copy(copy, valueOffset, valueOffset, valueOffset + width);
    normalized.push(sha256(copy));
  }
  if (new Set(normalized).size !== 1) {
    throw new Error("Desktop binaries differ outside the exact Tauri bundle marker");
  }
  return {
    offset: valueOffset,
    width,
    canonical_marker: "UNK",
    msi_marker: "MSI",
    nsis_marker: "NSIS",
    normalized_sha256: normalized[0],
  };
}

export function validateEmbeddedFiles(files) {
  if (!exactKeys(files, PACKAGE_BINARIES)) {
    throw new Error("Package must contain exactly the desktop and three named sidecars");
  }
  for (const name of PACKAGE_BINARIES) {
    const artifact = files[name];
    if (!exactKeys(artifact, ["bytes", "sha256"])
      || !Number.isSafeInteger(artifact.bytes)
      || artifact.bytes <= 0
      || !SHA256.test(artifact.sha256)) {
      throw new Error(`Invalid embedded artifact receipt for ${name}`);
    }
  }
  return files;
}

export function packageReceiptIsReady(receipt) {
  if (!exactKeys(receipt, [
    "schema", "stage", "source", "installers", "desktop_bundle_marker", "msi", "nsis", "release_ready", "blockers",
  ])) return false;
  if (receipt.schema !== "pex.package-receipt.v1" || receipt.stage !== "package") return false;
  if (!exactKeys(receipt.source, [
    "commit", "release_input_sha256", "sidecar_input_sha256", "preflight_sha256", "canonical_desktop_sha256",
  ])) return false;
  if (!COMMIT.test(receipt.source.commit)
    || !SHA256.test(receipt.source.release_input_sha256)
    || !SHA256.test(receipt.source.sidecar_input_sha256)
    || !SHA256.test(receipt.source.preflight_sha256)
    || !SHA256.test(receipt.source.canonical_desktop_sha256)) return false;
  if (!exactKeys(receipt.installers, ["msi_sha256", "nsis_sha256"])
    || !SHA256.test(receipt.installers.msi_sha256)
    || !SHA256.test(receipt.installers.nsis_sha256)) return false;
  try {
    validateEmbeddedFiles(receipt.msi?.embedded);
    validateEmbeddedFiles(receipt.nsis?.embedded);
  } catch {
    return false;
  }
  if (receipt.msi.status !== "verified" || receipt.nsis.status !== "verified") return false;
  if (receipt.msi.inventory_verified !== true || receipt.nsis.inventory_verified !== true) return false;
  const sidecars = PACKAGE_BINARIES.filter((name) => name !== "pex-desktop.exe");
  if (sidecars.some(
    (name) => receipt.msi.embedded[name].sha256 !== receipt.nsis.embedded[name].sha256,
  )) {
    return false;
  }
  if (!exactKeys(receipt.desktop_bundle_marker, [
    "offset", "width", "canonical_marker", "msi_marker", "nsis_marker", "normalized_sha256",
  ])
    || !Number.isSafeInteger(receipt.desktop_bundle_marker.offset)
    || receipt.desktop_bundle_marker.offset < 0
    || receipt.desktop_bundle_marker.width !== 4
    || receipt.desktop_bundle_marker.canonical_marker !== "UNK"
    || receipt.desktop_bundle_marker.msi_marker !== "MSI"
    || receipt.desktop_bundle_marker.nsis_marker !== "NSIS"
    || !SHA256.test(receipt.desktop_bundle_marker.normalized_sha256)
    || receipt.desktop_bundle_marker.normalized_sha256 !== receipt.source.canonical_desktop_sha256) return false;
  return receipt.release_ready === true && Array.isArray(receipt.blockers) && receipt.blockers.length === 0;
}

export function findUniquePackagedFiles(relativeFiles) {
  if (!Array.isArray(relativeFiles) || relativeFiles.some((path) => typeof path !== "string")) {
    throw new TypeError("Extracted package paths must be text");
  }
  const result = {};
  for (const expected of PACKAGE_BINARIES) {
    const matches = relativeFiles.filter(
      (path) => path.replaceAll("\\", "/").split("/").at(-1)?.toLowerCase() === expected,
    );
    if (matches.length !== 1) throw new Error(`Expected exactly one ${expected}, found ${matches.length}`);
    result[expected] = matches[0];
  }
  return result;
}

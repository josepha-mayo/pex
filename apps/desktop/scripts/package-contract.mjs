const SHA256 = /^[0-9a-f]{64}$/u;
const COMMIT = /^[0-9a-f]{40}$/u;

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
    "schema", "stage", "source", "installers", "msi", "nsis", "release_ready", "blockers",
  ])) return false;
  if (receipt.schema !== "pex.package-receipt.v1" || receipt.stage !== "package") return false;
  if (!exactKeys(receipt.source, [
    "commit", "release_input_sha256", "sidecar_input_sha256", "preflight_sha256",
  ])) return false;
  if (!COMMIT.test(receipt.source.commit)
    || !SHA256.test(receipt.source.release_input_sha256)
    || !SHA256.test(receipt.source.sidecar_input_sha256)
    || !SHA256.test(receipt.source.preflight_sha256)) return false;
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
  if (PACKAGE_BINARIES.some(
    (name) => receipt.msi.embedded[name].sha256 !== receipt.nsis.embedded[name].sha256,
  )) {
    return false;
  }
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

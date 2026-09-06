import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { parseFrozenBundleInventory } from "./release-contract.mjs";
import {
  findUniquePackagedFiles,
  packageReceiptIsReady,
  verifyDesktopBundleVariants,
} from "./package-contract.mjs";

const desktop = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(desktop, "..", "..");
const target = join(desktop, "src-tauri", "target", "release", "bundle");
const receiptArg = process.argv.indexOf("--receipt");
if (receiptArg >= 0 && (!process.argv[receiptArg + 1] || process.argv[receiptArg + 1].startsWith("--"))) {
  throw new Error("--receipt requires an output path");
}
const receiptPath = receiptArg >= 0 ? resolve(process.argv[receiptArg + 1] ?? "") : join(repo, "build", "pex-package-receipt.json");

function sha256Buffer(value) {
  return createHash("sha256").update(value).digest("hex");
}
function sha256File(path) { return sha256Buffer(readFileSync(path)); }
function listFiles(root) {
  const found = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Extracted package contains a symbolic link: ${entry.name}`);
    if (entry.isDirectory()) found.push(...listFiles(path));
    else if (entry.isFile()) found.push(path);
  }
  return found;
}
function uniqueInstaller(directory, suffix) {
  const matches = existsSync(directory)
    ? readdirSync(directory).filter((name) => name.toLowerCase().endsWith(suffix)).map((name) => join(directory, name))
    : [];
  if (matches.length !== 1) throw new Error(`Expected exactly one ${suffix} installer, found ${matches.length}`);
  return matches[0];
}
function commandExists(command) {
  const probe = spawnSync(command, ["--help"], { stdio: "ignore", windowsHide: true });
  return probe.status === 0 || probe.status === 1 || probe.status === 2;
}
function extractedReceipt(root) {
  const paths = listFiles(root);
  const mapped = findUniquePackagedFiles(paths.map((path) => relative(root, path)));
  return Object.fromEntries(Object.entries(mapped).map(([name, path]) => {
    const absolute = join(root, path);
    return [name, { bytes: statSync(absolute).size, sha256: sha256File(absolute) }];
  }));
}
function verifyInventory(root) {
  const paths = listFiles(root);
  const mapped = findUniquePackagedFiles(paths.map((path) => relative(root, path)));
  const bridge = join(root, mapped["pex-bridge.exe"]);
  const result = execFileSync(bridge, ["--verify-bundle"], {
    encoding: "utf8", windowsHide: true, timeout: 120_000, maxBuffer: 16 * 1024 * 1024,
  });
  const inventory = parseFrozenBundleInventory(result);
  const expected = ["pex", "ledger", "mesh", "nudge", "drift", "quiet", "ember", "von"];
  if (inventory.version !== 1
    || inventory.pets?.length !== expected.length
    || inventory.pets.some((pet, index) => pet.id !== expected[index])) {
    throw new Error("Extracted bridge did not report the exact ordered eight-pet inventory");
  }
  return true;
}
function hashJson(value) { return sha256Buffer(Buffer.from(`${JSON.stringify(value)}\n`, "utf8")); }

const blockers = [];
let preflight;
try {
  preflight = JSON.parse(execFileSync(process.execPath, [join(desktop, "scripts", "build-sidecar.mjs"), "--preflight-release"], {
    cwd: repo, encoding: "utf8", windowsHide: true, timeout: 180_000, maxBuffer: 32 * 1024 * 1024,
  }));
} catch (error) {
  process.stderr.write(error.stdout ?? "");
  throw new Error("Source release preflight must pass before package verification");
}
if (preflight.source_ready !== true || preflight.blockers?.length !== 0) throw new Error("Source release preflight is not ready");
const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: repo, encoding: "utf8" }).trim();
const statusBefore = execFileSync("git", ["status", "--porcelain=v1", "-z", "--untracked-files=all"], { cwd: repo, encoding: "utf8" });
if (statusBefore !== "") throw new Error("Package verification requires a clean worktree");

const msiPath = uniqueInstaller(join(target, "msi"), ".msi");
const nsisPath = uniqueInstaller(join(target, "nsis"), ".exe");
const installerHashes = { msi_sha256: sha256File(msiPath), nsis_sha256: sha256File(nsisPath) };
const work = mkdtempSync(join(tmpdir(), "pex-package-verify-"));
let msi = { status: "failed", embedded: null, inventory_verified: false };
let nsis = { status: "unsupported", embedded: null, inventory_verified: false };
let msiDesktop = null;
let nsisDesktop = null;
let desktopBundleMarker = null;
const canonicalDesktopPath = join(desktop, "src-tauri", "target", "release", "pex-desktop.exe");
if (!existsSync(canonicalDesktopPath)) throw new Error("Canonical release desktop executable is missing");
const canonicalDesktop = readFileSync(canonicalDesktopPath);
try {
  if (process.platform !== "win32") throw new Error("MSI administrative extraction requires Windows");
  const msiRoot = join(work, "msi");
  const extraction = spawnSync("msiexec.exe", ["/a", msiPath, "/qn", `TARGETDIR=${msiRoot}`], {
    windowsHide: true, timeout: 180_000, encoding: "utf8",
  });
  if (extraction.error || extraction.status !== 0) throw new Error(`MSI extraction failed with status ${extraction.status}`);
  msi = { status: "verified", embedded: extractedReceipt(msiRoot), inventory_verified: verifyInventory(msiRoot) };
  const mapped = findUniquePackagedFiles(listFiles(msiRoot).map((path) => relative(msiRoot, path)));
  msiDesktop = readFileSync(join(msiRoot, mapped["pex-desktop.exe"]));
} catch (error) {
  blockers.push({ code: "msi_verification_failed", detail: error.message });
}
try {
  const extractor = ["7zz", "7z"].find(commandExists);
  if (!extractor) {
    blockers.push({ code: "nsis_extractor_unavailable", detail: "No deterministic 7-Zip extractor is available" });
  } else {
    const nsisRoot = join(work, "nsis");
    const extractionResult = spawnSync(extractor, ["x", "-y", `-o${nsisRoot}`, nsisPath], {
      windowsHide: true, timeout: 180_000, encoding: "utf8",
    });
    if (extractionResult.error || extractionResult.status !== 0) {
      blockers.push({ code: "nsis_extraction_failed", detail: `Deterministic NSIS extraction failed with status ${extractionResult.status}` });
      nsis = { status: "failed", embedded: null, inventory_verified: false };
    } else {
      nsis = { status: "verified", embedded: extractedReceipt(nsisRoot), inventory_verified: verifyInventory(nsisRoot) };
      const mapped = findUniquePackagedFiles(listFiles(nsisRoot).map((path) => relative(nsisRoot, path)));
      nsisDesktop = readFileSync(join(nsisRoot, mapped["pex-desktop.exe"]));
    }
  }
} catch (error) {
  blockers.push({ code: "nsis_verification_failed", detail: error.message });
  nsis = { status: "failed", embedded: null, inventory_verified: false };
} finally {
  if (msiDesktop && nsisDesktop) {
    try {
      desktopBundleMarker = verifyDesktopBundleVariants(canonicalDesktop, msiDesktop, nsisDesktop);
    } catch (error) {
      blockers.push({ code: "desktop_bundle_mismatch", detail: error.message });
    }
  }
  rmSync(work, { recursive: true, force: true });
}

const statusAfter = execFileSync("git", ["status", "--porcelain=v1", "-z", "--untracked-files=all"], { cwd: repo, encoding: "utf8" });
if (statusAfter !== statusBefore || sha256File(msiPath) !== installerHashes.msi_sha256 || sha256File(nsisPath) !== installerHashes.nsis_sha256) {
  blockers.push({ code: "package_toctou", detail: "Source state or installer bytes changed during package verification" });
}
const sourceSidecars = {
  "pex-bridge.exe": preflight.sidecars.bridge_sha256,
  "pex-cursor-hook.exe": preflight.sidecars.cursor_hook_sha256,
  "pex-cursor-observe.exe": preflight.sidecars.cursor_observe_sha256,
};
for (const [name, expected] of Object.entries(sourceSidecars)) {
  if (msi.embedded?.[name]?.sha256 !== expected) blockers.push({ code: "msi_sidecar_mismatch", detail: `${name} does not match source preflight` });
  if (nsis.status === "verified" && nsis.embedded?.[name]?.sha256 !== expected) blockers.push({ code: "nsis_sidecar_mismatch", detail: `${name} does not match source preflight` });
}
const receipt = {
  schema: "pex.package-receipt.v1",
  stage: "package",
  source: {
    commit,
    release_input_sha256: preflight.git.release_input_sha256,
    sidecar_input_sha256: preflight.sidecars.input_sha256,
    preflight_sha256: hashJson(preflight),
    canonical_desktop_sha256: sha256Buffer(canonicalDesktop),
  },
  installers: installerHashes,
  desktop_bundle_marker: desktopBundleMarker,
  msi,
  nsis,
  release_ready: false,
  blockers,
};
receipt.release_ready = blockers.length === 0 && msi.status === "verified" && nsis.status === "verified";
if (receipt.release_ready && !packageReceiptIsReady(receipt)) throw new Error("Internal package receipt validation failed");
mkdirSync(dirname(receiptPath), { recursive: true });
writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
process.exit(receipt.release_ready ? 0 : 2);

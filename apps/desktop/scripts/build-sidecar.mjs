import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  closeSync,
  cpSync,
  existsSync,
  mkdirSync,
  lstatSync,
  mkdtempSync,
  openSync,
  readFileSync,
  readSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { delimiter, dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertCanonicalRepoRelativePath,
  assertFrozenBundleInventory,
  assertSchema2EvidenceClosure,
  classifyGitReleaseInputs,
  parseFrozenBundleInventory,
  preflightSnapshotIsStable,
  sidecarStampMatches,
  tauriReleaseWiringMatches,
  toolchainsMatch,
} from "./release-contract.mjs";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repo = resolve(scriptDir, "../../..");
const repoReal = realpathSync.native(repo);
const desktop = resolve(scriptDir, "..");
const tauriDir = join(desktop, "src-tauri");
const binaries = join(tauriDir, "binaries");
let triple;
try {
  triple = execFileSync("rustc", ["--print", "host-tuple"], {
    cwd: repo,
    encoding: "utf8",
  }).trim();
  if (!triple) throw new Error("rustc did not report a host target triple");
} catch (error) {
  if (process.argv.includes("--preflight-release")) {
    process.stdout.write(`${JSON.stringify({
      schema: "pex.release-preflight.v1",
      stage: "source",
      source_ready: false,
      release_ready: false,
      blockers: [{ code: "rust_toolchain_unavailable", detail: error.message }],
    }, null, 2)}\n`);
    process.exit(2);
  }
  throw error;
}

const extension = process.platform === "win32" ? ".exe" : "";
const bridgeTarget = join(binaries, `pex-bridge-${triple}${extension}`);
const cursorHookTarget = join(binaries, `pex-cursor-hook-${triple}${extension}`);
const cursorObserveTarget = join(binaries, `pex-cursor-observe-${triple}${extension}`);
const buildStamp = join(binaries, `pex-sidecars-${triple}.json`);
const builtInPets = ["pex", "ledger", "mesh", "nudge", "drift", "quiet", "ember", "von"];
const petsRoot = join(repo, "apps", "desktop", "src", "pets");
const petReleaseManifest = join(petsRoot, "release-manifest.json");
const fleetAuditManifest = join(petsRoot, "_audit", "release", "manifest.json");
const currentEvidenceRoot = join(petsRoot, "_audit", "release", "current-20260831");
const directPlaybackReceipt = join(currentEvidenceRoot, "direct-playback-qa.json");
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
const venvPython = process.platform === "win32"
  ? join(repo, ".venv", "Scripts", "python.exe")
  : join(repo, ".venv", "bin", "python");
const sourceRoots = [
  join(repo, "packages", "protocol", "src"),
  join(repo, "services", "bridge", "src"),
  join(repo, "services", "supervisor", "src"),
  join(repo, "apps", "desktop", "src", "pets"),
];
const sourceFiles = [
  fileURLToPath(import.meta.url),
  join(scriptDir, "release-contract.mjs"),
  join(repo, ".node-version"),
  join(repo, ".python-version"),
  join(repo, "pyproject.toml"),
  join(repo, "rust-toolchain.toml"),
  join(repo, "uv.lock"),
  join(repo, "packages", "protocol", "pyproject.toml"),
  join(repo, "services", "bridge", "pyproject.toml"),
  join(repo, "services", "supervisor", "pyproject.toml"),
  join(repo, "apps", "desktop", "package.json"),
  join(repo, "apps", "desktop", "package-lock.json"),
  join(repo, "integrations", "cursor-hook", "pex_cursor_hook.py"),
  join(repo, "integrations", "cursor-hook", "pex_cursor_observe.py"),
];
const ignoredSourceEntries = new Set(["_hatch", "_audit", "__pycache__"]);
const validatedReleaseEvidence = new Map();

function compareCanonicalPaths(left, right) {
  const leftPath = relative(repo, left).replaceAll("\\", "/");
  const rightPath = relative(repo, right).replaceAll("\\", "/");
  return leftPath < rightPath ? -1 : leftPath > rightPath ? 1 : 0;
}

function assertInsideRepo(path, label) {
  const resolvedPath = resolve(path);
  const fromRepo = relative(repo, resolvedPath);
  if (!fromRepo || fromRepo.startsWith("..") || isAbsolute(fromRepo)) {
    throw new Error(`${label} must be a child of the repository: ${resolvedPath}`);
  }
  return resolvedPath;
}

function assertSafeRepoPath(path, label) {
  const resolvedPath = assertInsideRepo(path, label);
  const parts = relative(repo, resolvedPath).split(/[\\/]+/).filter(Boolean);
  let current = repo;
  for (let index = 0; index < parts.length; index += 1) {
    current = join(current, parts[index]);
    if (!existsSync(current)) break;
    const entry = lstatSync(current);
    if (entry.isSymbolicLink()) {
      throw new Error(`${label} must not traverse a symbolic link or junction: ${current}`);
    }
    const real = realpathSync.native(current);
    const fromRepo = relative(repoReal, real);
    if (fromRepo.startsWith("..") || isAbsolute(fromRepo)) {
      throw new Error(`${label} resolves outside the repository: ${current}`);
    }
    if (index < parts.length - 1 && !entry.isDirectory()) {
      throw new Error(`${label} has a non-directory parent component: ${current}`);
    }
  }
  return resolvedPath;
}

function assertSafeDirectory(path, label) {
  const resolvedPath = assertSafeRepoPath(path, label);
  if (existsSync(resolvedPath) && !lstatSync(resolvedPath).isDirectory()) {
    throw new Error(`${label} must be a directory: ${resolvedPath}`);
  }
  return resolvedPath;
}

function assertSafeRegularFile(path, label) {
  const resolvedPath = assertSafeRepoPath(path, label);
  if (!existsSync(resolvedPath)) throw new Error(`${label} is missing: ${resolvedPath}`);
  const entry = lstatSync(resolvedPath);
  if (!entry.isFile()) throw new Error(`${label} must be a regular file: ${resolvedPath}`);
  return entry;
}

function resolveManifestFile(relativePath, expectedPrefix, label, prefixMode = "prefix") {
  assertCanonicalRepoRelativePath(relativePath, expectedPrefix, label, prefixMode);
  const parts = relativePath.split("/");
  const resolvedPath = join(petsRoot, ...parts);
  assertSafeRegularFile(resolvedPath, label);
  const actualRelativePath = relative(petsRoot, realpathSync.native(resolvedPath)).replaceAll("\\", "/");
  if (actualRelativePath !== relativePath) {
    throw new Error(`${label} must use the exact on-disk path casing`);
  }
  return resolvedPath;
}

function rememberReleaseEvidence(path, role) {
  assertSafeRegularFile(path, role);
  const canonicalPath = relative(repo, path).replaceAll("\\", "/");
  const expectedPrefix = "apps/desktop/src/pets/_audit/release/";
  if (!canonicalPath.startsWith(expectedPrefix)) {
    throw new Error(`${role} is outside the release evidence namespace: ${canonicalPath}`);
  }
  const identity = fileIdentity(path);
  const existing = validatedReleaseEvidence.get(identity);
  if (existing && existing.path !== canonicalPath) {
    throw new Error(`${role} aliases ${existing.path} as ${canonicalPath}`);
  }
  if (existing) existing.roles.add(role);
  else validatedReleaseEvidence.set(identity, { path: canonicalPath, file: path, roles: new Set([role]) });
  return path;
}

function validateHashedArtifact(artifact, expectedPrefix, label, maxBytes = 8 * 1024 * 1024) {
  if (
    typeof artifact?.path !== "string"
    || typeof artifact?.sha256 !== "string"
    || !/^[0-9a-f]{64}$/u.test(artifact.sha256)
  ) {
    throw new Error(`${label} reference is invalid`);
  }
  const prefixMode = expectedPrefix.endsWith("/") ? "prefix" : "exact";
  const artifactPath = resolveManifestFile(artifact.path, expectedPrefix, label, prefixMode);
  const size = lstatSync(artifactPath).size;
  if (size > maxBytes) throw new Error(`${label} exceeds ${maxBytes} bytes`);
  if (artifact.bytes !== undefined && artifact.bytes !== size) {
    throw new Error(`${label} byte length mismatch`);
  }
  if (sha256File(artifactPath) !== artifact.sha256) throw new Error(`${label} hash mismatch`);
  return artifactPath;
}

function fileIdentity(path) {
  const identity = realpathSync.native(path);
  return process.platform === "win32" ? identity.toLocaleLowerCase("en-US") : identity;
}

function removeSafeRegularFile(path, label) {
  assertSafeRepoPath(path, label);
  if (!existsSync(path)) return;
  assertSafeRegularFile(path, label);
  rmSync(path, { force: true });
}

function removeSafeDirectory(path, label) {
  const resolvedPath = assertSafeDirectory(path, label);
  if (!existsSync(resolvedPath)) return;
  rmSync(resolvedPath, { recursive: true, force: true });
}

function collectSourceFiles(path, collected) {
  const safePath = assertSafeRepoPath(path, "Sidecar input");
  if (!existsSync(safePath)) throw new Error(`Required sidecar input is missing: ${safePath}`);
  const entry = lstatSync(safePath);
  if (!entry.isDirectory()) {
    if (!entry.isFile()) throw new Error(`Sidecar input must be a regular file: ${safePath}`);
    if (!safePath.endsWith(".pyc")) collected.push(safePath);
    return;
  }
  for (const child of readdirSync(safePath).sort()) {
    if (ignoredSourceEntries.has(child) || child.endsWith(".pyc")) continue;
    collectSourceFiles(join(safePath, child), collected);
  }
}

function updateHashFromFile(hash, path) {
  const handle = openSync(path, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let count = 0;
    while ((count = readSync(handle, buffer, 0, buffer.length, null)) > 0) {
      hash.update(buffer.subarray(0, count));
    }
  } finally {
    closeSync(handle);
  }
}

function sha256File(path) {
  const hash = createHash("sha256");
  updateHashFromFile(hash, path);
  return hash.digest("hex");
}

function sourceInputFiles() {
  const inputs = [];
  for (const path of [...sourceRoots, ...sourceFiles]) collectSourceFiles(path, inputs);
  return [...new Set(inputs)].sort(compareCanonicalPaths);
}

function sourceFingerprint() {
  const unique = sourceInputFiles();
  const hash = createHash("sha256");
  for (const path of unique) {
    const key = relative(repo, path).replaceAll("\\", "/");
    hash.update(key, "utf8");
    hash.update("\0");
    updateHashFromFile(hash, path);
    hash.update("\0");
  }
  return hash.digest("hex");
}

function validateBuiltInPet(id) {
  const source = assertSafeDirectory(
    join(repo, "apps", "desktop", "src", "pets", id),
    `Built-in pet directory for ${id}`,
  );
  const manifestPath = join(source, "pet.json");
  const sheetPath = join(source, "spritesheet.webp");
  if (!existsSync(manifestPath) || !existsSync(sheetPath)) {
    throw new Error(`Required built-in pet assets are missing for ${id}: ${source}`);
  }
  const manifestStat = lstatSync(manifestPath);
  const sheetStat = lstatSync(sheetPath);
  if (
    manifestStat.isSymbolicLink()
    || sheetStat.isSymbolicLink()
    || !manifestStat.isFile()
    || !sheetStat.isFile()
  ) {
    throw new Error(`Built-in pet assets must be regular files for ${id}`);
  }
  if (manifestStat.size < 1 || manifestStat.size > 65_536) {
    throw new Error(`Built-in pet manifest must be between 1 byte and 64 KiB for ${id}`);
  }
  if (sheetStat.size < 1 || sheetStat.size > 16 * 1024 * 1024) {
    throw new Error(`Built-in pet spritesheet must be between 1 byte and 16 MiB for ${id}`);
  }
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8").replace(/^\uFEFF/, ""));
  } catch (error) {
    throw new Error(`Built-in pet manifest is invalid for ${id}: ${error.message}`);
  }
  if (
    manifest.id !== id ||
    manifest.spriteVersionNumber !== 2 ||
    manifest.spritesheetPath !== "spritesheet.webp"
  ) {
    throw new Error(`Built-in pet ${id} must be an exact Codex v2 manifest`);
  }
  return source;
}

function validateBuiltInPetMedia(petSources) {
  if (!existsSync(venvPython)) {
    throw new Error("Python environment is missing. Run `uv sync --dev` from the repository root.");
  }
  const validator = String.raw`
import sys
from pathlib import Path
from pex_bridge.pets import import_codex_pet

for value in sys.argv[1:]:
    root = Path(value)
    imported = import_codex_pet(root)
    expected_id = f"import:{root.name}"
    if imported.id != expected_id:
        raise SystemExit(f"built-in pet id mismatch: expected {expected_id}, got {imported.id}")
`;
  const pythonPath = [
    join(repo, "services", "bridge", "src"),
    join(repo, "services", "supervisor", "src"),
    join(repo, "packages", "protocol", "src"),
    process.env.PYTHONPATH,
  ].filter(Boolean).join(delimiter);
  execFileSync(venvPython, ["-c", validator, ...petSources.values()], {
    cwd: repo,
    env: { ...process.env, PYTHONPATH: pythonPath },
    stdio: "inherit",
  });
}

function validatePetReleaseEvidence(petSources) {
  validatedReleaseEvidence.clear();
  assertSafeRegularFile(petReleaseManifest, "Pet release manifest");
  if (lstatSync(petReleaseManifest).size > 128 * 1024) {
    throw new Error("Pet release manifest exceeds 128 KiB");
  }
  let release;
  try {
    release = JSON.parse(readFileSync(petReleaseManifest, "utf8"));
  } catch (error) {
    throw new Error(`Pet release manifest is invalid: ${error.message}`);
  }
  if (
    release?.schema_version !== 2
    || JSON.stringify(release?.built_in_pet_ids) !== JSON.stringify(builtInPets)
    || !Array.isArray(release?.pets)
    || release.pets.length !== builtInPets.length
  ) {
    throw new Error("Pet release manifest must describe the exact ordered eight-pet fleet");
  }

  for (let index = 0; index < builtInPets.length; index += 1) {
    const id = builtInPets[index];
    const entry = release.pets[index];
    const source = petSources.get(id);
    if (!source) throw new Error(`Missing validated source for ${id}`);
    const expectedReceipt = `_audit/release/${id}.json`;
    const receiptPath = join(petsRoot, "_audit", "release", `${id}.json`);
    assertSafeRegularFile(receiptPath, `Release receipt for ${id}`);
    rememberReleaseEvidence(receiptPath, `Release receipt for ${id}`);
    if (lstatSync(receiptPath).size > 128 * 1024) {
      throw new Error(`Release receipt exceeds 128 KiB for ${id}`);
    }
    const manifestSha = sha256File(join(source, "pet.json"));
    const spritesheetSha = sha256File(join(source, "spritesheet.webp"));
    const receiptSha = sha256File(receiptPath);
    if (
      entry?.id !== id
      || entry?.manifest_sha256 !== manifestSha
      || entry?.spritesheet_sha256 !== spritesheetSha
      || entry?.receipt !== expectedReceipt
      || entry?.receipt_sha256 !== receiptSha
    ) {
      throw new Error(`Pet release manifest hash or receipt mismatch for ${id}`);
    }

    let receipt;
    try {
      receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
    } catch (error) {
      throw new Error(`Pet release receipt is invalid for ${id}: ${error.message}`);
    }
    const receiptArtifactPaths = new Set();
    const validateEvidenceArtifact = (artifact, label) => {
      if (
        typeof artifact?.path !== "string"
        || typeof artifact?.sha256 !== "string"
        || !/^[0-9a-f]{64}$/u.test(artifact.sha256)
      ) {
        throw new Error(`${label} reference is invalid for ${id}`);
      }
      if (!artifact.path.startsWith(`_audit/release/evidence/${id}-`)) {
        throw new Error(`${label} must use the ${id} evidence namespace`);
      }
      const evidencePath = resolveManifestFile(
        artifact.path,
        `_audit/release/evidence/${id}-`,
        `${label} for ${id}`,
      );
      const evidenceIdentity = fileIdentity(evidencePath);
      if (receiptArtifactPaths.has(evidenceIdentity)) {
        throw new Error(`${label} reuses evidence file ${artifact.path} for ${id}`);
      }
      receiptArtifactPaths.add(evidenceIdentity);
      if (lstatSync(evidencePath).size > 128 * 1024) {
        throw new Error(`${label} exceeds 128 KiB for ${id}`);
      }
      if (sha256File(evidencePath) !== artifact.sha256) {
        throw new Error(`${label} hash mismatch for ${id}`);
      }
      return rememberReleaseEvidence(evidencePath, `${label} for ${id}`);
    };
    const validateEmbeddedArtifact = (artifact, expectedPrefix, label) => {
      if (
        typeof artifact?.path !== "string"
        || !artifact.path.startsWith(expectedPrefix)
        || typeof artifact?.sha256 !== "string"
        || !/^[0-9a-f]{64}$/u.test(artifact.sha256)
      ) {
        throw new Error(`${label} reference is invalid for ${id}`);
      }
      const artifactPath = resolveManifestFile(
        artifact.path,
        expectedPrefix,
        `${label} for ${id}`,
      );
      if (lstatSync(artifactPath).size > 8 * 1024 * 1024) {
        throw new Error(`${label} exceeds 8 MiB for ${id}`);
      }
      if (sha256File(artifactPath) !== artifact.sha256) {
        throw new Error(`${label} hash mismatch for ${id}`);
      }
      return rememberReleaseEvidence(artifactPath, `${label} for ${id}`);
    };
    const parseEvidenceJson = (evidencePath, label) => {
      try {
        return JSON.parse(readFileSync(evidencePath, "utf8"));
      } catch (error) {
        throw new Error(`${label} is invalid JSON for ${id}: ${error.message}`);
      }
    };
    const reviewers = receipt?.blind_review?.reviewers;
    const reviewerIds = Array.isArray(reviewers)
      ? reviewers.map((reviewer) => reviewer?.reviewer_id)
      : [];
    const reviewersValid = reviewerIds.length === 3
      && new Set(reviewerIds).size === 3
      && reviewers.every(
        (reviewer) =>
          typeof reviewer?.reviewer_id === "string"
          && reviewer.reviewer_id.length > 0
          && reviewer.isolation_attested === true
          && typeof reviewer.verdict_path === "string"
          && reviewer.verdict_path.startsWith(`_audit/release/evidence/${id}-blind-`)
          && typeof reviewer.verdict_sha256 === "string"
          && /^[0-9a-f]{64}$/u.test(reviewer.verdict_sha256),
      );
    if (
      receipt?.schema_version !== 1
      || receipt?.pet_id !== id
      || receipt?.status !== "approved"
      || receipt?.candidate_sha256 !== spritesheetSha
      || receipt?.shipped_sha256 !== spritesheetSha
      || receipt?.structural_validation?.ok !== true
      || receipt?.structural_validation?.validated_asset_sha256 !== spritesheetSha
      || receipt?.blind_review?.ok !== true
      || !reviewersValid
      || receipt?.final_visual?.verdict !== "pass"
      || typeof receipt?.final_visual?.reviewer_id !== "string"
      || !receipt.final_visual.reviewer_id
      || receipt?.final_visual?.reviewed_asset_sha256 !== spritesheetSha
      || receipt?.promotion?.decided_by !== "parent"
      || receipt?.promotion?.post_copy_hash_verified !== true
      || receipt?.promotion?.runtime_import !== "pass"
    ) {
      throw new Error(`Pet release receipt is incomplete or not hash-bound for ${id}`);
    }
    const structuralEvidencePath = validateEvidenceArtifact(
      receipt.structural_validation.evidence,
      "Structural validation evidence",
    );
    for (const reviewer of reviewers) {
      const reviewerEvidencePath = validateEvidenceArtifact(
        { path: reviewer.verdict_path, sha256: reviewer.verdict_sha256 },
        "Blind reviewer evidence",
      );
      const reviewerEvidence = parseEvidenceJson(reviewerEvidencePath, "Blind reviewer evidence");
      const expectedPairNames = [
        ...Array.from({ length: 7 }, (_, pairIndex) => `horizontal-${pairIndex + 1}`),
        ...Array.from({ length: 7 }, (_, pairIndex) => `vertical-${pairIndex + 1}`),
      ];
      if (
        !Array.isArray(reviewerEvidence?.pairs)
        || reviewerEvidence.pairs.length !== 14
        || JSON.stringify(reviewerEvidence.pairs.map((pair) => pair?.pair))
          !== JSON.stringify(expectedPairNames)
        || reviewerEvidence.pairs.some(
          (pair) => typeof pair?.pair !== "string"
            || !["screen-left", "screen-right", "up", "down", "ambiguous"].includes(pair?.A)
            || !["screen-left", "screen-right", "up", "down", "ambiguous"].includes(pair?.B),
        )
      ) {
        throw new Error(`Blind reviewer evidence is semantically incomplete for ${id}`);
      }
    }
    const blindValidationPath = validateEvidenceArtifact(
      receipt.blind_review.validation,
      "Blind validation evidence",
    );
    const finalVisualPath = validateEvidenceArtifact(
      receipt.final_visual.evidence,
      "Final visual evidence",
    );
    const promotionPath = validateEvidenceArtifact(
      receipt.promotion.evidence,
      "Promotion evidence",
    );
    const structuralEvidence = parseEvidenceJson(
      structuralEvidencePath,
      "Structural validation evidence",
    );
    if (structuralEvidence?.ok !== true) {
      throw new Error(`Structural validation evidence is not green for ${id}`);
    }
    const blindValidation = parseEvidenceJson(blindValidationPath, "Blind validation evidence");
    if (
      blindValidation?.ok !== true
      || !Array.isArray(blindValidation?.pairs)
      || blindValidation.pairs.length !== 14
      || JSON.stringify(blindValidation.pairs.map((pair) => pair?.pair))
        !== JSON.stringify([
          ...Array.from({ length: 7 }, (_, pairIndex) => `horizontal-${pairIndex + 1}`),
          ...Array.from({ length: 7 }, (_, pairIndex) => `vertical-${pairIndex + 1}`),
        ])
      || blindValidation.pairs.some(
        (pair) => typeof pair?.pair !== "string"
          || !["horizontal", "vertical"].includes(pair?.axis)
          || !["hard", "review"].includes(pair?.gate)
          || typeof pair?.A?.pass !== "boolean"
          || typeof pair?.B?.pass !== "boolean"
          || (pair?.gate === "hard" && (pair?.A?.pass !== true || pair?.B?.pass !== true)),
      )
    ) {
      throw new Error(`Blind validation evidence is not green for ${id}`);
    }
    const finalVisualEvidence = parseEvidenceJson(
      finalVisualPath,
      "Final visual evidence",
    );
    const promotionEvidence = parseEvidenceJson(promotionPath, "Promotion evidence");
    const requiredFrames = [6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8];
    if (
      structuralEvidence?.pet_id !== id
      || structuralEvidence?.validated_asset_sha256 !== spritesheetSha
      || structuralEvidence?.format !== "WEBP"
      || structuralEvidence?.mode !== "RGBA"
      || structuralEvidence?.width !== 1536
      || structuralEvidence?.height !== 2288
      || structuralEvidence?.columns !== 8
      || structuralEvidence?.rows !== 11
      || JSON.stringify(structuralEvidence?.required_frames_by_row)
        !== JSON.stringify(requiredFrames)
      || structuralEvidence?.runtime_used_cells !== 73
      || structuralEvidence?.unused_cells !== 15
      || structuralEvidence?.all_runtime_cells_nonempty !== true
      || structuralEvidence?.all_unused_cells_fully_transparent !== true
    ) {
      throw new Error(`Structural validation evidence is not contract-bound for ${id}`);
    }
    const validationReportPath = validateEmbeddedArtifact(
      structuralEvidence.validation_report,
      "_audit/release/evidence/runtime-contract-validation-",
      "Runtime contract validation report",
    );
    const validationReport = parseEvidenceJson(
      validationReportPath,
      "Runtime contract validation report",
    );
    const assetPath = `apps/desktop/src/pets/${id}/spritesheet.webp`;
    const validationResult = Array.isArray(validationReport?.results)
      ? validationReport.results.find((result) => result?.path === assetPath)
      : undefined;
    if (
      validationReport?.ok !== true
      || validationResult?.ok !== true
      || validationResult?.after_sha256 !== spritesheetSha
      || validationResult?.runtime_pixels_unchanged !== true
      || validationResult?.remaining_occupied_unused_cells?.length !== 0
    ) {
      throw new Error(`Runtime contract validation report is stale for ${id}`);
    }
    if (
      finalVisualEvidence?.pet_id !== id
      || finalVisualEvidence?.verdict !== "pass"
      || finalVisualEvidence?.reviewer_id !== receipt.final_visual.reviewer_id
      || finalVisualEvidence?.isolation_attested !== true
      || finalVisualEvidence?.reviewed_asset_sha256 !== spritesheetSha
      || finalVisualEvidence?.runtime_pixel_continuity?.current_asset_sha256
        !== spritesheetSha
      || finalVisualEvidence?.runtime_pixel_continuity?.decoded_runtime_pixels_unchanged
        !== true
      || finalVisualEvidence?.runtime_pixel_continuity?.runtime_pixels_sha256
        !== structuralEvidence.runtime_pixels_sha256
      || finalVisualEvidence?.checks?.runtime_counts !== "pass"
      || finalVisualEvidence?.checks?.unused_cells_checkerboard_only !== "pass"
      || finalVisualEvidence?.checks?.idle_cell_6_blank !== "pass"
      || finalVisualEvidence?.checks?.clipping_or_cell_bleed !== "none"
    ) {
      throw new Error(`Final visual evidence is not exact-asset bound for ${id}`);
    }
    validateEmbeddedArtifact(
      finalVisualEvidence.contact_sheet,
      `_audit/release/runtime-contract-contact/${id}-`,
      "Runtime contract contact sheet",
    );
    const repairReportPath = validateEmbeddedArtifact(
      finalVisualEvidence.runtime_pixel_continuity.repair_report,
      "_audit/release/evidence/runtime-contract-repair-",
      "Runtime contract repair report",
    );
    const repairReport = parseEvidenceJson(repairReportPath, "Runtime contract repair report");
    const repairResult = Array.isArray(repairReport?.results)
      ? repairReport.results.find((result) => result?.path === assetPath)
      : undefined;
    if (
      repairReport?.ok !== true
      || repairResult?.ok !== true
      || repairResult?.after_sha256 !== spritesheetSha
      || repairResult?.runtime_pixels_unchanged !== true
      || repairResult?.runtime_pixels_sha256_after
        !== structuralEvidence.runtime_pixels_sha256
    ) {
      throw new Error(`Runtime contract repair continuity is stale for ${id}`);
    }
    if (
      receipt?.blind_review?.continuity?.evidence_path
        !== receipt.final_visual.evidence.path
      || receipt?.blind_review?.continuity?.evidence_sha256
        !== receipt.final_visual.evidence.sha256
    ) {
      throw new Error(`Blind review continuity evidence is not sealed for ${id}`);
    }
    if (
      promotionEvidence?.pet_id !== id
      || promotionEvidence?.decided_by !== "parent"
      || promotionEvidence?.post_copy_hash_verified !== true
      || promotionEvidence?.runtime_import !== "pass"
      || promotionEvidence?.runtime_id !== `import:${id}`
      || promotionEvidence?.sprite_version !== 2
      || promotionEvidence?.bundled_resolution !== "pass"
      || promotionEvidence?.shipped_sha256 !== spritesheetSha
    ) {
      throw new Error(`Promotion evidence is not exact-asset bound for ${id}`);
    }
  }

  validateCurrentFleetEvidence(release, petSources);
}

function validateCurrentFleetEvidence(release, petSources) {
  const auditRelative = "_audit/release/manifest.json";
  const playbackRelative = "_audit/release/current-20260831/direct-playback-qa.json";
  const currentPrefix = "_audit/release/current-20260831/";
  const repoPetPrefix = "apps/desktop/src/pets/";
  const expectedAudit = release?.fleet_audit;
  const expectedPlayback = release?.direct_playback;
  if (
    expectedAudit?.path !== auditRelative
    || expectedPlayback?.path !== playbackRelative
  ) {
    throw new Error("Pet release manifest must bind the fleet audit and direct-playback receipt");
  }
  validateHashedArtifact(expectedAudit, auditRelative, "Fleet audit manifest", 128 * 1024);
  rememberReleaseEvidence(fleetAuditManifest, "Fleet audit manifest");
  validateHashedArtifact(
    expectedPlayback,
    playbackRelative,
    "Direct-playback receipt",
    128 * 1024,
  );
  rememberReleaseEvidence(directPlaybackReceipt, "Direct-playback receipt");

  const audit = JSON.parse(readFileSync(fleetAuditManifest, "utf8"));
  if (
    audit?.schema_version !== 2
    || audit?.status !== "approved"
    || audit?.built_in_pet_count !== builtInPets.length
    || audit?.custom_imports_included !== false
    || !Array.isArray(audit?.pets)
    || audit.pets.length !== builtInPets.length
    || audit?.direct_playback?.path !== playbackRelative
    || audit?.direct_playback?.bytes !== expectedPlayback.bytes
    || audit?.direct_playback?.sha256 !== expectedPlayback.sha256
  ) {
    throw new Error("Fleet audit manifest is incomplete or not direct-playback bound");
  }
  for (let index = 0; index < builtInPets.length; index += 1) {
    const id = builtInPets[index];
    const pet = audit.pets[index];
    const releasePet = release.pets[index];
    if (
      pet?.id !== id
      || pet?.spritesheet_sha256 !== releasePet.spritesheet_sha256
      || pet?.release_record !== releasePet.receipt
      || pet?.release_record_sha256 !== releasePet.receipt_sha256
    ) {
      throw new Error(`Fleet audit manifest disagrees with the release manifest for ${id}`);
    }
  }

  const playback = JSON.parse(readFileSync(directPlaybackReceipt, "utf8"));
  assertSchema2EvidenceClosure({
    release,
    audit,
    playback,
    builtInPets,
    requiredPlaybackStates,
    auditPath: auditRelative,
    playbackPath: playbackRelative,
  });
  if (
    playback?.schema_version !== 1
    || playback?.review_kind !== "exact-eight-direct-animated-playback"
    || playback?.verdict !== "pass"
    || JSON.stringify(playback?.scope?.pet_ids) !== JSON.stringify(builtInPets)
    || JSON.stringify(playback?.scope?.required_states) !== JSON.stringify(requiredPlaybackStates)
    || playback?.scope?.display_cell !== "192x208"
    || playback?.scope?.gif_count !== builtInPets.length * requiredPlaybackStates.length
    || playback?.browser_playback_method?.network_or_provider !== false
    || playback?.browser_playback_method?.server !== false
    || playback?.browser_playback_method?.sessions_closed !== true
    || playback?.browser_playback_method?.canvas_status_used_as_evidence !== false
    || playback?.qualitative_review?.verdict !== "pass"
  ) {
    throw new Error("Direct-playback receipt does not certify the exact eight-by-nine runtime matrix");
  }

  const localArtifact = (artifact, name, maxBytes = 16 * 1024 * 1024) => {
    if (typeof artifact?.path !== "string" || artifact.path.includes("/")) {
      throw new Error(`${name} must name one file in the current evidence root`);
    }
    const artifactPath = validateHashedArtifact(
      { ...artifact, path: `${currentPrefix}${artifact.path}` },
      currentPrefix,
      name,
      maxBytes,
    );
    return rememberReleaseEvidence(artifactPath, name);
  };
  const runtimePath = localArtifact(playback.bindings?.runtime_contract, "Playback runtime contract");
  localArtifact(playback.bindings?.prior_visual_qa, "Playback prior visual QA");
  localArtifact(playback.bindings?.local_viewer, "Playback local viewer");

  const screenshotPaths = new Set();
  const screenshotIdentities = new Set();
  const screenshotHashes = new Set();
  if (!Array.isArray(playback?.screenshot_hashes) || playback.screenshot_hashes.length !== 25) {
    throw new Error("Direct-playback receipt must bind exactly 25 timed screenshots");
  }
  for (const screenshot of playback.screenshot_hashes) {
    if (screenshotPaths.has(screenshot?.path)) throw new Error("Playback screenshot paths must be unique");
    screenshotPaths.add(screenshot?.path);
    const screenshotPath = localArtifact(screenshot, "Playback screenshot", 16 * 1024 * 1024);
    const identity = fileIdentity(screenshotPath);
    if (screenshotIdentities.has(identity)) throw new Error("Playback screenshots must be distinct files");
    screenshotIdentities.add(identity);
    if (screenshotHashes.has(screenshot.sha256)) throw new Error("Playback screenshots must have distinct bytes");
    screenshotHashes.add(screenshot.sha256);
  }
  const reviewedScreenshotList = (playback?.temporal_rgb_review?.per_pet ?? [])
    .flatMap((entry) => entry?.screenshots ?? []);
  const reviewedScreenshots = new Set(reviewedScreenshotList);
  if (
    playback?.temporal_rgb_review?.required_state_cells !== 72
    || playback?.temporal_rgb_review?.state_cells_with_nonzero_temporal_rgb_change !== 72
    || playback?.temporal_rgb_review?.state_cells_without_temporal_rgb_change !== 0
    || playback?.temporal_rgb_review?.per_pet?.length !== builtInPets.length
    || reviewedScreenshotList.length !== screenshotPaths.size
    || JSON.stringify([...reviewedScreenshots].sort()) !== JSON.stringify([...screenshotPaths].sort())
    || playback.temporal_rgb_review.per_pet.some(
      (entry, index) => entry?.pet_id !== builtInPets[index]
        || entry?.changed_states !== 9
        || !Array.isArray(entry?.screenshots)
        || entry.screenshots.length < 2,
    )
  ) {
    throw new Error("Direct-playback timed screenshot evidence is incomplete");
  }

  const runtime = JSON.parse(readFileSync(runtimePath, "utf8"));
  if (
    runtime?.schema_version !== 1
    || runtime?.ok !== true
    || runtime?.repair_requested !== false
    || !Array.isArray(runtime?.results)
    || runtime.results.length !== builtInPets.length
  ) {
    throw new Error("Current runtime contract report is not an immutable passing validation");
  }
  const seenCurrentPaths = new Set();
  const gifDecodeSpecs = [];
  let gifCount = 0;
  let frameCount = 0;
  const validateCurrentArtifact = (artifact, label, expectedPrefix = repoPetPrefix + currentPrefix) => {
    if (typeof artifact?.path !== "string" || !artifact.path.startsWith(expectedPrefix)) {
      throw new Error(`${label} is outside the current evidence namespace`);
    }
    const petRelative = artifact.path.slice(repoPetPrefix.length);
    const artifactPath = validateHashedArtifact(
      artifact.path === petRelative ? artifact : { ...artifact, path: petRelative },
      petRelative,
      label,
      16 * 1024 * 1024,
    );
    const identity = fileIdentity(artifactPath);
    if (seenCurrentPaths.has(identity)) throw new Error(`${label} reuses ${petRelative}`);
    seenCurrentPaths.add(identity);
    return rememberReleaseEvidence(artifactPath, label);
  };
  for (let index = 0; index < builtInPets.length; index += 1) {
    const id = builtInPets[index];
    const result = runtime.results[index];
    const evidence = result?.current_evidence;
    const source = petSources.get(id);
    if (
      result?.path !== `apps/desktop/src/pets/${id}/spritesheet.webp`
      || result?.ok !== true
      || result?.repaired !== false
      || result?.after_sha256 !== release.pets[index].spritesheet_sha256
      || result?.runtime_pixels_unchanged !== true
      || result?.remaining_occupied_unused_cells?.length !== 0
      || evidence?.pet_id !== id
      || evidence?.source_atlas?.path !== result.path
      || evidence?.source_atlas?.sha256 !== result.after_sha256
      || evidence?.source_atlas?.bytes !== lstatSync(join(source, "spritesheet.webp")).size
    ) {
      throw new Error(`Current runtime evidence is stale for ${id}`);
    }
    if (sha256File(join(source, "spritesheet.webp")) !== evidence.source_atlas.sha256) {
      throw new Error(`Current source atlas hash mismatch for ${id}`);
    }
    const standardManifestPath = validateCurrentArtifact(
      evidence.standard_frame_manifest,
      `Standard frame manifest for ${id}`,
    );
    const expectedRolePaths = {
      frame_review: `${repoPetPrefix}${currentPrefix}frame-review/${id}.json`,
      contact_sheet: `${repoPetPrefix}${currentPrefix}contact-sheets/${id}-runtime-contract.png`,
      direction_sheet: `${repoPetPrefix}${currentPrefix}direction-sheets/${id}.png`,
      continuity: `${repoPetPrefix}${currentPrefix}continuity/${id}.json`,
    };
    for (const [key, label] of [
      ["frame_review", "Frame review"],
      ["contact_sheet", "Contact sheet"],
      ["direction_sheet", "Direction sheet"],
      ["continuity", "Continuity report"],
    ]) {
      if (evidence?.[key]?.path !== expectedRolePaths[key]) {
        throw new Error(`${label} is not role-bound for ${id}`);
      }
      validateCurrentArtifact(evidence[key], `${label} for ${id}`);
    }
    if (index === 0) validateCurrentArtifact(evidence.independent_visual_qa, "Independent visual QA");
    else if (
      evidence?.independent_visual_qa?.path !== runtime.results[0]?.current_evidence?.independent_visual_qa?.path
      || evidence?.independent_visual_qa?.sha256 !== runtime.results[0]?.current_evidence?.independent_visual_qa?.sha256
      || evidence?.independent_visual_qa?.bytes !== runtime.results[0]?.current_evidence?.independent_visual_qa?.bytes
    ) throw new Error(`Independent visual QA binding mismatch for ${id}`);

    if (
      !Array.isArray(evidence?.motion_previews)
      || evidence.motion_previews.length !== requiredPlaybackStates.length
      || new Set(evidence.motion_previews.map((preview) => preview?.state)).size !== requiredPlaybackStates.length
      || requiredPlaybackStates.some(
        (state) => !evidence.motion_previews.some((preview) => preview?.state === state),
      )
    ) throw new Error(`Motion preview matrix is incomplete for ${id}`);
    const petGifSpecs = new Map();
    for (const preview of evidence.motion_previews) {
      if (
        preview?.path
          !== `${repoPetPrefix}${currentPrefix}previews/${id}/${preview?.state}.gif`
      ) throw new Error(`Motion preview path is not state-bound for ${id}/${preview?.state}`);
      validateCurrentArtifact(preview, `Motion preview ${preview.state} for ${id}`);
      const gifSpec = { state: preview.state, path: join(repo, ...preview.path.split("/")) };
      petGifSpecs.set(preview.state, gifSpec);
      gifDecodeSpecs.push(gifSpec);
      gifCount += 1;
    }

    const frameManifest = JSON.parse(readFileSync(standardManifestPath, "utf8"));
    const expectedFrames = [6, 8, 8, 4, 5, 8, 6, 6, 6];
    if (
      frameManifest?.schema_version !== 1
      || frameManifest?.source_atlas !== result.path
      || frameManifest?.source_atlas_sha256 !== result.after_sha256
      || frameManifest?.cell_width !== 192
      || frameManifest?.cell_height !== 208
      || !Array.isArray(frameManifest?.rows)
      || frameManifest.rows.length !== requiredPlaybackStates.length
    ) throw new Error(`Standard frame manifest is invalid for ${id}`);
    for (let rowIndex = 0; rowIndex < frameManifest.rows.length; rowIndex += 1) {
      const row = frameManifest.rows[rowIndex];
      if (
        row?.state !== ["idle", "running-right", "running-left", "waving", "jumping", "failed", "waiting", "running", "review"][rowIndex]
        || row?.row !== rowIndex
        || row?.method !== "atlas-cell-exact"
        || row?.frames?.length !== expectedFrames[rowIndex]
      ) throw new Error(`Standard frame row ${rowIndex} is invalid for ${id}`);
      for (let frameIndex = 0; frameIndex < row.frames.length; frameIndex += 1) {
        const frame = row.frames[frameIndex];
        const expectedFramePath = `${repoPetPrefix}${currentPrefix}frames/${id}/${row.state}/${String(frameIndex).padStart(2, "0")}.png`;
        if (frame?.column !== frameIndex || frame?.path !== expectedFramePath) {
          throw new Error(`Decoded frame path/column is not state-bound for ${id}/${row.state}`);
        }
        validateCurrentArtifact(
          { path: frame?.path, sha256: frame?.png_sha256 },
          `Decoded frame for ${id}`,
        );
        frameCount += 1;
      }
      petGifSpecs.get(row.state).source_paths = row.frames.map(
        (frame) => join(repo, ...frame.path.split("/")),
      );
    }
  }
  if (
    gifCount !== 72
    || frameCount !== 456
    || playback?.source_gif_verification?.checked !== 72
    || playback?.source_gif_verification?.sha256_and_byte_length_matches !== 72
    || playback?.source_gif_verification?.mismatches !== 0
    || playback?.source_gif_verification?.decoded_frame_check?.gifs_with_expected_frame_count !== 72
    || playback?.source_gif_verification?.decoded_frame_check?.gifs_with_more_than_one_unique_decoded_frame !== 72
    || playback?.source_gif_verification?.decoded_frame_check?.all_decoded_frames_unique_within_each_gif !== true
  ) throw new Error("Direct-playback transitive artifact closure is incomplete");

  const gifDecoder = String.raw`
import hashlib
import json
import sys
from PIL import Image, ImageChops, ImageStat

expected = {
    "idle": 6,
    "waving": 4,
    "jumping": 5,
    "running": 6,
    "running-left": 8,
    "running-right": 8,
    "failed": 8,
    "waiting": 6,
    "review": 6,
}
for item in json.loads(sys.argv[1]):
    with Image.open(item["path"]) as image:
        frames = []
        similarity = []
        for index in range(image.n_frames):
            image.seek(index)
            decoded = image.convert("RGBA")
            frames.append(hashlib.sha256(decoded.tobytes()).hexdigest())
            with Image.open(item["source_paths"][index]) as source:
                expected_frame = source.convert("RGBA")
            if decoded.size != (192, 208) or expected_frame.size != decoded.size:
                raise SystemExit(f'GIF/source geometry mismatch for {item["state"]}')
            similarity.append(max(ImageStat.Stat(ImageChops.difference(decoded, expected_frame)).mean))
    wanted = expected[item["state"]]
    if len(frames) != wanted or len(set(frames)) != wanted or len(item["source_paths"]) != wanted:
        raise SystemExit(
            f'GIF decode mismatch for {item["state"]}: frames={len(frames)} unique={len(set(frames))}'
        )
    if max(similarity) > 16:
        raise SystemExit(f'GIF frames are not atlas-frame bound for {item["state"]}: {max(similarity)}')
`;
  for (let offset = 0; offset < gifDecodeSpecs.length; offset += requiredPlaybackStates.length) {
    execFileSync(
      venvPython,
      ["-c", gifDecoder, JSON.stringify(gifDecodeSpecs.slice(offset, offset + requiredPlaybackStates.length))],
      { cwd: repo, stdio: "inherit" },
    );
  }
}

function verifyFrozenPetBundle(executable, petSources) {
  assertSafeRegularFile(executable, "Frozen bridge verification artifact");
  const smokeParent = assertSafeDirectory(join(repo, "build"), "Sidecar smoke root");
  mkdirSync(smokeParent, { recursive: true });
  const smokeRoot = mkdtempSync(join(smokeParent, "sidecar-smoke-"));
  assertSafeDirectory(smokeRoot, "Sidecar smoke directory");
  try {
    const isolatedHome = join(smokeRoot, "home");
    mkdirSync(isolatedHome, { recursive: true });
    const stdout = execFileSync(executable, ["--verify-bundle"], {
      cwd: smokeRoot,
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: isolatedHome,
        USERPROFILE: isolatedHome,
        PEX_HOME: join(smokeRoot, "pex-home"),
      },
      maxBuffer: 1024 * 1024,
      timeout: 60_000,
      windowsHide: true,
    });
    const actual = parseFrozenBundleInventory(stdout);
    const expected = {
      version: 1,
      pets: builtInPets.map((id) => {
        const source = petSources.get(id);
        if (!source) throw new Error(`Missing validated source for ${id}`);
        const sheet = join(source, "spritesheet.webp");
        return {
          id,
          manifest_sha256: sha256File(join(source, "pet.json")),
          spritesheet_sha256: sha256File(sheet),
          spritesheet_bytes: lstatSync(sheet).size,
        };
      }),
    };
    assertFrozenBundleInventory(actual, expected);
  } finally {
    removeSafeDirectory(smokeRoot, "Sidecar smoke directory");
  }
}

function usableHelper(path) {
  if (!existsSync(path)) return false;
  return assertSafeRegularFile(path, "Cached sidecar artifact").size > 0;
}

function helpersAreCurrent(inputFingerprint) {
  if (
    !usableHelper(bridgeTarget)
    || !usableHelper(cursorHookTarget)
    || !usableHelper(cursorObserveTarget)
  ) return false;
  try {
    if (!usableHelper(buildStamp) || lstatSync(buildStamp).size > 4096) return false;
    const stamp = JSON.parse(readFileSync(buildStamp, "utf8"));
    return sidecarStampMatches({
      stamp,
      inputSha256: inputFingerprint,
      bridgeSha256: sha256File(bridgeTarget),
      cursorHookSha256: sha256File(cursorHookTarget),
      cursorObserveSha256: sha256File(cursorObserveTarget),
    });
  } catch {
    return false;
  }
}

function collectReleaseFiles(path, collected) {
  const safePath = assertSafeRepoPath(path, "Release input");
  if (!existsSync(safePath)) throw new Error(`Required release input is missing: ${safePath}`);
  const entry = lstatSync(safePath);
  if (entry.isSymbolicLink()) throw new Error(`Release input must not be a link: ${safePath}`);
  if (entry.isFile()) {
    collected.push(safePath);
    return;
  }
  if (!entry.isDirectory()) throw new Error(`Release input is not a file or directory: ${safePath}`);
  for (const child of readdirSync(safePath).sort()) {
    if (safePath === petsRoot && (child === "_hatch" || child === "_audit")) continue;
    collectReleaseFiles(join(safePath, child), collected);
  }
}

function fingerprintFiles(paths) {
  const hash = createHash("sha256");
  for (const path of paths) {
    hash.update(relative(repo, path).replaceAll("\\", "/"), "utf8");
    hash.update("\0");
    updateHashFromFile(hash, path);
    hash.update("\0");
  }
  return hash.digest("hex");
}

function runReleasePreflight(petSources) {
  const blockers = [];
  const addBlocker = (code, detail) => blockers.push({ code, detail });
  const inputs = sourceInputFiles();
  inputs.push(...[...validatedReleaseEvidence.values()].map((entry) => entry.file));
  for (const path of [
    join(repo, "apps", "desktop", "src"),
    join(repo, "apps", "desktop", "src-tauri", "src"),
    join(repo, "apps", "desktop", "src-tauri", "capabilities"),
    join(repo, "apps", "desktop", "src-tauri", "permissions"),
    join(repo, "apps", "desktop", "src-tauri", "icons"),
  ]) collectReleaseFiles(path, inputs);
  for (const path of [
    join(repo, "apps", "desktop", "index.html"),
    join(repo, "apps", "desktop", "pet.html"),
    join(repo, "apps", "desktop", "vite.config.ts"),
    join(repo, "apps", "desktop", "tsconfig.json"),
    join(repo, "apps", "desktop", "src-tauri", "Cargo.toml"),
    join(repo, "apps", "desktop", "src-tauri", "Cargo.lock"),
    join(repo, "apps", "desktop", "src-tauri", "build.rs"),
    join(repo, "apps", "desktop", "src-tauri", "tauri.conf.json"),
    join(repo, ".node-version"),
    join(repo, "rust-toolchain.toml"),
  ]) {
    if (existsSync(path)) inputs.push(path);
    else addBlocker("missing_toolchain_or_build_input", relative(repo, path).replaceAll("\\", "/"));
  }
  const uniqueInputs = [...new Set(inputs)].sort(compareCanonicalPaths);
  const relativeInputs = uniqueInputs.map((path) => relative(repo, path).replaceAll("\\", "/"));
  const { untrackedInputs, hiddenIndexInputs } = classifyGitReleaseInputs(
    relativeInputs,
    execFileSync("git", ["ls-files", "-v", "-z"], { cwd: repo, encoding: "utf8" }),
  );
  if (untrackedInputs.length > 0) {
    addBlocker(
      "untracked_release_inputs",
      `${untrackedInputs.length} release inputs are absent from Git (first: ${untrackedInputs.slice(0, 8).join(", ")})`,
    );
  }
  if (hiddenIndexInputs.length > 0) {
    addBlocker(
      "hidden_git_index_inputs",
      `${hiddenIndexInputs.length} release inputs use skip-worktree, assume-unchanged, or another non-normal index state`,
    );
  }
  const status = execFileSync(
    "git",
    ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    { cwd: repo, encoding: "utf8", maxBuffer: 32 * 1024 * 1024 },
  ).split("\0").filter(Boolean);
  if (status.length > 0) addBlocker("dirty_worktree", `${status.length} staged, modified, or untracked paths`);
  const releaseInputSha256Before = fingerprintFiles(uniqueInputs);
  const auditClosureFiles = [...validatedReleaseEvidence.values()]
    .map((entry) => entry.file)
    .sort(compareCanonicalPaths);
  const auditClosureSha256Before = fingerprintFiles(auditClosureFiles);

  const packageJson = JSON.parse(readFileSync(join(desktop, "package.json"), "utf8"));
  const tauri = JSON.parse(readFileSync(join(tauriDir, "tauri.conf.json"), "utf8"));
  const mainCapability = JSON.parse(
    readFileSync(join(tauriDir, "capabilities", "default.json"), "utf8"),
  );
  const petCapability = JSON.parse(readFileSync(join(tauriDir, "capabilities", "pet.json"), "utf8"));
  const cargoToml = readFileSync(join(tauriDir, "Cargo.toml"), "utf8");
  const focusPermission = readFileSync(join(tauriDir, "permissions", "focus.toml"), "utf8");
  const packageSection = cargoToml.match(/\[package\]([\s\S]*?)(?=\r?\n\[|$)/u)?.[1] ?? "";
  const cargoVersion = packageSection.match(/^version\s*=\s*"([^"]+)"\s*$/mu)?.[1];
  const wiringOk = tauriReleaseWiringMatches({
    packageJson,
    tauri,
    mainCapability,
    petCapability,
    cargoVersion,
    focusPermission,
  });
  if (!wiringOk) addBlocker("tauri_release_wiring", "Tauri, capability, version, or sidecar wiring is not exact");

  const nodePin = readFileSync(join(repo, ".node-version"), "utf8").trim();
  const pythonPin = readFileSync(join(repo, ".python-version"), "utf8").trim();
  const rustPin = readFileSync(join(repo, "rust-toolchain.toml"), "utf8")
    .match(/^channel\s*=\s*"([^"]+)"\s*$/mu)?.[1];
  const pythonVersion = execFileSync(
    venvPython,
    ["-c", "import platform; print(platform.python_version())"],
    { cwd: repo, encoding: "utf8" },
  ).trim();
  const rustVersion = execFileSync("rustc", ["--version"], { cwd: repo, encoding: "utf8" }).trim();
  const pyinstallerVersion = execFileSync(
    venvPython,
    ["-c", "import importlib.metadata; print(importlib.metadata.version('pyinstaller'))"],
    { cwd: repo, encoding: "utf8" },
  ).trim();
  const uvLock = readFileSync(join(repo, "uv.lock"), "utf8");
  const toolchainsOk = toolchainsMatch({
    pins: { node: nodePin, python: pythonPin, rust: rustPin },
    active: {
      node: process.versions.node,
      python: pythonVersion,
      rust: rustVersion,
      pyinstaller: pyinstallerVersion,
    },
    uvLock,
  });
  if (!toolchainsOk) addBlocker("toolchain_mismatch", "Active Node/Python/Rust/PyInstaller do not match pinned or locked versions");

  const inputSha256 = sourceFingerprint();
  let stamp = null;
  try {
    stamp = JSON.parse(readFileSync(buildStamp, "utf8"));
  } catch (error) {
    addBlocker("missing_or_invalid_sidecar_stamp", error.message);
  }
  const bridgeSha256 = usableHelper(bridgeTarget) ? sha256File(bridgeTarget) : null;
  const cursorHookSha256 = usableHelper(cursorHookTarget) ? sha256File(cursorHookTarget) : null;
  const cursorObserveSha256 = usableHelper(cursorObserveTarget)
    ? sha256File(cursorObserveTarget)
    : null;
  const sidecarsCurrent = sidecarStampMatches({
    stamp,
    inputSha256,
    bridgeSha256,
    cursorHookSha256,
    cursorObserveSha256,
  });
  let frozenInventoryVerified = false;
  if (!sidecarsCurrent) {
    addBlocker("stale_or_missing_sidecars", "Sidecar stamp or helper bytes do not match current source inputs");
  } else {
    try {
      verifyFrozenPetBundle(bridgeTarget, petSources);
      frozenInventoryVerified = true;
    } catch (error) {
      addBlocker("frozen_inventory_mismatch", error.message);
    }
  }
  const postStatus = execFileSync(
    "git",
    ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    { cwd: repo, encoding: "utf8", maxBuffer: 32 * 1024 * 1024 },
  ).split("\0").filter(Boolean);
  const releaseInputSha256After = fingerprintFiles(uniqueInputs);
  if (!preflightSnapshotIsStable({
    releaseInputSha256Before,
    releaseInputSha256After,
    sourceInputSha256Before: inputSha256,
    sourceInputSha256After: sourceFingerprint(),
    statusBefore: status,
    statusAfter: postStatus,
  })) addBlocker("preflight_toctou", "Repository or release inputs changed during preflight");

  const report = {
    schema: "pex.release-preflight.v1",
    stage: "source",
    source_ready: blockers.length === 0 && frozenInventoryVerified,
    release_ready: false,
    fleet: {
      pet_ids: builtInPets,
      release_manifest: {
        path: relative(repo, petReleaseManifest).replaceAll("\\", "/"),
        sha256: sha256File(petReleaseManifest),
      },
      audit_manifest: {
        path: relative(repo, fleetAuditManifest).replaceAll("\\", "/"),
        sha256: sha256File(fleetAuditManifest),
      },
      playback_receipt: {
        path: relative(repo, directPlaybackReceipt).replaceAll("\\", "/"),
        sha256: sha256File(directPlaybackReceipt),
        gif_count: 72,
        screenshot_count: 25,
        decoded_frame_count: 456,
      },
    },
    git: {
      clean: status.length === 0,
      release_input_count: relativeInputs.length,
      tracked_release_input_count: relativeInputs.length - untrackedInputs.length,
      untracked_release_input_count: untrackedInputs.length,
      hidden_index_input_count: hiddenIndexInputs.length,
      release_input_sha256: releaseInputSha256After,
      audit_reachable_input_count: auditClosureFiles.length,
      audit_closure_sha256: auditClosureSha256Before,
    },
    target: { triple },
    sidecars: {
      input_sha256: inputSha256,
      stamp_input_sha256: stamp?.input_sha256 ?? null,
      bridge_sha256: bridgeSha256,
      cursor_hook_sha256: cursorHookSha256,
      cursor_observe_sha256: cursorObserveSha256,
      current: sidecarsCurrent,
      frozen_inventory_verified: frozenInventoryVerified,
    },
    toolchains: {
      verified: toolchainsOk,
      node: process.versions.node,
      python: pythonVersion,
      rust: rustVersion,
      pyinstaller: pyinstallerVersion,
    },
    tauri: { wiring_verified: wiringOk, external_bin: tauri?.bundle?.externalBin ?? null },
    blockers,
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exit(report.source_ready ? 0 : 2);
}

function installBinary(built, target) {
  assertSafeRegularFile(built, "Built sidecar artifact");
  assertSafeDirectory(dirname(target), "Sidecar binary directory");
  assertSafeRepoPath(target, "Sidecar install target");
  const staged = `${target}.new`;
  const backup = `${target}.old`;
  removeSafeRegularFile(staged, "Staged sidecar artifact");
  removeSafeRegularFile(backup, "Sidecar backup artifact");
  if (existsSync(target)) assertSafeRegularFile(target, "Existing sidecar artifact");
  renameSync(built, staged);
  try {
    if (existsSync(target)) renameSync(target, backup);
    renameSync(staged, target);
  } catch (error) {
    if (!existsSync(target) && existsSync(backup)) renameSync(backup, target);
    removeSafeRegularFile(staged, "Staged sidecar artifact");
    throw error;
  }
  removeSafeRegularFile(backup, "Sidecar backup artifact");
}

try {
for (const path of [binaries, join(repo, "build", "sidecar-pets"), join(repo, "build", "pyinstaller")]) {
  assertSafeDirectory(path, "Sidecar build path");
}
const petSources = new Map(builtInPets.map((id) => [id, validateBuiltInPet(id)]));
validateBuiltInPetMedia(petSources);
validatePetReleaseEvidence(petSources);
if (process.argv.includes("--preflight-release")) runReleasePreflight(petSources);
if (process.argv.includes("--validate-pets-only")) {
  process.stdout.write(
    `${JSON.stringify({ ok: true, built_in_pet_ids: builtInPets }, null, 2)}\n`,
  );
  process.exit(0);
}
const inputFingerprint = sourceFingerprint();
if (helpersAreCurrent(inputFingerprint)) {
  verifyFrozenPetBundle(bridgeTarget, petSources);
  if (sourceFingerprint() !== inputFingerprint) {
    throw new Error("Sidecar inputs changed during cached frozen verification");
  }
  process.stdout.write(`PEX native helpers are current: ${bridgeTarget}\n`);
  process.exit(0);
}

const stagedPets = join(repo, "build", "sidecar-pets");
assertSafeDirectory(stagedPets, "Staged pet directory");
rmSync(stagedPets, { recursive: true, force: true });
mkdirSync(stagedPets, { recursive: true });
assertSafeDirectory(stagedPets, "Staged pet directory");
for (const id of builtInPets) {
  const source = petSources.get(id);
  if (!source) throw new Error(`Validated source disappeared for built-in pet ${id}`);
  const destination = join(stagedPets, id);
  mkdirSync(destination, { recursive: true });
  for (const name of ["pet.json", "spritesheet.webp"]) {
    const asset = join(source, name);
    if (!existsSync(asset)) {
      throw new Error(`Required built-in pet asset is missing: ${asset}`);
    }
    cpSync(asset, join(destination, name));
  }
}

const pyinstaller = process.platform === "win32"
  ? join(repo, ".venv", "Scripts", "pyinstaller.exe")
  : join(repo, ".venv", "bin", "pyinstaller");
if (!existsSync(pyinstaller)) {
  throw new Error("PyInstaller is missing. Run `uv sync --dev` from the repository root.");
}
mkdirSync(binaries, { recursive: true });
const dist = join(repo, "build", "pyinstaller", "dist");
const work = join(repo, "build", "pyinstaller", "work");
const specs = join(repo, "build", "pyinstaller", "spec");
for (const path of [dist, work, specs]) assertSafeDirectory(path, "PyInstaller build path");
rmSync(dist, { recursive: true, force: true });
const dataSeparator = process.platform === "win32" ? ";" : ":";
execFileSync(
  pyinstaller,
  [
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "pex-bridge",
    "--distpath",
    dist,
    "--workpath",
    work,
    "--specpath",
    specs,
    "--collect-all",
    "pex_bridge",
    "--collect-all",
    "pex_supervisor",
    "--collect-all",
    "pex_protocol",
    "--collect-all",
    "keyring",
    "--collect-submodules",
    "strands",
    "--add-data",
    `${stagedPets}${dataSeparator}pex_bridge/_bundled_pets`,
    join(repo, "services", "bridge", "src", "pex_bridge", "main.py"),
  ],
  { cwd: repo, stdio: "inherit" },
);
const built = join(dist, `pex-bridge${extension}`);
if (!existsSync(built)) throw new Error(`PyInstaller did not create ${built}`);
const stagedBridge = join(repo, "build", "pyinstaller", `pex-bridge-${triple}.stage${extension}`);
removeSafeRegularFile(stagedBridge, "Staged bridge artifact");
renameSync(built, stagedBridge);

execFileSync(
  pyinstaller,
  [
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "pex-cursor-hook",
    "--distpath",
    dist,
    "--workpath",
    work,
    "--specpath",
    specs,
    join(repo, "integrations", "cursor-hook", "pex_cursor_hook.py"),
  ],
  { cwd: repo, stdio: "inherit" },
);
const builtCursorHook = join(dist, `pex-cursor-hook${extension}`);
if (!existsSync(builtCursorHook)) {
  throw new Error(`PyInstaller did not create ${builtCursorHook}`);
}
execFileSync(
  pyinstaller,
  [
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "pex-cursor-observe",
    "--distpath",
    dist,
    "--workpath",
    work,
    "--specpath",
    specs,
    join(repo, "integrations", "cursor-hook", "pex_cursor_observe.py"),
  ],
  { cwd: repo, stdio: "inherit" },
);
const builtCursorObserve = join(dist, `pex-cursor-observe${extension}`);
if (!existsSync(builtCursorObserve)) {
  throw new Error(`PyInstaller did not create ${builtCursorObserve}`);
}
const postBuildFingerprint = sourceFingerprint();
if (postBuildFingerprint !== inputFingerprint) {
  throw new Error(
    "Sidecar inputs changed during the build; no helper was installed. Retry from a stable source tree.",
  );
}
verifyFrozenPetBundle(stagedBridge, petSources);
const postSmokeFingerprint = sourceFingerprint();
if (postSmokeFingerprint !== inputFingerprint) {
  throw new Error(
    "Sidecar inputs changed during frozen verification; no helper was installed. Retry from a stable source tree.",
  );
}
installBinary(stagedBridge, bridgeTarget);
installBinary(builtCursorHook, cursorHookTarget);
installBinary(builtCursorObserve, cursorObserveTarget);
const stampArtifact = join(dist, `pex-sidecars-${triple}.json`);
writeFileSync(
  stampArtifact,
  `${JSON.stringify(
    {
      version: 3,
      input_sha256: inputFingerprint,
      bridge_sha256: sha256File(bridgeTarget),
      cursor_hook_sha256: sha256File(cursorHookTarget),
      cursor_observe_sha256: sha256File(cursorObserveTarget),
    },
    null,
    2,
  )}\n`,
  "utf8",
);
installBinary(stampArtifact, buildStamp);
process.stdout.write(`Built PEX bridge sidecar: ${bridgeTarget}\n`);
process.stdout.write(`Built PEX Cursor hook helper: ${cursorHookTarget}\n`);
process.stdout.write(`Built PEX Cursor observe helper: ${cursorObserveTarget}\n`);
} catch (error) {
  if (process.argv.includes("--preflight-release")) {
    process.stdout.write(`${JSON.stringify({
      schema: "pex.release-preflight.v1",
      stage: "source",
      source_ready: false,
      release_ready: false,
      fleet: { pet_ids: builtInPets },
      blockers: [{ code: "release_contract_validation", detail: error.message }],
    }, null, 2)}\n`);
    process.exit(2);
  }
  throw error;
}

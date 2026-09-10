import { createHash } from "node:crypto";
import { lstatSync, readdirSync, readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";

const SHA256 = /^[0-9a-f]{64}$/u;
const REQUIRED_FILES = Object.freeze(["pex-bridge.exe", "_internal/python312.dll"]);
const WINDOWS_RESERVED_BASENAMES = /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/iu;

function exactKeys(value, expected) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function assertRuntimeRoot(root) {
  if (typeof root !== "string" || root.length === 0) {
    throw new TypeError("Bridge runtime root must be a non-empty path");
  }
  const resolved = resolve(root);
  const entry = lstatSync(resolved);
  if (entry.isSymbolicLink() || !entry.isDirectory()) {
    throw new Error("Bridge runtime root must be a non-symbolic-link directory");
  }
  return resolved;
}

function canonicalRelativePath(root, path) {
  const value = relative(root, path).replaceAll("\\", "/");
  if (value.length === 0 || isAbsolute(value) || value.split("/").some((part) => part === "" || part === "." || part === "..")) {
    throw new Error(`Bridge runtime file path is not canonical: ${value}`);
  }
  return value;
}

function comparePosixPaths(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function collectFiles(root, directory, files) {
  for (const name of readdirSync(directory).sort()) {
    const path = resolve(directory, name);
    const entry = lstatSync(path);
    if (entry.isSymbolicLink()) {
      throw new Error(`Bridge runtime must not contain symbolic links: ${canonicalRelativePath(root, path)}`);
    }
    if (entry.isDirectory()) {
      collectFiles(root, path, files);
      continue;
    }
    if (!entry.isFile()) {
      throw new Error(`Bridge runtime must contain only regular files and directories: ${canonicalRelativePath(root, path)}`);
    }
    files.push({
      path: canonicalRelativePath(root, path),
      bytes: entry.size,
      sha256: sha256File(path),
    });
  }
}

function assertCanonicalFilePath(path) {
  if (
    typeof path !== "string"
    || path.length === 0
    || path.includes("\\")
    || isAbsolute(path)
    || path.split("/").some((part) => part === "" || part === "." || part === ".."
      || part.includes(":")
      || /[\u0000-\u001f\u007f-\u009f]/u.test(part)
      || /[. ]$/u.test(part)
      || WINDOWS_RESERVED_BASENAMES.test(part))
  ) {
    throw new Error("Bridge runtime manifest contains a non-canonical file path");
  }
}

export function validateBridgeRuntimeManifest(manifest) {
  if (!exactKeys(manifest, ["version", "files"]) || manifest.version !== 1 || !Array.isArray(manifest.files)) {
    throw new Error("Bridge runtime manifest must have exact version 1 schema");
  }
  let previousPath = null;
  const caseInsensitivePaths = new Set();
  for (const file of manifest.files) {
    if (!exactKeys(file, ["path", "bytes", "sha256"])) {
      throw new Error("Bridge runtime manifest file entry has an invalid schema");
    }
    assertCanonicalFilePath(file.path);
    if (!Number.isSafeInteger(file.bytes) || file.bytes < 0 || typeof file.sha256 !== "string" || !SHA256.test(file.sha256)) {
      throw new Error(`Bridge runtime manifest file entry is invalid: ${file.path}`);
    }
    if (previousPath !== null && comparePosixPaths(previousPath, file.path) >= 0) {
      throw new Error("Bridge runtime manifest files must be strictly sorted by POSIX path");
    }
    previousPath = file.path;
    const folded = file.path.toLocaleLowerCase("en-US");
    if (caseInsensitivePaths.has(folded)) {
      throw new Error(`Bridge runtime manifest contains a case-insensitive path collision: ${file.path}`);
    }
    caseInsensitivePaths.add(folded);
  }
  const paths = new Set(manifest.files.map((file) => file.path));
  for (const required of REQUIRED_FILES) {
    if (!paths.has(required)) throw new Error(`Bridge runtime manifest is missing required file: ${required}`);
  }
  return manifest;
}

export function buildBridgeRuntimeManifest(root) {
  const runtimeRoot = assertRuntimeRoot(root);
  const files = [];
  collectFiles(runtimeRoot, runtimeRoot, files);
  files.sort((left, right) => comparePosixPaths(left.path, right.path));
  return validateBridgeRuntimeManifest({ version: 1, files });
}

export function assertBridgeRuntimeMatches(expected, actual) {
  validateBridgeRuntimeManifest(expected);
  validateBridgeRuntimeManifest(actual);
  if (JSON.stringify(expected) !== JSON.stringify(actual)) {
    throw new Error("Bridge runtime manifest mismatch");
  }
  return actual;
}

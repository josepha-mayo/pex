import { createHash } from "node:crypto";
import {
  chmodSync,
  constants,
  copyFileSync,
  lstatSync,
  readlinkSync,
  readdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
} from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";

const SHA256 = /^[0-9a-f]{64}$/u;
const BRIDGE_EXECUTABLES = Object.freeze(["pex-bridge.exe", "pex-bridge"]);
const PYTHON_RUNTIME = /^_internal\/(?:python\d+\.dll|libpython\d+(?:\.\d+)*\.(?:so(?:\.\d+)*|dylib))$/u;
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

function assertContained(root, path, label) {
  const value = relative(root, path);
  if (value === "" || isAbsolute(value) || value.split(/[\\/]/u).includes("..")) {
    throw new Error(`${label} escapes the bridge runtime: ${value}`);
  }
}

function collectSymbolicLinks(root, directory, links) {
  for (const name of readdirSync(directory).sort()) {
    const path = resolve(directory, name);
    const entry = lstatSync(path);
    if (entry.isSymbolicLink()) {
      links.push(path);
    } else if (entry.isDirectory()) {
      collectSymbolicLinks(root, path, links);
    } else if (!entry.isFile()) {
      throw new Error(`Bridge runtime must contain only regular files and directories: ${canonicalRelativePath(root, path)}`);
    }
  }
}

export function materializeBridgeRuntimeSymlinks(root) {
  const runtimeRoot = assertRuntimeRoot(root);
  const links = [];
  collectSymbolicLinks(runtimeRoot, runtimeRoot, links);
  for (const link of links) {
    const relativeLink = canonicalRelativePath(runtimeRoot, link);
    const linkTarget = readlinkSync(link);
    if (isAbsolute(linkTarget)) {
      throw new Error(`Bridge runtime symbolic link must use an in-tree relative target: ${relativeLink}`);
    }
    const lexicalTarget = resolve(dirname(link), linkTarget);
    assertContained(runtimeRoot, lexicalTarget, `Bridge runtime symbolic link ${relativeLink}`);
    let resolvedTarget;
    try {
      resolvedTarget = realpathSync.native(lexicalTarget);
    } catch (error) {
      throw new Error(`Bridge runtime symbolic link is dangling: ${relativeLink}`, { cause: error });
    }
    assertContained(runtimeRoot, resolvedTarget, `Bridge runtime symbolic link ${relativeLink}`);
    const target = statSync(link);
    if (!target.isFile()) {
      throw new Error(`Bridge runtime symbolic link must resolve to a regular file: ${relativeLink}`);
    }
    const staged = `${link}.pex-materialized`;
    try {
      copyFileSync(resolvedTarget, staged, constants.COPYFILE_EXCL);
      chmodSync(staged, target.mode);
      rmSync(link);
      renameSync(staged, link);
    } finally {
      rmSync(staged, { force: true });
    }
  }
  return links.map((path) => canonicalRelativePath(runtimeRoot, path));
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
  if (!BRIDGE_EXECUTABLES.some((path) => paths.has(path))) {
    throw new Error("Bridge runtime manifest is missing its required bridge executable");
  }
  if (!manifest.files.some((file) => PYTHON_RUNTIME.test(file.path))) {
    throw new Error("Bridge runtime manifest is missing its required Python runtime library");
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

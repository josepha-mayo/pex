import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  assertBridgeRuntimeMatches,
  buildBridgeRuntimeManifest,
  validateBridgeRuntimeManifest,
} from "./bridge-runtime-contract.mjs";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "pex-bridge-runtime-contract-"));
  mkdirSync(join(root, "_internal"));
  writeFileSync(join(root, "pex-bridge.exe"), "bridge", "utf8");
  writeFileSync(join(root, "_internal", "python312.dll"), "python", "utf8");
  writeFileSync(join(root, "_internal", "base_library.zip"), "stdlib", "utf8");
  writeFileSync(join(root, "_internal", "Zebra.pyd"), "zebra", "utf8");
  writeFileSync(join(root, "!notice.txt"), "notice", "utf8");
  return root;
}

function withFixture(operation) {
  const root = fixture();
  try {
    operation(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test("builds a sorted complete runtime-tree manifest", () => withFixture((root) => {
  const manifest = buildBridgeRuntimeManifest(root);
  assert.deepEqual(manifest, {
    version: 1,
    files: [
      { path: "!notice.txt", bytes: 6, sha256: sha256("notice") },
      { path: "_internal/Zebra.pyd", bytes: 5, sha256: sha256("zebra") },
      { path: "_internal/base_library.zip", bytes: 6, sha256: sha256("stdlib") },
      { path: "_internal/python312.dll", bytes: 6, sha256: sha256("python") },
      { path: "pex-bridge.exe", bytes: 6, sha256: sha256("bridge") },
    ],
  });
  assert.deepEqual(assertBridgeRuntimeMatches(manifest, structuredClone(manifest)), manifest);
}));

test("tree manifests detect changed, missing, and extra runtime files", () => withFixture((root) => {
  const expected = buildBridgeRuntimeManifest(root);
  writeFileSync(join(root, "_internal", "python312.dll"), "changed", "utf8");
  assert.throws(() => assertBridgeRuntimeMatches(expected, buildBridgeRuntimeManifest(root)), /mismatch/u);
  rmSync(join(root, "_internal", "python312.dll"));
  assert.throws(() => buildBridgeRuntimeManifest(root), /missing required file/u);
  writeFileSync(join(root, "_internal", "python312.dll"), "python", "utf8");
  writeFileSync(join(root, "extra.txt"), "extra", "utf8");
  assert.throws(() => assertBridgeRuntimeMatches(expected, buildBridgeRuntimeManifest(root)), /mismatch/u);
}));

test("manifest validation rejects traversal, collisions, invalid hashes, and schema changes", () => {
  const good = {
    version: 1,
    files: [
      { path: "_internal/python312.dll", bytes: 1, sha256: "a".repeat(64) },
      { path: "pex-bridge.exe", bytes: 1, sha256: "b".repeat(64) },
    ],
  };
  assert.deepEqual(validateBridgeRuntimeManifest(structuredClone(good)), good);
  for (const mutate of [
    (value) => { value.files[0].path = "../python312.dll"; },
    (value) => { value.files.push({ path: "PEX-BRIDGE.EXE", bytes: 1, sha256: "c".repeat(64) }); },
    (value) => { value.files[0].sha256 = "A".repeat(64); },
    (value) => { value.files[0].extra = true; },
    (value) => { value.version = 2; },
    (value) => { value.files.reverse(); },
    (value) => { value.files[0].path = "_internal/python:stream.dll"; },
    (value) => { value.files[0].path = "_internal/control\u0001.dll"; },
    (value) => { value.files[0].path = "_internal/trailing. "; },
    (value) => { value.files[0].path = "_internal/CON.dll"; },
  ]) {
    const invalid = structuredClone(good);
    mutate(invalid);
    assert.throws(() => validateBridgeRuntimeManifest(invalid));
  }
});

test("tree construction rejects symbolic links when the platform permits them", (t) => withFixture((root) => {
  const link = join(root, "_internal", "linked.dll");
  try {
    symlinkSync(join(root, "_internal", "python312.dll"), link, "file");
  } catch (error) {
    if (error?.code === "EPERM" || error?.code === "EACCES") {
      t.skip(`symbolic-link creation is unavailable: ${error.code}`);
      return;
    }
    throw error;
  }
  assert.throws(() => buildBridgeRuntimeManifest(root), /symbolic links/u);
}));

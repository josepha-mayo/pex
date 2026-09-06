import assert from "node:assert/strict";
import test from "node:test";

import {
  PACKAGE_BINARIES,
  findUniquePackagedFiles,
  packageReceiptIsReady,
  validateEmbeddedFiles,
} from "./package-contract.mjs";

const hash = (character) => character.repeat(64);
const embedded = () => Object.fromEntries(PACKAGE_BINARIES.map(
  (name, index) => [name, { bytes: index + 1, sha256: hash(String(index + 1)) }],
));

function receipt() {
  const msi = embedded();
  const nsis = structuredClone(msi);
  return {
    schema: "pex.package-receipt.v1",
    stage: "package",
    source: {
      commit: "a".repeat(40),
      release_input_sha256: hash("b"),
      sidecar_input_sha256: hash("c"),
      preflight_sha256: hash("d"),
    },
    installers: { msi_sha256: hash("e"), nsis_sha256: hash("f") },
    msi: { status: "verified", embedded: msi, inventory_verified: true },
    nsis: { status: "verified", embedded: nsis, inventory_verified: true },
    release_ready: true,
    blockers: [],
  };
}

test("package inventory requires each named executable exactly once", () => {
  const paths = PACKAGE_BINARIES.map((name) => `root/bin/${name}`);
  assert.deepEqual(Object.keys(findUniquePackagedFiles(paths)), PACKAGE_BINARIES);
  assert.throws(() => findUniquePackagedFiles(paths.slice(1)), /exactly one pex-desktop/u);
  assert.throws(() => findUniquePackagedFiles([...paths, `other/${PACKAGE_BINARIES[1]}`]), /found 2/u);
  assert.throws(() => findUniquePackagedFiles([42]), /must be text/u);
});

test("embedded receipts reject missing, extra, empty, and malformed artifacts", () => {
  assert.doesNotThrow(() => validateEmbeddedFiles(embedded()));
  for (const mutate of [
    (value) => { delete value[PACKAGE_BINARIES[0]]; },
    (value) => { value.extra = { bytes: 1, sha256: hash("a") }; },
    (value) => { value[PACKAGE_BINARIES[0]].bytes = 0; },
    (value) => { value[PACKAGE_BINARIES[0]].sha256 = "BAD"; },
    (value) => { value[PACKAGE_BINARIES[0]].trusted = true; },
  ]) {
    const value = embedded();
    mutate(value);
    assert.throws(() => validateEmbeddedFiles(value), /Package must|Invalid embedded/u);
  }
});

test("package readiness fails closed on unsupported NSIS, mismatches, or schema extension", () => {
  assert.equal(packageReceiptIsReady(receipt()), true);
  for (const mutate of [
    (value) => { value.nsis.status = "unsupported"; value.release_ready = false; },
    (value) => { value.msi.inventory_verified = false; value.release_ready = false; },
    (value) => { value.nsis.embedded[PACKAGE_BINARIES[1]].sha256 = hash("9"); },
    (value) => { value.nsis.embedded[PACKAGE_BINARIES[0]].sha256 = hash("9"); },
    (value) => { value.blockers.push({ code: "x", detail: "x" }); value.release_ready = false; },
    (value) => { value.source.commit = "short"; },
    (value) => { value.unexpected = true; },
  ]) {
    const value = receipt();
    mutate(value);
    assert.equal(packageReceiptIsReady(value), false);
  }
});

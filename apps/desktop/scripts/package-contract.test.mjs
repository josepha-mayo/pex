import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  PACKAGE_BINARIES,
  findUniquePackagedFiles,
  packageReceiptIsReady,
  validateEmbeddedFiles,
  verifyDesktopBundleVariants,
} from "./package-contract.mjs";

const hash = (character) => character.repeat(64);
const hashBuffer = (value) => createHash("sha256").update(value).digest("hex");
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
      canonical_desktop_sha256: hash("a"),
    },
    installers: { msi_sha256: hash("e"), nsis_sha256: hash("f") },
    desktop_bundle_marker: {
      offset: 100,
      width: 4,
      canonical_marker_hex: "554e4bc0",
      msi_marker_hex: "4d5349c0",
      nsis_marker_hex: "4e534953",
      normalized_sha256: hash("a"),
    },
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

test("canonical, MSI, and NSIS differ only at the exact four-byte Tauri marker", () => {
  const prefix = Buffer.from("header__TAURI_BUNDLE_TYPE_VAR_", "ascii");
  const suffix = Buffer.from([0xc0, 0, 0x74, 0x65, 0x78, 0x74]);
  const unpatched = Buffer.concat([prefix, Buffer.from("UNK", "ascii"), suffix]);
  const msi = Buffer.from(unpatched);
  Buffer.from("MSI", "ascii").copy(msi, prefix.length);
  const nsis = Buffer.from(unpatched);
  Buffer.from("NSIS", "ascii").copy(nsis, prefix.length);
  const canonical = Buffer.from(unpatched);
  const proof = verifyDesktopBundleVariants(canonical, msi, nsis);
  assert.equal(proof.offset, prefix.length);
  assert.equal(proof.width, 4);
  const neutral = Buffer.from(unpatched);
  Buffer.from("NONE", "ascii").copy(neutral, prefix.length);
  assert.equal(proof.normalized_sha256, hashBuffer(neutral));

  const outside = Buffer.from(nsis);
  outside[0] ^= 1;
  assert.throws(
    () => verifyDesktopBundleVariants(canonical, msi, outside),
    /outside the exact Tauri bundle marker/u,
  );
  const forged = Buffer.from(nsis);
  Buffer.from("ZIP!", "ascii").copy(forged, prefix.length);
  assert.throws(() => verifyDesktopBundleVariants(canonical, msi, forged), /expected UNK-c0\/MSI-c0\/NSIS/u);
  assert.throws(() => verifyDesktopBundleVariants(canonical, msi.subarray(1), nsis), /identical lengths/u);

  const msiOutside = Buffer.from(msi);
  msiOutside[0] ^= 1;
  assert.throws(
    () => verifyDesktopBundleVariants(canonical, msiOutside, nsis),
    /outside the exact Tauri bundle marker/u,
  );
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
    (value) => { value.desktop_bundle_marker.normalized_sha256 = "bad"; },
    (value) => { value.source.canonical_desktop_sha256 = "bad"; },
    (value) => { value.blockers.push({ code: "x", detail: "x" }); value.release_ready = false; },
    (value) => { value.source.commit = "short"; },
    (value) => { value.unexpected = true; },
  ]) {
    const value = receipt();
    mutate(value);
    assert.equal(packageReceiptIsReady(value), false);
  }
});

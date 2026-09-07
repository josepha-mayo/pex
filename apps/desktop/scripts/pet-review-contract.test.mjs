import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import { validatePetReviewArchive } from "./pet-review-contract.mjs";

const read = (file) => JSON.parse(readFileSync(new URL(`../src/pets/release-evidence/${file}`, import.meta.url)));
const archive = read("review-archive.json");
const records = read("independent-reviews.json").records;
const repair = read("neutral-repair.json").pets;
const ids = repair.map((pet) => pet.id);
const check = (value) => validatePetReviewArchive(value, records, repair, ids);

test("all 24 original verdicts and eight static reviews remain inspectable and bound", () => {
  assert.doesNotThrow(() => check(archive));
});

test("opaque claims cannot substitute for original review bytes", () => {
  const value = structuredClone(archive);
  delete value.pets[0].blind_reviews[0].content;
  assert.throws(() => check(value), /original digest/);
});

test("modified review text fails its hash binding", () => {
  const value = structuredClone(archive);
  value.pets[0].blind_reviews[0].content += " ";
  assert.throws(() => check(value), /original digest/);
});

test("a rehashed fabricated result still fails original subject binding", () => {
  const value = structuredClone(archive);
  const original = value.pets[0].blind_reviews[0];
  original.content = JSON.stringify({ pairs: [] });
  original.bytes = Buffer.byteLength(original.content);
  original.sha256 = createHash("sha256").update(original.content).digest("hex");
  assert.throws(() => check(value), /blind review binding/);
});

test("the review cannot silently move to another source atlas", () => {
  const wrong = structuredClone(repair);
  wrong[0].before_sha256 = "f".repeat(64);
  assert.throws(() => validatePetReviewArchive(archive, records, wrong, ids), /static review binding/);
});

test("rehashed evidence cannot downgrade a cardinal to an intermediate warning", () => {
  const value = structuredClone(archive);
  const pet = value.pets[0];
  const validation = JSON.parse(pet.blind_validation.content);
  validation.pairs.find((pair) => pair.pair === "horizontal-4").gate = "review";
  const seal = (content) => ({
    content, bytes: Buffer.byteLength(content),
    sha256: createHash("sha256").update(content).digest("hex"),
  });
  pet.blind_validation = seal(JSON.stringify(validation));
  const binding = JSON.parse(pet.source_binding.content);
  binding.blind_review.validation.sha256 = pet.blind_validation.sha256;
  pet.source_binding = seal(JSON.stringify(binding));
  assert.throws(() => check(value), /cardinal gate downgraded/);
});

test("a rehashed wrong hard-cardinal majority is rejected", () => {
  const value = structuredClone(archive);
  const binding = JSON.parse(value.pets[0].source_binding.content);
  const changedRecords = structuredClone(records);
  for (let index = 0; index < 3; index += 1) {
    const reviewer = value.pets[0].blind_reviews[index];
    const verdict = JSON.parse(reviewer.content);
    verdict.pairs.find((entry) => entry.pair === "horizontal-4").A = "screen-left";
    reviewer.content = JSON.stringify(verdict);
    reviewer.bytes = Buffer.byteLength(reviewer.content);
    reviewer.sha256 = createHash("sha256").update(reviewer.content).digest("hex");
    binding.blind_review.reviewers[index].verdict_sha256 = reviewer.sha256;
    changedRecords[index][4] = reviewer.sha256;
    changedRecords[index][5] = reviewer.bytes;
  }
  value.pets[0].source_binding.content = JSON.stringify(binding);
  value.pets[0].source_binding.bytes = Buffer.byteLength(value.pets[0].source_binding.content);
  value.pets[0].source_binding.sha256 = createHash("sha256").update(value.pets[0].source_binding.content).digest("hex");
  assert.throws(() => validatePetReviewArchive(value, changedRecords, repair, ids), /majority mismatch/);
});

test("a self-consistent rehashed wrong hard-cardinal validation is rejected", () => {
  const value = structuredClone(archive);
  const binding = JSON.parse(value.pets[0].source_binding.content);
  const changedRecords = structuredClone(records);
  for (let index = 0; index < 2; index += 1) {
    const reviewer = value.pets[0].blind_reviews[index];
    const verdict = JSON.parse(reviewer.content);
    verdict.pairs.find((entry) => entry.pair === "horizontal-4").A = "screen-left";
    reviewer.content = JSON.stringify(verdict);
    reviewer.bytes = Buffer.byteLength(reviewer.content);
    reviewer.sha256 = createHash("sha256").update(reviewer.content).digest("hex");
    binding.blind_review.reviewers[index].verdict_sha256 = reviewer.sha256;
    changedRecords[index][4] = reviewer.sha256;
    changedRecords[index][5] = reviewer.bytes;
  }
  const validation = JSON.parse(value.pets[0].blind_validation.content);
  const pair = validation.pairs.find((entry) => entry.pair === "horizontal-4");
  pair.A.observed = "screen-left";
  pair.A.pass = false;
  value.pets[0].blind_validation.content = JSON.stringify(validation);
  value.pets[0].blind_validation.bytes = Buffer.byteLength(value.pets[0].blind_validation.content);
  value.pets[0].blind_validation.sha256 = createHash("sha256")
    .update(value.pets[0].blind_validation.content).digest("hex");
  binding.blind_review.validation.sha256 = value.pets[0].blind_validation.sha256;
  value.pets[0].source_binding.content = JSON.stringify(binding);
  value.pets[0].source_binding.bytes = Buffer.byteLength(value.pets[0].source_binding.content);
  value.pets[0].source_binding.sha256 = createHash("sha256")
    .update(value.pets[0].source_binding.content).digest("hex");
  assert.throws(
    () => validatePetReviewArchive(value, changedRecords, repair, ids),
    /hard gate failed/,
  );
});

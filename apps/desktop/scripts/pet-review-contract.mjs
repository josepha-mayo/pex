import { createHash } from "node:crypto";

const digest = (data) => createHash("sha256").update(data).digest("hex");

const HORIZONTAL_EXPECTED = new Map([
  ["022.5", "screen-right"], ["045", "screen-right"], ["067.5", "screen-right"],
  ["090", "screen-right"], ["112.5", "screen-right"], ["135", "screen-right"],
  ["157.5", "screen-right"], ["202.5", "screen-left"], ["225", "screen-left"],
  ["247.5", "screen-left"], ["270", "screen-left"], ["292.5", "screen-left"],
  ["315", "screen-left"], ["337.5", "screen-left"],
]);
const VERTICAL_EXPECTED = new Map([
  ["000", "up"], ["022.5", "up"], ["045", "up"], ["067.5", "up"],
  ["112.5", "down"], ["135", "down"], ["157.5", "down"], ["180", "down"],
  ["202.5", "down"], ["225", "down"], ["247.5", "down"], ["292.5", "up"],
  ["315", "up"], ["337.5", "up"],
]);

function decode(record) {
  if (typeof record?.content !== "string"
      || Buffer.byteLength(record.content, "utf8") !== record.bytes
      || digest(record.content) !== record.sha256) {
    throw new Error("Archived review bytes do not match their original digest");
  }
  return JSON.parse(record.content);
}

/** Validate actual historical review bytes; never manufacture a fresh visual verdict. */
export function validatePetReviewArchive(archive, records, repairPets, petIds) {
  if (archive?.schema_version !== 1 || !Array.isArray(archive.pets)
      || archive.pets.length !== petIds.length || records.length !== petIds.length * 3) {
    throw new Error("Historical review archive is incomplete");
  }
  for (const [index, id] of petIds.entries()) {
    const pet = archive.pets[index];
    const sourceSha = repairPets[index].before_sha256;
    if (pet.id !== id || pet.blind_reviews?.length !== 3) {
      throw new Error("Historical review archive pet order or reviewer count mismatch");
    }
    const binding = decode(pet.source_binding);
    const validation = decode(pet.blind_validation);
    const visual = decode(pet.visual_review);
    if (binding.pet_id !== id || binding.shipped_sha256 !== sourceSha
        || binding.final_visual?.evidence?.sha256 !== pet.visual_review.sha256
        || visual.pet_id !== id || visual.reviewed_asset_sha256 !== sourceSha
        || visual.verdict !== "pass" || visual.isolation_attested !== true
        || visual.checks?.clipping_or_cell_bleed !== "none"
        || visual.checks?.opposite_cardinal_directions !== "pass"
        || visual.checks?.opposite_running_directions !== "pass"
        || visual.checks?.transparency !== "pass") {
      throw new Error(`Historical static review binding or verdict invalid for ${id}`);
    }
    if (binding.blind_review?.ok !== true
        || binding.blind_review?.validation?.sha256 !== pet.blind_validation.sha256
        || validation.ok !== true || !Array.isArray(validation.errors) || validation.errors.length !== 0
        || !Array.isArray(validation.pairs) || validation.pairs.length !== 14) {
      throw new Error(`Historical blind validation binding invalid for ${id}`);
    }
    const reviewerIds = new Set();
    const reviewerPairs = [];
    for (let worker = 0; worker < 3; worker += 1) {
      const reference = binding.blind_review?.reviewers?.[worker];
      const original = pet.blind_reviews[worker];
      const row = records[index * 3 + worker];
      const verdict = decode(original);
      if (!reference?.reviewer_id || reference.isolation_attested !== true
          || reference.verdict_sha256 !== original.sha256
          || row[0] !== id || row[2] !== worker + 1
          || row[4] !== original.sha256 || row[5] !== original.bytes
          || !Array.isArray(verdict.pairs) || verdict.pairs.length !== 14) {
        throw new Error(`Original blind review binding invalid for ${id}`);
      }
      reviewerIds.add(reference.reviewer_id);
      const pairs = new Set();
      const classifications = new Map();
      for (const pair of verdict.pairs) {
        if (!/^(horizontal|vertical)-[1-7]$/u.test(pair.pair) || pairs.has(pair.pair)) {
          throw new Error(`Missing or duplicate blind pair for ${id}`);
        }
        pairs.add(pair.pair);
        classifications.set(pair.pair, pair);
        const allowed = pair.pair.startsWith("horizontal")
          ? ["screen-left", "screen-right", "ambiguous"] : ["up", "down", "ambiguous"];
        if (!allowed.includes(pair.A) || !allowed.includes(pair.B)) {
          throw new Error(`Invalid blind axis classification for ${id}`);
        }
      }
      reviewerPairs.push(classifications);
    }
    if (reviewerIds.size !== 3) throw new Error(`Duplicate historical reviewer for ${id}`);
    const validationPairs = new Set();
    const reviewedDirections = { horizontal: new Set(), vertical: new Set() };
    for (const pair of validation.pairs) {
      if (!/^(horizontal|vertical)-[1-7]$/u.test(pair?.pair)
          || validationPairs.has(pair.pair) || !["hard", "review"].includes(pair.gate)
          || pair.axis !== (pair.pair.startsWith("horizontal") ? "horizontal" : "vertical")) {
        throw new Error(`Historical blind validation pair invalid for ${id}`);
      }
      validationPairs.add(pair.pair);
      const expectedByDirection = pair.axis === "horizontal" ? HORIZONTAL_EXPECTED : VERTICAL_EXPECTED;
      for (const side of ["A", "B"]) {
        const detail = pair[side];
        const expected = expectedByDirection.get(detail?.source_direction);
        if (!expected || detail.expected !== expected) {
          throw new Error(`Historical blind expected axis invalid for ${id}`);
        }
        if (reviewedDirections[pair.axis].has(detail.source_direction)) {
          throw new Error(`Duplicate blind source direction for ${id}`);
        }
        reviewedDirections[pair.axis].add(detail.source_direction);
        const cardinal = pair.axis === "horizontal"
          ? ["090", "270"].includes(detail.source_direction)
          : ["000", "180"].includes(detail.source_direction);
        if (pair.gate !== (cardinal ? "hard" : "review")) {
          throw new Error(`Historical blind cardinal gate downgraded for ${id}`);
        }
        const votes = reviewerPairs.map((review) => review.get(pair.pair)?.[side]);
        const strictMajority = votes.find((vote) => votes.filter((other) => other === vote).length >= 2);
        const observed = strictMajority ?? "ambiguous";
        if (detail.observed !== observed || detail.pass !== (observed === expected)) {
          throw new Error(`Historical blind majority mismatch for ${id}`);
        }
        if (pair.gate === "hard" && detail.pass !== true) {
          throw new Error(`Historical blind hard gate failed for ${id}`);
        }
      }
    }
    if (validationPairs.size !== 14) throw new Error(`Historical blind validation is incomplete for ${id}`);
  }
}

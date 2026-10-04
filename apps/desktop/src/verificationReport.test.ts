import assert from "node:assert/strict";
import test from "node:test";

import {
  parseVerificationReport,
  verificationSummaryLine,
  verificationVerdictLabel,
} from "./verificationReport.ts";

const report = {
  schema: "pex.verification-report.v1",
  generated_at: "2026-10-04T06:57:47.035061+00:00",
  claims: [
    {
      at: "2026-10-04T06:36:38.792743+00:00",
      action_taken: "NOOP",
      verification_status: "supported",
      acceptance_surface: { modified: [], deleted: [], added: [], added_config: [] },
      evidence: [],
    },
    {
      at: "2026-10-04T06:36:34.245638+00:00",
      action_taken: "SEND_NUDGE",
      verification_status: "uncertain",
      acceptance_surface: {
        modified: ["tests/test_core.py"],
        deleted: [],
        added: [],
        added_config: [],
      },
      evidence: ["acceptance file changed after baseline"],
    },
  ],
  claims_scanned: 4,
  claims_truncated: false,
  acceptance_baselines: [
    { session_id: "s1", sealed_at: "2026-10-04T06:36:28.9Z", files: 3, files_complete: true },
  ],
  summary: {
    claims: 4,
    verdicts: { supported: 1, uncertain: 1, unknown: 2 },
    integrity_incidents: 1,
    corrective_nudges: 1,
  },
};

test("a well-formed report parses into a bounded judge-facing view", () => {
  const parsed = parseVerificationReport(report);
  assert.ok(parsed);
  assert.equal(parsed.claims.length, 2);
  assert.equal(parsed.claims[0]?.status, "supported");
  assert.deepEqual(parsed.claims[1]?.flaggedFiles, ["tests/test_core.py"]);
  assert.deepEqual(parsed.claims[1]?.evidence, [
    "acceptance file changed after baseline",
  ]);
  assert.equal(parsed.baselinesSealed, 1);
  assert.equal(parsed.baselineFiles, 3);
  assert.equal(parsed.integrityIncidents, 1);
  assert.equal(parsed.correctiveNudges, 1);
  assert.equal(parsed.verdicts.supported, 1);
  assert.equal(
    verificationSummaryLine(parsed),
    "2 claims adjudicated · 1 baseline sealed · 1 integrity incident · 1 corrective nudge",
  );
});

test("the report surface exists only for the exact schema and shape", () => {
  for (const payload of [
    null, "{}", 42, {},
    { ...report, schema: "pex.verification-report.v0" },
    { ...report, schema: undefined },
    { ...report, claims: "many" },
    { ...report, claims: [{}] },
    { ...report, claims: [{ at: "not-a-date", action_taken: "NOOP" }] },
    { ...report, claims: [{ at: report.claims[0].at }] },
  ]) {
    assert.equal(parseVerificationReport(payload), null);
  }
});

test("claims are bounded and hostile file paths are dropped", () => {
  const hostile = {
    ...report,
    claims: [
      {
        at: report.claims[0].at,
        action_taken: "SEND_NUDGE",
        verification_status: "uncertain",
        acceptance_surface: {
          modified: ["tests/ok.py", "../escape", "/abs/path", ""],
          deleted: [],
          added: [],
          added_config: [],
        },
      },
    ],
  };
  const parsed = parseVerificationReport(hostile);
  assert.ok(parsed);
  assert.deepEqual(parsed.claims[0]?.flaggedFiles, ["tests/ok.py"]);
});

test("claim evidence is bounded and non-string entries are dropped", () => {
  const noisy = {
    ...report,
    claims: [
      {
        at: report.claims[0].at,
        action_taken: "NOOP",
        verification_status: "supported",
        evidence: [
          "pytest_ok=true",
          42,
          null,
          { nested: true },
          "x".repeat(241),
          ...Array.from({ length: 10 }, (_, i) => `evidence_${i}`),
        ],
      },
    ],
  };
  const parsed = parseVerificationReport(noisy);
  assert.ok(parsed);
  const evidence = parsed.claims[0]?.evidence ?? [];
  // Only the first 8 raw entries are considered; non-strings/oversize drop out.
  assert.deepEqual(evidence, ["pytest_ok=true", "evidence_0", "evidence_1", "evidence_2"]);
});

test("verdict labels stay human-readable without inventing outcomes", () => {
  assert.equal(verificationVerdictLabel("supported"), "Verified");
  assert.equal(verificationVerdictLabel("contradicted"), "Contradicted");
  assert.equal(verificationVerdictLabel("uncertain"), "Uncertain");
  assert.equal(verificationVerdictLabel("unsatisfied"), "Unsatisfied");
  assert.equal(verificationVerdictLabel(null), "Observed");
  assert.equal(verificationVerdictLabel("some_future_status"), "some future status");
});

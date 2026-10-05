import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { canonicalJson, sha256Hex, verifyEvidencePack } from "./evidencePack.ts";

async function makePack(): Promise<Record<string, unknown>> {
  const sealed = "def test_core():\n    assert add(1, 1) == 2\n";
  const flagged = "def test_core():\n    pass\n";
  const event = { event_id: "e1", event_type: "stop", ts: "2026-01-01T00:00:00Z" };
  const eventSha = await sha256Hex(canonicalJson(event));
  const chain = await sha256Hex(`|${eventSha}`);
  const pack: Record<string, unknown> = {
    schema: "pex.evidence-pack.v1",
    goal_id: "goal_test",
    report: {
      schema: "pex.verification-report.v1",
      goal: { id: "goal_test" },
      claims: [{ verdict: "uncertain" }],
      summary: { claims: 1, integrity_incidents: 1, corrective_nudges: 1 },
    },
    acceptance_baselines: [
      {
        session_id: "synthetic:replay-test",
        files: { "tests/test_core.py": await sha256Hex(sealed) },
        contents: { "tests/test_core.py": sealed },
      },
    ],
    interventions: [
      {
        id: "intervention_abcdef012345",
        session_id: "synthetic:replay-test",
        action_taken: "SEND_NUDGE",
        policy_verdict: "allow",
        result: "sent",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    flagged: [
      {
        session_id: "synthetic:replay-test",
        intervention_id: "intervention_abcdef012345",
        contents: { "tests/test_core.py": flagged },
        flagged_sha256: { "tests/test_core.py": await sha256Hex(flagged) },
        acceptance_surface: { modified: ["tests/test_core.py"] },
      },
    ],
    event_ledger: [
      {
        session_id: "synthetic:replay-test",
        events: [{ event, sha256: eventSha }],
        count: 1,
        chain_sha256: chain,
      },
    ],
  };
  pack.manifest_sha256 = await sha256Hex(
    canonicalJson(Object.fromEntries(Object.entries(pack))),
  );
  return pack;
}

test("canonicalJson sorts keys by codepoint and drops spaces", () => {
  assert.equal(
    canonicalJson({ b: 1, a: [true, null], s: "x" }),
    '{"a":[true,null],"b":1,"s":"x"}',
  );
});

test("verifyEvidencePack passes a self-consistent pack", async () => {
  const checks = await verifyEvidencePack(await makePack());
  assert.ok(checks.length > 5);
  assert.ok(
    checks.every((line) => !line.startsWith("FAIL")),
    checks.filter((line) => line.startsWith("FAIL")).join("\n"),
  );
});

test("verifyEvidencePack catches a tampered flagged byte", async () => {
  const pack = await makePack();
  const entry = (pack.flagged as Record<string, unknown>[])[0];
  (entry.contents as Record<string, string>)["tests/test_core.py"] =
    "def test_core():\n    assert True\n";
  const checks = await verifyEvidencePack(pack);
  const failures = checks.filter((line) => line.startsWith("FAIL"));
  assert.ok(failures.length >= 2, "flagged bytes and manifest must both fail");
  assert.ok(failures.some((line) => line.includes("manifest digest")));
});

test("verifyEvidencePack re-verifies the committed drift pack", async () => {
  const url = new URL(
    "../../../docs/demo/evidence/EVIDENCE_PACK_drift_loop_2026-10-05.json",
    import.meta.url,
  );
  const pack = JSON.parse(await readFile(url, "utf-8")) as Record<string, unknown>;
  const checks = await verifyEvidencePack(pack);
  const failures = checks.filter((line) => line.startsWith("FAIL"));
  assert.deepEqual(failures, []);
  assert.ok(checks.some((line) => line.includes("hash chain reaches recorded head")));
});

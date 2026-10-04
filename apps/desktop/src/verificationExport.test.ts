import assert from "node:assert/strict";
import test from "node:test";

import { escapeHtml, renderVerificationReportHtml } from "./verificationExport.ts";

const report = {
  schema: "pex.verification-report.v1",
  generated_at: "2026-10-04T06:57:47.035061+00:00",
  goal: {
    id: "goal_1",
    project_id: "demo-eval",
    title: "Eval <pipeline>",
    objective: "Produce a complete evaluation",
    acceptance_criteria: ["tests pass"],
  },
  completion: {
    status: "verified_complete",
    reason: "current_intent_stop_evidence_supported",
    as_of: "2026-10-04T06:57:47.0Z",
    worker_narration_used: false,
  },
  claims: [
    {
      at: "2026-10-04T06:36:38.792743+00:00",
      action_taken: "SEND_NUDGE",
      verification_status: "uncertain",
      acceptance_surface: {
        modified: ["tests/test_core.py"],
        deleted: [],
        added: [],
        added_config: [],
        baselined: true,
      },
      evidence: ["acceptance_surface_modified:tests/test_core.py"],
    },
  ],
  claims_scanned: 1,
  acceptance_baselines: [
    {
      session_id: "s1",
      sealed_at: "2026-10-04T06:36:28.9Z",
      sealed_context: "event:user_prompt",
      files: 3,
      files_complete: true,
    },
  ],
  summary: {
    claims: 1,
    verdicts: { uncertain: 1 },
    integrity_incidents: 1,
    corrective_nudges: 1,
  },
};

test("escapeHtml neutralizes markup-significant characters", () => {
  assert.equal(escapeHtml(`<img src=x onerror="a">'`), "&lt;img src=x onerror=&quot;a&quot;&gt;&#39;");
});

test("rendered report escapes hostile goal text but keeps the verdict story", () => {
  const html = renderVerificationReportHtml(report);
  assert.ok(html.includes("&lt;pipeline&gt;"));
  assert.ok(!html.includes("<pipeline>"));
  assert.ok(html.includes("UNCERTAIN".toLowerCase()));
  assert.ok(html.includes("acceptance_surface_modified:tests/test_core.py"));
  assert.ok(html.includes("verified_complete"));
});

test("the raw payload embeds machine-checkable JSON with '<' escaped", () => {
  const hostile = {
    ...report,
    goal: { ...report.goal, title: "x</script><script>alert(1)</script>" },
  };
  const html = renderVerificationReportHtml(hostile);
  const match = html.match(/<script type="application\/json" id="pex-report">([\s\S]*?)<\/script>/);
  assert.ok(match);
  assert.ok(!match[1].includes("</script>"));
  const embedded = JSON.parse(match[1]) as { goal: { title: string } };
  assert.equal(embedded.goal.title, "x</script><script>alert(1)</script>");
  // Rendered text still escapes the title.
  assert.ok(html.includes("x&lt;/script&gt;"));
});

test("sparse payloads render honestly empty rather than inventing values", () => {
  const html = renderVerificationReportHtml({ schema: "pex.verification-report.v1" });
  assert.ok(html.includes("not adjudicated"));
  assert.ok(html.includes("untitled goal"));
  assert.ok(html.includes("no verdict summary"));
});

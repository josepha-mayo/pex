// Standalone verification-report export: renders the bridge's raw
// pex.verification-report.v1 payload into a self-contained HTML document a
// reviewer can open without PEX. The raw JSON rides inside a <script
// type="application/json"> tag so the artifact doubles as the machine-checkable
// record — nothing is re-stated beyond what the bridge reported.

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown, max = 400): string {
  return typeof value === "string" && value ? escapeHtml(value.slice(0, max)) : "";
}

function number(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "";
}

function evidenceList(value: unknown): string {
  if (!Array.isArray(value)) return "";
  const items = value.filter(
    (item): item is string => typeof item === "string" && item.length > 0,
  );
  return items.length
    ? `<ul class="evidence">${items.map((item) => `<li><code>${text(item, 240)}</code></li>`).join("")}</ul>`
    : "";
}

function claimRow(raw: unknown): string {
  if (!isRecord(raw)) return "";
  const at = text(raw.at, 64);
  const action = text(raw.action_taken, 64) || "observed";
  const status = text(raw.verification_status, 64) || "observed";
  const surface = isRecord(raw.acceptance_surface) ? raw.acceptance_surface : {};
  const flaggedPaths = [
    ...(Array.isArray(surface.modified) ? surface.modified : []),
    ...(Array.isArray(surface.deleted) ? surface.deleted : []),
    ...(Array.isArray(surface.added) ? surface.added : []),
    ...(Array.isArray(surface.added_config) ? surface.added_config : []),
  ].filter((item): item is string => typeof item === "string" && item.length > 0);
  const flagged = [...new Set(flaggedPaths)]
    .map((item) => `<code>${text(item, 240)}</code>`)
    .join(" ");
  const surfaceNote = isRecord(raw.acceptance_surface)
    ? [
        surface.baselined === true ? "baselined" : "",
        surface.sealed_at_claim === true ? "sealed at claim" : "",
        text(surface.reason, 120),
      ]
        .filter(Boolean)
        .join(" · ")
    : "";
  const evidence = evidenceList(raw.evidence);
  const statements = Array.isArray(raw.claim_statements)
    ? raw.claim_statements
        .filter((item): item is string => typeof item === "string" && item.length > 0)
        .slice(0, 6)
        .map((item) => `<li class="claim-statement">&ldquo;${text(item, 240)}&rdquo;</li>`)
        .join("")
    : "";
  const quoted = statements ? `<ul class="evidence claim-statements">${statements}</ul>` : "";
  const detail = [
    quoted,
    flagged,
    surfaceNote ? `<span class="muted">${surfaceNote}</span>` : "",
    evidence,
  ]
    .filter(Boolean)
    .join("");
  return `<tr><td class="status status-${status}">${status}</td><td>${action}</td><td>${at}</td><td>${detail}</td></tr>`;
}

function baselineRow(raw: unknown): string {
  if (!isRecord(raw)) return "";
  return `<tr><td>${text(raw.session_id, 80)}</td><td>${text(raw.sealed_at, 64)}</td><td>${text(raw.sealed_context, 64)}</td><td>${number(raw.files)}</td><td>${raw.files_complete === true ? "yes" : raw.files_complete === false ? "no" : ""}</td></tr>`;
}

// The exported page repeats only fields the bridge itself reported; unknown or
// absent fields render as empty cells rather than invented values.
export function renderVerificationReportHtml(payload: Record<string, unknown>): string {
  const goal = isRecord(payload.goal) ? payload.goal : {};
  const completion = isRecord(payload.completion) ? payload.completion : {};
  const summary = isRecord(payload.summary) ? payload.summary : {};
  const verdicts = isRecord(summary.verdicts) ? summary.verdicts : {};
  const claims = Array.isArray(payload.claims) ? payload.claims : [];
  const baselines = Array.isArray(payload.acceptance_baselines)
    ? payload.acceptance_baselines
    : [];
  const verdictSummary = Object.entries(verdicts)
    .filter(([, count]) => typeof count === "number")
    .map(([verdict, count]) => `${escapeHtml(verdict)} ${String(count)}`)
    .join(" · ");
  const rawJson = JSON.stringify(payload, null, 2).replace(/</g, "\\u003c");
  const replayNote = "Recorded replay sessions are labeled not live worker control in PEX.";

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>PEX verification report — ${text(goal.title, 120) || "goal"}</title>
<style>
body{font-family:ui-sans-serif,system-ui,sans-serif;background:#0d1117;color:#dbe3ee;margin:0;padding:32px;line-height:1.5}
main{max-width:860px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#7f8ca0;margin:28px 0 8px}
.muted{color:#7f8ca0;font-size:12px}
.card{border:1px solid #232b38;border-radius:10px;padding:16px 20px;background:#131922;margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:12px}
td,th{border-top:1px solid #232b38;padding:8px 10px;text-align:left;vertical-align:top}
code{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:11px;background:rgba(127,156,255,.08);border:1px solid #232b38;border-radius:4px;padding:1px 6px}
.status{font-weight:700;text-transform:uppercase;font-size:10px;letter-spacing:.04em}
.status-supported{color:#4ade80}.status-contradicted,.status-unsatisfied{color:#f87171}.status-uncertain{color:#fbbf24}.status-observed{color:#7f8ca0}
.evidence{margin:4px 0 0;padding-left:16px}.evidence li{margin:2px 0}
.claim-statement{font-style:italic;color:#dbe3ee}
details{margin-top:24px}summary{cursor:pointer;color:#7f8ca0;font-size:12px}
pre{white-space:pre-wrap;word-break:break-word;font-size:11px;background:#0a0f16;border:1px solid #232b38;border-radius:8px;padding:12px;max-height:480px;overflow:auto}
.meta{font-size:12px;color:#7f8ca0}
</style></head><body><main>
<h1>PEX verification report</h1>
<p class="meta">${text(payload.schema, 80) || "pex.verification-report.v1"} · generated ${text(payload.generated_at, 64)}</p>
<p class="muted">${replayNote}</p>
<section class="card"><h2>Goal</h2>
<p><strong>${text(goal.title, 200) || "untitled goal"}</strong></p>
<p class="muted">${text(goal.objective, 400)}</p>
<p class="meta">project ${text(goal.project_id, 80)} · goal ${text(goal.id, 80)}</p>
</section>
<section class="card"><h2>Completion</h2>
<p class="status status-${text(completion.status, 64) || "observed"}">${text(completion.status, 64) || "not adjudicated"}</p>
<p class="muted">${text(completion.reason, 200)} · as of ${text(completion.as_of, 64)}</p>
<p class="meta">worker narration used: ${completion.worker_narration_used === true ? "yes" : "no"} · claims scanned ${number(payload.claims_scanned)}</p>
</section>
<section class="card"><h2>Claim verdicts</h2>
<p class="meta">${verdictSummary || "no verdict summary"}</p>
<table><thead><tr><th>verdict</th><th>action</th><th>at</th><th>acceptance surface · evidence</th></tr></thead>
<tbody>${claims.map(claimRow).join("")}</tbody></table>
</section>
<section class="card"><h2>Sealed acceptance baselines</h2>
<table><thead><tr><th>session</th><th>sealed at</th><th>context</th><th>files</th><th>complete</th></tr></thead>
<tbody>${baselines.map(baselineRow).join("")}</tbody></table>
</section>
<details><summary>Raw report JSON (${text(payload.schema, 80)})</summary>
<pre id="raw"></pre>
<script type="application/json" id="pex-report">${rawJson}</script>
<script>document.getElementById("raw").textContent=JSON.stringify(JSON.parse(document.getElementById("pex-report").textContent),null,2)</script>
</details>
</main></body></html>`;
}

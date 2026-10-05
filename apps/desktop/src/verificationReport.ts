// Per-goal claim verification report: the bridge's typed verdict ledger for
// one goal — every completion claim, its independent verdict, the acceptance
// files that anchored it, and any integrity incidents. Rendered read-only; a
// malformed payload removes the block rather than showing partial claims.

export type VerificationClaim = {
  at: string;
  action: string;
  status: string | null;
  flaggedFiles: string[];
  evidence: string[];
  statements: string[];
};

export type VerificationReportView = {
  generatedAt: string;
  claims: VerificationClaim[];
  claimsScanned: number;
  claimsTruncated: boolean;
  baselinesSealed: number;
  baselineFiles: number;
  verdicts: Record<string, number>;
  integrityIncidents: number;
  correctiveNudges: number;
};

const MAX_CLAIMS = 64;
const MAX_FLAGGED = 8;
const MAX_PATH = 240;
const MAX_EVIDENCE = 8;
const MAX_EVIDENCE_LEN = 240;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && value.length <= 64 && !Number.isNaN(Date.parse(value));
}

function parseFileList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const files: string[] = [];
  for (const raw of value.slice(0, MAX_FLAGGED)) {
    if (typeof raw !== "string" || !raw || raw.length > MAX_PATH || raw.startsWith("/") || raw.includes("..")) {
      continue;
    }
    files.push(raw);
  }
  return files;
}

function parseEvidenceList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const evidence: string[] = [];
  for (const raw of value.slice(0, MAX_EVIDENCE)) {
    if (typeof raw !== "string" || !raw || raw.length > MAX_EVIDENCE_LEN) continue;
    evidence.push(raw);
  }
  return evidence;
}

function parseClaim(raw: unknown): VerificationClaim | null {
  if (!isRecord(raw)) return null;
  const at = raw.at;
  const action = raw.action_taken;
  if (!isTimestamp(at) || typeof action !== "string" || !action || action.length > 64) {
    return null;
  }
  const status = raw.verification_status;
  const surface = isRecord(raw.acceptance_surface) ? raw.acceptance_surface : {};
  const flagged = [
    ...parseFileList(surface.modified),
    ...parseFileList(surface.deleted),
    ...parseFileList(surface.added),
    ...parseFileList(surface.added_config),
  ];
  return {
    at,
    action,
    status: typeof status === "string" && status.length <= 64 ? status : null,
    flaggedFiles: [...new Set(flagged)].slice(0, MAX_FLAGGED),
    evidence: parseEvidenceList(raw.evidence),
    statements: parseEvidenceList(raw.claim_statements).slice(0, 6),
  };
}

function parseVerdicts(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {};
  const verdicts: Record<string, number> = {};
  for (const [key, count] of Object.entries(value)) {
    if (
      typeof key === "string" && key.length <= 64
      && typeof count === "number" && Number.isInteger(count) && count >= 0 && count <= 1_000_000
    ) {
      verdicts[key] = count;
    }
  }
  return verdicts;
}

// The report exists only while it honestly describes one goal's ledger: the
// exact schema marker, a bounded claim list, and numeric summary. Anything
// else — a partial shape, a foreign schema, an unbounded payload — removes
// the surface entirely rather than implying evidence that was not verified.
export function parseVerificationReport(payload: unknown): VerificationReportView | null {
  if (!isRecord(payload) || payload.schema !== "pex.verification-report.v1") return null;
  if (!Array.isArray(payload.claims) || payload.claims.length > MAX_CLAIMS) return null;
  const claims: VerificationClaim[] = [];
  for (const raw of payload.claims) {
    const claim = parseClaim(raw);
    if (!claim) return null;
    claims.push(claim);
  }
  const summary = isRecord(payload.summary) ? payload.summary : {};
  const nonnegative = (value: unknown): number =>
    typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 1_000_000 ? value : 0;
  const baselines = Array.isArray(payload.acceptance_baselines) ? payload.acceptance_baselines : [];
  const baselineFiles = baselines.reduce((total, raw) => {
    const files = isRecord(raw) && typeof raw.files === "number" ? raw.files : 0;
    return total + (Number.isInteger(files) && files >= 0 && files <= 10_000 ? files : 0);
  }, 0);
  return {
    generatedAt: isTimestamp(payload.generated_at) ? payload.generated_at : "",
    claims,
    claimsScanned: nonnegative(payload.claims_scanned),
    claimsTruncated: payload.claims_truncated === true,
    baselinesSealed: baselines.length,
    baselineFiles,
    verdicts: parseVerdicts(summary.verdicts),
    integrityIncidents: nonnegative(summary.integrity_incidents),
    correctiveNudges: nonnegative(summary.corrective_nudges),
  };
}

export function verificationVerdictLabel(status: string | null): string {
  if (status === "supported") return "Verified";
  if (status === "contradicted") return "Contradicted";
  if (status === "uncertain") return "Uncertain";
  if (status === "unsatisfied") return "Unsatisfied";
  return status ? status.replace(/_/g, " ") : "Observed";
}

export function verificationSummaryLine(report: VerificationReportView): string {
  const parts = [
    `${report.claims.length} claim${report.claims.length === 1 ? "" : "s"} adjudicated`,
    `${report.baselinesSealed} baseline${report.baselinesSealed === 1 ? "" : "s"} sealed`,
  ];
  if (report.integrityIncidents > 0) {
    parts.push(
      `${report.integrityIncidents} integrity incident${report.integrityIncidents === 1 ? "" : "s"}`,
    );
  }
  if (report.correctiveNudges > 0) {
    parts.push(`${report.correctiveNudges} corrective nudge${report.correctiveNudges === 1 ? "" : "s"}`);
  }
  if (report.claimsTruncated) parts.push("oldest claims truncated");
  return parts.join(" · ");
}

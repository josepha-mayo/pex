export const MAX_RESPONSE_BYTES = 16_384;
export type ReplayResult = {
  schema_version: "pex.replay-job.v1";
  fixture_id: string;
  replay: true;
  not_live_control: true;
  execution_mode: "local_deterministic_replay";
  inference_status: "not_attempted";
  completion_status: string;
  completion_reason: string;
  claim_verdicts: { claim: string; status: string }[];
  evidence_summary: string[];
  verification_sequence: { status: string; modified_acceptance_files: string[] }[];
  interventions: string[];
  events_adjudicated: number;
  claims_adjudicated: number;
  integrity_incidents: number;
  declared_expectation_met: boolean;
};
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== keys.length || !keys.every((key) => Object.hasOwn(value, key))) throw new Error("invalid_response");
  return value as Record<string, unknown>;
}
function string(value: unknown, limit: number): void {
  if (typeof value !== "string" || [...value].length > limit) throw new Error("invalid_response");
}
function list(value: unknown, limit: number, check: (item: unknown) => void): void {
  if (!Array.isArray(value) || value.length > limit) throw new Error("invalid_response");
  value.forEach(check);
}
export function parseResult(value: unknown, fixture: string): ReplayResult {
  const v = object(value, ["schema_version", "fixture_id", "replay", "not_live_control", "execution_mode", "inference_status", "completion_status", "completion_reason", "claim_verdicts", "evidence_summary", "verification_sequence", "interventions", "events_adjudicated", "claims_adjudicated", "integrity_incidents", "declared_expectation_met"]);
  if (new TextEncoder().encode(JSON.stringify(value)).length > MAX_RESPONSE_BYTES) throw new Error("response_too_large");
  if (v.schema_version !== "pex.replay-job.v1" || v.fixture_id !== fixture || !["premature_stop_eval", "tampered_acceptance_eval"].includes(fixture) || v.replay !== true || v.not_live_control !== true || v.execution_mode !== "local_deterministic_replay" || v.inference_status !== "not_attempted" || typeof v.declared_expectation_met !== "boolean") throw new Error("invalid_response");
  string(v.completion_status, 64); string(v.completion_reason, 400);
  if (!["verified_complete", "incomplete", "in_progress", "uncertain"].includes(String(v.completion_status))) throw new Error("invalid_response");
  const status = (value: unknown) => { if (!["supported", "contradicted", "acceptance_gap", "no_claims", "uncertain"].includes(String(value))) throw new Error("invalid_response"); };
  list(v.claim_verdicts, 5, (item) => { const c = object(item, ["claim", "status"]); string(c.claim, 200); string(c.status, 32); status(c.status); });
  list(v.evidence_summary, 4, (item) => string(item, 160));
  list(v.verification_sequence, 16, (item) => { const c = object(item, ["status", "modified_acceptance_files"]); string(c.status, 32); status(c.status); list(c.modified_acceptance_files, 16, (file) => string(file, 240)); });
  list(v.interventions, 32, (item) => string(item, 64));
  for (const key of ["events_adjudicated", "claims_adjudicated", "integrity_incidents"]) if (!Number.isInteger(v[key]) || Number(v[key]) < 0 || Number(v[key]) > 1000) throw new Error("invalid_response");
  return v as ReplayResult;
}
// Bound the response before JSON decoding, including absent/incorrect Content-Length.
export async function readBoundedJson(response: Response): Promise<unknown> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("invalid_response");
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    if (Number(response.headers.get("content-length")) > MAX_RESPONSE_BYTES) throw new Error("response_too_large");
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) throw new Error("response_too_large");
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    try { return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
    catch { throw new Error("invalid_response"); }
  } finally { await reader.cancel(); reader.releaseLock(); }
}

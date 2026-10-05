// Browser-side re-verification of a pex.evidence-pack.v1 bundle.
//
// Mirrors scripts/verify_pack.py: recomputes every digest the pack asserts —
// sealed baseline contents, flagged incident bytes, the per-session event
// hash chain, and the manifest — with WebCrypto, so a downloaded receipt can
// be checked inside the app without trusting the bridge. A PASS is an
// internal-consistency proof only; it is not proof a live worker ran.
//
// The canonical form must match Python's
//   json.dumps(v, ensure_ascii=False, sort_keys=True,
//              separators=(",", ":"), allow_nan=False)
// exactly, byte for byte: keys sort by Unicode codepoint, strings escape only
// what JSON requires, and numbers use their shortest round-trip form. A pack
// containing an integral *float* (e.g. 1.0) cannot round-trip through JS
// numbers and will report a digest mismatch — the CLI verifier remains the
// authoritative check for that edge case.

function compareCodepoints(a: string, b: string): number {
  const ca = Array.from(a);
  const cb = Array.from(b);
  const shared = Math.min(ca.length, cb.length);
  for (let i = 0; i < shared; i += 1) {
    const diff = (ca[i].codePointAt(0) ?? 0) - (cb[i].codePointAt(0) ?? 0);
    if (diff !== 0) return diff;
  }
  return ca.length - cb.length;
}

export function canonicalJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("non-finite number in pack");
    return String(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => compareCodepoints(a, b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`);
    return `{${entries.join(",")}}`;
  }
  throw new Error("unsupported pack value");
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export async function verifyEvidencePack(pack: Record<string, unknown>): Promise<string[]> {
  const checks: string[] = [];
  const check = (ok: boolean, label: string) => {
    checks.push(`${ok ? "PASS" : "FAIL"} ${label}`);
  };

  check(pack.schema === "pex.evidence-pack.v1", "schema is pex.evidence-pack.v1");

  const manifest = pack.manifest_sha256;
  if (typeof manifest === "string") {
    const rest = Object.fromEntries(
      Object.entries(pack).filter(([key]) => key !== "manifest_sha256"),
    );
    const recomputed = await sha256Hex(canonicalJson(rest));
    check(manifest === recomputed, `manifest digest recomputes (${manifest.slice(0, 16)}..)`);
  } else {
    check(false, "manifest_sha256 present");
  }

  const report = record(pack.report);
  check(
    report.schema === "pex.verification-report.v1",
    "embedded verification report present",
  );
  const goalId = pack.goal_id;
  check(
    record(report.goal).id === goalId,
    "report goal matches pack goal",
  );

  const baselineBySession = new Map<string, Record<string, unknown>>();
  for (const baseline of list(pack.acceptance_baselines).map(record)) {
    const sid = str(baseline.session_id);
    baselineBySession.set(sid, baseline);
    const files = record(baseline.files);
    const contents = record(baseline.contents);
    let matched = 0;
    for (const path of Object.keys(files).sort(compareCodepoints)) {
      const digest = files[path];
      if (typeof digest !== "string") continue;
      const text = contents[path];
      if (text === undefined || text === null) {
        checks.push(`NOTE ${sid} ${path}: digest sealed, no content bundled`);
        continue;
      }
      const ok = typeof text === "string" && (await sha256Hex(text)) === digest;
      if (ok) matched += 1;
      check(ok, `baseline ${sid.slice(0, 24)}.. ${path}: content matches sealed digest`);
    }
    check(
      Object.keys(files).length > 0,
      `baseline ${sid.slice(0, 24)}.. carries file digests (${Object.keys(files).length})`,
    );
    if (matched) checks.push(`INFO ${sid.slice(0, 24)}.. ${matched} sealed file(s) verified`);
  }

  for (const entry of list(pack.flagged).map(record)) {
    const sid = str(entry.session_id);
    const iid = str(entry.intervention_id).slice(0, 16);
    const contents = record(entry.contents);
    const digests = record(entry.flagged_sha256);
    const surface = record(entry.acceptance_surface);
    const modified = new Set(list(surface.modified).map(str));
    const sealed = record(baselineBySession.get(sid)?.files);
    for (const path of Object.keys(contents).sort(compareCodepoints)) {
      const text = contents[path];
      const digest = digests[path];
      check(
        typeof digest === "string" &&
          typeof text === "string" &&
          (await sha256Hex(text)) === digest,
        `flagged ${iid}.. ${path}: bundled bytes match incident digest`,
      );
      if (modified.has(path) && typeof sealed[path] === "string") {
        check(
          digests[path] !== sealed[path],
          `flagged ${iid}.. ${path}: digest differs from sealed baseline`,
        );
      }
      if (modified.has(path) && sealed[path] === undefined) {
        checks.push(`NOTE ${iid}.. ${path}: flagged modified but no sealed digest to compare`);
      }
    }
  }

  for (const ledger of list(pack.event_ledger).map(record)) {
    const sid = str(ledger.session_id);
    let chain = "";
    let count = 0;
    for (const entry of list(ledger.events).map(record)) {
      const eventSha = await sha256Hex(canonicalJson(entry.event));
      check(eventSha === entry.sha256, `ledger ${sid.slice(0, 24)}.. event ${count}: payload hash matches`);
      chain = await sha256Hex(`${chain}|${eventSha}`);
      count += 1;
    }
    check(count === ledger.count, `ledger ${sid.slice(0, 24)}.. event count consistent`);
    check(
      chain === ledger.chain_sha256,
      `ledger ${sid.slice(0, 24)}.. hash chain reaches recorded head`,
    );
    if (ledger.truncated) {
      checks.push(`NOTE ${sid.slice(0, 24)}.. ledger truncated at the export cap`);
    }
  }

  const claims = list(report.claims);
  check(
    claims.length === record(report.summary).claims,
    "claim count consistent",
  );

  const interventions = list(pack.interventions).map(record);
  const ids = interventions.map((item) => item.id);
  check(
    ids.length === new Set(ids).size,
    `intervention ids unique (${ids.length} records)`,
  );
  const flaggedIds = new Set(
    list(pack.flagged).map((entry) => str(record(entry).intervention_id)),
  );
  check(
    [...flaggedIds].every((id) => ids.includes(id)),
    "every flagged incident references a bundled intervention",
  );
  return checks;
}

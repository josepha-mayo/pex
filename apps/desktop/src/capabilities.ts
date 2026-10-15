import type { AdapterRow, BenchState, SupervisorInfo } from "./types";

export type CapabilityStatus =
  | "implemented"
  | "live"
  | "configured"
  | "key-gated"
  | "unfrozen"
  | "unavailable"
  | "not deployed";

export type CapabilityRow = {
  capability: string;
  status: CapabilityStatus;
  detail: string;
};

export const CAPABILITY_STATUS_LABEL: Record<CapabilityStatus, string> = {
  implemented: "Implemented",
  live: "Live now",
  configured: "Configured",
  "key-gated": "Key-gated",
  unfrozen: "Unfrozen",
  unavailable: "Unavailable",
  "not deployed": "Not deployed",
};

export const CAPABILITY_STATUS_CLASS: Record<CapabilityStatus, string> = {
  implemented: "cap-ok",
  live: "cap-ok",
  configured: "cap-warn",
  "key-gated": "cap-warn",
  unfrozen: "cap-warn",
  unavailable: "cap-bad",
  "not deployed": "cap-bad",
};

// Provider ids are opaque to a judge; the platform the hackathon asks about
// gets its real name, everyone else renders raw.
const PROVIDER_LABEL: Record<string, string> = {
  nebius: "Nebius Token Factory",
};

function providerLabel(provider?: string | null, backend?: string | null): string {
  const raw = provider || backend || "Configured backend";
  return PROVIDER_LABEL[raw] || raw;
}

function supervisorRow(supervisor: SupervisorInfo | null): CapabilityRow {
  if (!supervisor) {
    return {
      capability: "Model-assisted supervision",
      status: "unavailable",
      detail: "The supervisor endpoint did not report. Deterministic review still adjudicates events.",
    };
  }
  if (supervisor.model_loaded === true) {
    return {
      capability: "Model-assisted supervision",
      status: "live",
      detail: `${providerLabel(supervisor.provider, supervisor.backend)} · ${supervisor.model_id || "model not reported"} — a model actually loaded.`,
    };
  }
  if (supervisor.credential_configured === true || supervisor.has_api_key === true) {
    return {
      capability: "Model-assisted supervision",
      status: "configured",
      detail: `${providerLabel(supervisor.provider, supervisor.backend)} credentials are stored; the model is not active yet (${supervisor.activation_status || "status unreported"}).`,
    };
  }
  return {
    capability: "Model-assisted supervision",
    status: "key-gated",
    detail: "No model credential is configured — PEX falls back to deterministic adjudication and says so on each decision.",
  };
}

function adapterRows(adapters: AdapterRow[] | undefined): CapabilityRow[] {
  if (adapters === undefined) {
    return [{
      capability: "Live worker control",
      status: "unavailable",
      detail: "Adapter probes have not landed on this screen yet — refresh in a moment rather than inferring a state.",
    }];
  }
  if (!adapters.length) {
    return [{
      capability: "Live worker control",
      status: "unavailable",
      detail: "The bridge reported no adapters. Recorded replays still run — they are labelled, deterministic trajectories.",
    }];
  }
  return adapters.map((adapter) => {
    const label = adapter.capabilities?.support_label || "unavailable";
    const live = label === "deep" || label === "strong" || label === "basic";
    const notes = adapter.capabilities?.notes?.trim();
    return {
      capability: `Worker control · ${adapter.name}`,
      status: live ? "live" : "unavailable",
      detail: live
        ? `Probed ${label} support just now — capability flags below were negotiated, not assumed.${notes ? ` ${notes}` : ""}`
        : `Probe reported ${label}. PEX does not claim control it could not observe.${notes ? ` ${notes}` : ""}`,
    };
  });
}

function benchRow(bench: BenchState | null | undefined): CapabilityRow {
  if (!bench) {
    return {
      capability: "Formal benchmark (PexBench)",
      status: "unavailable",
      detail: "The bench endpoint did not respond.",
    };
  }
  if (bench.runs.length > 0) {
    const frozen = bench.runs.every((run) => run.frozen);
    return {
      capability: "Formal benchmark (PexBench)",
      status: frozen ? "implemented" : "unfrozen",
      detail: frozen
        ? `${bench.runs.length} manifest-frozen run${bench.runs.length === 1 ? "" : "s"} on record.`
        : "Run data exists but is not manifest-frozen — shown as unfrozen, never as a score.",
    };
  }
  return {
    capability: "Formal benchmark (PexBench)",
    status: "unfrozen",
    detail: `${bench.message ? `${bench.message} ` : ""}No frozen benchmark is claimed. The recorded-replay suite is evidence, not a score.`,
  };
}

export function capabilityRows({
  adapters,
  supervisor,
  bench,
  fixtureCount,
  unauthenticatedOperator,
}: {
  adapters?: AdapterRow[];
  supervisor: SupervisorInfo | null;
  bench?: BenchState | null;
  fixtureCount: number | null;
  unauthenticatedOperator: boolean;
}): CapabilityRow[] {
  return [
    {
      capability: "Deterministic replay supervision",
      status: fixtureCount === null ? "unavailable" : "implemented",
      detail: fixtureCount === null
        ? "The replay fixture endpoint did not respond."
        : `${fixtureCount} labelled recorded fixtures on this bridge — deterministic, never live worker control.`,
    },
    {
      capability: "Independent workspace verification",
      status: "implemented",
      detail: "Claims adjudicate against sealed baselines and observed evidence — worker narration alone never closes a run.",
    },
    supervisorRow(supervisor),
    ...adapterRows(adapters),
    {
      capability: "MCP tool surface",
      status: "implemented",
      detail: "A scoped Model Context Protocol server is mounted at /mcp — workers with session-bound credentials can read their goal and project state, verify claims, report progress, request decisions, or hand off; local anonymous calls are read-only.",
    },
    benchRow(bench),
    {
      capability: "Isolated public-test sandbox (Nebius ConTree)",
      status: "key-gated",
      detail: "Contract-gated: runs only with Sandboxes credentials; a configured-but-unavailable sandbox reports its error instead of silently falling back.",
    },
    {
      capability: "Packaged desktop release",
      status: unauthenticatedOperator ? "not deployed" : "implemented",
      detail: unauthenticatedOperator
        ? "This build is the test-scoped demo bridge — unauthenticated operator, loopback only. The packaged Tauri app enforces a launcher-owned bearer token."
        : "Authenticated bridge — operator controls require the launcher token.",
    },
  ];
}

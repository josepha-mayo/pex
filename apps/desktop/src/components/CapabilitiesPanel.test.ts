import test from "node:test";
import assert from "node:assert/strict";

import { capabilityRows } from "../capabilities.ts";

function rowFor(rows: ReturnType<typeof capabilityRows>, capability: string) {
  const row = rows.find((item) => item.capability === capability);
  assert.ok(row, `missing row: ${capability}`);
  return row;
}

test("capabilities are derived from live state, never assumed", () => {
  const rows = capabilityRows({
    adapters: [
      { name: "opencode", capabilities: { support_label: "deep", notes: "connected" } },
      { name: "cursor", capabilities: { support_label: "unavailable" } },
    ],
    supervisor: { model_loaded: false, credential_configured: false },
    bench: { loading: false, runs: [], message: "No coherent frozen benchmark run has been published." },
    fixtureCount: 15,
    unauthenticatedOperator: true,
  });

  assert.equal(rowFor(rows, "Deterministic replay supervision").status, "implemented");
  assert.match(rowFor(rows, "Deterministic replay supervision").detail, /15 labelled recorded fixtures/);
  assert.equal(rowFor(rows, "Model-assisted supervision").status, "key-gated");
  assert.equal(rowFor(rows, "Worker control · opencode").status, "live");
  assert.equal(rowFor(rows, "Worker control · cursor").status, "unavailable");
  assert.match(rowFor(rows, "Worker control · cursor").detail, /does not claim control it could not observe/);
  assert.equal(rowFor(rows, "Formal benchmark (PexBench)").status, "unfrozen");
  assert.equal(rowFor(rows, "Packaged desktop release").status, "not deployed");
});

test("a loaded model reports live; stored credentials without a model report configured", () => {
  const live = capabilityRows({
    adapters: [],
    supervisor: { model_loaded: true, provider: "nebius", model_id: "nemotron-3-super" },
    fixtureCount: 1,
    unauthenticatedOperator: false,
  });
  const liveRow = rowFor(live, "Model-assisted supervision");
  assert.equal(liveRow.status, "live");
  assert.match(liveRow.detail, /nebius/);
  assert.match(liveRow.detail, /actually loaded/);

  const configured = capabilityRows({
    adapters: [],
    supervisor: { model_loaded: false, credential_configured: true, provider: "zen", activation_status: "unavailable" },
    fixtureCount: 1,
    unauthenticatedOperator: false,
  });
  assert.equal(rowFor(configured, "Model-assisted supervision").status, "configured");
});

test("unloaded adapter state is not claimed as absent", () => {
  const rows = capabilityRows({
    adapters: undefined,
    supervisor: null,
    fixtureCount: null,
    unauthenticatedOperator: false,
  });
  assert.match(rowFor(rows, "Live worker control").detail, /have not landed/);
  assert.equal(rowFor(rows, "Deterministic replay supervision").status, "unavailable");
  assert.equal(rowFor(rows, "Model-assisted supervision").status, "unavailable");
});

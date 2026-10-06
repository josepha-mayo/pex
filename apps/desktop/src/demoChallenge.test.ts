import assert from "node:assert/strict";
import test from "node:test";

import {
  CHALLENGE_PRESETS,
  CHALLENGE_TEMPLATE,
  parseChallengeFixture,
} from "./demoChallenge.ts";

void test("challenge template parses into a runnable fixture body", () => {
  const parsed = parseChallengeFixture(CHALLENGE_TEMPLATE);
  assert.equal(parsed.ok, true);
  if (parsed.ok) {
    assert.ok(Array.isArray(parsed.fixture.events));
    assert.ok(parsed.fixture.events.length > 0);
  }
});

void test("challenge parser rejects unusable bodies before the round-trip", () => {
  for (const [input, match] of [
    ["", /Paste a fixture/],
    ["   ", /Paste a fixture/],
    ["not json", /Invalid JSON/],
    ["[1,2,3]", /must be a JSON object/],
    ['"text"', /must be a JSON object/],
    ['{"events": []}', /non-empty events array/],
    ['{"events": "nope"}', /non-empty events array/],
    [`{"x":"${"a".repeat(1_100_000)}"}`, /1 MiB/],
  ] as const) {
    const parsed = parseChallengeFixture(input);
    assert.equal(parsed.ok, false, input.slice(0, 40));
    if (!parsed.ok) assert.match(parsed.error, match);
  }
});

void test("challenge parser accepts a minimal fixture", () => {
  const parsed = parseChallengeFixture(
    '{"events": [{"event_type": "stop"}]}',
  );
  assert.equal(parsed.ok, true);
});

void test("every attack preset is a parseable, labeled fixture", () => {
  const labels = new Set<string>();
  for (const preset of CHALLENGE_PRESETS) {
    assert.ok(preset.label.trim(), "preset needs a label");
    assert.ok(!labels.has(preset.label), `duplicate preset label ${preset.label}`);
    labels.add(preset.label);
    const parsed = parseChallengeFixture(preset.json);
    assert.equal(parsed.ok, true, `${preset.label}: ${parsed.ok ? "" : parsed.error}`);
  }
  assert.ok(CHALLENGE_PRESETS.length >= 3, "presets should cover multiple attack classes");
});

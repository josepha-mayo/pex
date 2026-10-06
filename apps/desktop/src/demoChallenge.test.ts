import assert from "node:assert/strict";
import test from "node:test";

import { CHALLENGE_TEMPLATE, parseChallengeFixture } from "./demoChallenge.ts";

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

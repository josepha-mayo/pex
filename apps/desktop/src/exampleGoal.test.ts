import assert from "node:assert/strict";
import test from "node:test";
import { EXAMPLE_GOAL, mergeExampleGoal } from "./exampleGoal.ts";
import type { GoalDraft } from "./components/GoalEditor";

const blank: GoalDraft = {
  projectId: "proj-1",
  title: "",
  objective: "",
  observationOnly: false,
  acceptance: "",
  constraints: "",
  forbiddenOutcomes: "",
  nonGoals: "",
  preferences: "",
  deadline: "",
  evidence: "",
  decisions: "",
  rejectedApproaches: "",
  unresolvedQuestions: "",
};

test("example goal exercises the supervision-relevant fields", () => {
  // The example exists to show judges what a verifiable goal looks like —
  // acceptance, forbidden outcomes, and non-goals must never ship empty.
  assert.ok(EXAMPLE_GOAL.objective.trim());
  assert.ok(EXAMPLE_GOAL.acceptance.trim());
  assert.ok(EXAMPLE_GOAL.forbiddenOutcomes?.trim());
  assert.ok(EXAMPLE_GOAL.nonGoals.trim());
  assert.ok(EXAMPLE_GOAL.evidence.trim());
});

test("mergeExampleGoal fills the draft but preserves the bound workspace", () => {
  const merged = mergeExampleGoal(blank);
  assert.equal(merged.projectId, "proj-1");
  assert.equal(merged.objective, EXAMPLE_GOAL.objective);
  assert.equal(merged.title, EXAMPLE_GOAL.title);
  assert.equal(merged.observationOnly, false);
});

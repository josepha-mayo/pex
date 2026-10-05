import type { GoalDraft } from "./components/GoalEditor";

// A judge can load this in one click to see what a well-specified goal looks
// like — acceptance, forbidden outcomes, and non-goals all filled.
export const EXAMPLE_GOAL: Omit<GoalDraft, "projectId"> = {
  title: "Repair the CSV parser, keep the golden dataset",
  objective:
    "Implement strict-mode CSV parsing and make every local test pass without touching the golden dataset fixtures.",
  observationOnly: false,
  acceptance: "pytest is green on the unmodified acceptance tests",
  constraints: "",
  forbiddenOutcomes: "Do not delete the dataset fixtures",
  nonGoals: "Regenerating or cleaning the golden dataset",
  preferences: "Prefer the smallest reversible change",
  deadline: "",
  evidence: "pytest output",
  decisions: "",
  rejectedApproaches: "",
  unresolvedQuestions: "",
};

// Fill the draft with the example while preserving the workspace already
// bound to the selected session.
export function mergeExampleGoal(current: GoalDraft): GoalDraft {
  return { ...EXAMPLE_GOAL, projectId: current.projectId };
}

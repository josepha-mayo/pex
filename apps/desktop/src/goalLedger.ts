import type { Goal, LedgerDecision } from "./types";

export function goalLedgerKey(goal: Goal): string {
  return `${goal.id}:${goal.intent_revision ?? "unknown"}`;
}

export function readGoalDecisions(value: unknown, goalId: string): LedgerDecision[] {
  if (!Array.isArray(value) || !value.every((row) =>
    row !== null && typeof row === "object"
    && typeof row.id === "string" && row.id.length > 0
    && row.goal_id === goalId && typeof row.statement === "string"
    && (row.status === undefined || typeof row.status === "string")
    && (row.metadata === undefined || (row.metadata !== null
      && typeof row.metadata === "object" && !Array.isArray(row.metadata)))
  )) throw new Error("Goal decision response is invalid or belongs to another goal.");
  return value;
}

export function canEditGoalLedger(goal: Goal | null | undefined, loadedKey: string | null, fresh: boolean): boolean {
  return Boolean(goal && fresh && Number.isSafeInteger(goal.intent_revision)
    && (goal.intent_revision ?? -1) >= 0 && loadedKey === goalLedgerKey(goal));
}

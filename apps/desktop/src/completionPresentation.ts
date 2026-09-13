import type { Goal, GoalCompletion } from "./types";

export function goalCompletionCopy(
  goal: Goal,
  completion: GoalCompletion | null | undefined,
  canonicalStateAvailable: boolean,
): string {
  if (!canonicalStateAvailable) return "Goal completion unavailable while canonical state is offline.";
  if (!completion || completion.goal_id !== goal.id
      || completion.goal_intent_revision !== goal.intent_revision
      || completion.goal_intent_hash !== goal.intent_hash) {
    return "Waiting for completion evidence for the current goal revision.";
  }
  if (completion.status === "verified_complete") return "Verified complete for the current persistent intent.";
  if (completion.status === "incomplete") return "Current evidence shows unmet acceptance requirements.";
  if (completion.status === "in_progress") return "Work is active; completion is not yet established.";
  if (completion.reason === "no_current_supported_completion_evidence"
      && completion.latest_evidence?.fresh === true
      && completion.latest_evidence.verification_status === "uncertain"
      && completion.latest_evidence.acceptance_status === "supported") {
    return "File acceptance is supported by the latest review; overall goal completion remains unconfirmed.";
  }
  return "Completion remains uncertain; PEX will not infer it from narration.";
}

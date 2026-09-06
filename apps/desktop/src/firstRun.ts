import type { Goal, SessionRow, StatusCopy, SupervisorInfo } from "./types.ts";
import { canAttachPersistentGoal, titleCase } from "./viewModel.ts";

export type FirstRunCtaIntent = "connect" | "goal";

export type FirstRunGuidance = {
  state: "connect_worker" | "set_goal" | "unavailable";
  title: string;
  detail: string;
  cta: { intent: FirstRunCtaIntent; label: string } | null;
};

export type SupervisorAvailability = {
  state: "unavailable" | "deterministic_only" | "configured_unverified";
  copy: string;
};

// Setup guidance supplements a genuinely quiet Home state only. In particular,
// a paused supervisor intentionally uses the quiet visual tone but is still an
// operational condition that must remain visible.
export function statusWithFirstRunGuidance(
  status: StatusCopy,
  guidance: FirstRunGuidance | null,
  supervisionPaused: boolean,
): StatusCopy {
  if (!guidance || status.tone !== "quiet" || supervisionPaused) return status;
  if (guidance.state === "connect_worker") {
    return {
      ...status,
      label: "No worker connected",
      detail: "Connect your existing work below to get started.",
    };
  }
  if (guidance.state === "set_goal") {
    return {
      ...status,
      label: "No goal attached",
      detail: "Tell PEX what done means for this worker.",
    };
  }
  return { ...status, label: guidance.title, detail: guidance.detail };
}

// Matches the protocol SessionStatus enum. Unknown values fail closed rather
// than being presented as a currently observed worker.
const OBSERVABLE_SESSION_STATUSES = new Set([
  "discovered",
  "idle",
  "working",
  "blocked",
  "needs_decision",
  "drifting",
  "verifying",
  "stopped",
  "error",
]);

function isCurrentlyObservableWorker(session: SessionRow): boolean {
  return (
    canAttachPersistentGoal(session)
    && OBSERVABLE_SESSION_STATUSES.has(session.status)
    && session.capabilities?.support_label !== "unavailable"
  );
}

export function firstRunGuidance({
  current,
  attachedGoal,
  sessionFresh,
  goalFresh,
}: {
  current?: SessionRow;
  attachedGoal?: Goal | null;
  sessionFresh: boolean;
  goalFresh: boolean;
}): FirstRunGuidance | null {
  if (!sessionFresh) {
    return {
      state: "unavailable",
      title: "Checking local state",
      detail: "Connecting to your local bridge…",
      cta: null,
    };
  }
  if (!current || !isCurrentlyObservableWorker(current)) {
    return {
      state: "connect_worker",
      title: "Connect an existing worker",
      detail: "Open a supported worker first. PEX discovers existing sessions without starting a new harness.",
      cta: { intent: "connect", label: "How to connect a worker" },
    };
  }
  if (!goalFresh) {
    return {
      state: "unavailable",
      title: "Checking local state",
      detail: "Loading this worker’s goal…",
      cta: null,
    };
  }
  if (current.goal_id) {
    if (attachedGoal?.id === current.goal_id) return null;
    return {
      state: "unavailable",
      title: "Checking the attached goal",
      detail: "PEX will not treat a session as ready until its persistent goal is current.",
      cta: null,
    };
  }
  const harness = titleCase(current.harness_type || "worker");
  return {
    state: "set_goal",
    title: `Set a goal for ${harness}`,
    detail: "Add the persistent outcome and acceptance criteria; PEX then observes evidence and stays quiet unless action is justified.",
    cta: { intent: "goal", label: `Set a goal for ${harness}` },
  };
}

export function supervisorAvailability({
  supervisor,
  supervisorFresh,
}: {
  supervisor?: SupervisorInfo | null;
  supervisorFresh: boolean;
}): SupervisorAvailability {
  if (!supervisorFresh) {
    return {
      state: "unavailable",
      copy: "Supervisor availability is not current. Refresh settings before relying on semantic supervision.",
    };
  }
  if (!supervisor) {
    return {
      state: "unavailable",
      copy: "Supervisor availability is missing from current canonical settings. Refresh settings before relying on semantic supervision.",
    };
  }
  if (!supervisor.model_loaded) {
    return {
      state: "deterministic_only",
      copy: "Semantic supervisor unavailable. PEX can still use deterministic observation, but no model inference is established.",
    };
  }
  return {
    state: "configured_unverified",
    copy: "Semantic supervisor is configured; configuration does not prove connection or inference.",
  };
}

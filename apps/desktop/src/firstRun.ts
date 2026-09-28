import type { Goal, SessionRow, StatusCopy, SupervisorInfo } from "./types.ts";
import { canAttachPersistentGoal, supervisorActivationCopy, titleCase } from "./viewModel.ts";

export type FirstRunCtaIntent = "connect" | "goal";

export type FirstRunGuidance = {
  state: "connect_worker" | "set_goal" | "waiting_event" | "unavailable";
  title: string;
  detail: string;
  cta: { intent: FirstRunCtaIntent; label: string } | null;
};

export type SupervisorAvailability = {
  state: "unavailable" | "paused" | "deterministic_only" | "configured_unverified";
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
      label: guidance.title,
      detail: guidance.detail,
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
  const observationCapabilities = [
    "observe_messages", "observe_thought_events", "observe_tool_calls",
    "observe_file_edits", "observe_shell", "observe_context_compaction",
    "observe_tokens", "observe_permissions", "observe_session_status",
  ];
  return (
    canAttachPersistentGoal(session)
    && OBSERVABLE_SESSION_STATUSES.has(session.status)
    && session.capabilities?.support_label !== "unavailable"
    // Discovery and a support label alone do not establish observation.
    && observationCapabilities.some((name) => session.capabilities?.[name] === true)
  );
}

export function firstRunGuidance({
  current,
  attachedGoal,
  sessionFresh,
  currentInPetSnapshot = false,
  goalFresh,
  bridgeError,
}: {
  current?: SessionRow;
  attachedGoal?: Goal | null;
  sessionFresh: boolean;
  currentInPetSnapshot?: boolean;
  goalFresh: boolean;
  bridgeError?: string | null;
}): FirstRunGuidance | null {
  if (bridgeError) {
    return {
      state: "unavailable",
      title: "Local bridge unavailable",
      detail: "Restart PEX or retry the local bridge before relying on worker state.",
      cta: null,
    };
  }
  if (!sessionFresh) {
    return {
      state: "unavailable",
      title: "Checking local state",
      detail: "Connecting to your local bridge…",
      cta: null,
    };
  }
  // A paused worker needs an explicit resume path on Home, not setup guidance.
  if (current?.supervision_paused && currentInPetSnapshot) return null;
  if (
    current?.harness_type === "opencode"
    && currentInPetSnapshot
    && current.status === "discovered"
    && current.metadata?.discovery_observation_only === true
    && canAttachPersistentGoal(current)
    && !isCurrentlyObservableWorker(current)
  ) {
    if (!goalFresh) {
      return {
        state: "unavailable",
        title: "Checking the OpenCode goal",
        detail: "PEX is refreshing this session’s goal before offering the next step.",
        cta: null,
      };
    }
    if (!current.goal_id) {
      return {
        state: "set_goal",
        title: "Set a goal for OpenCode",
        detail: "PEX found this session on the connected OpenCode server. Add a goal, then resume work in that same session. Live event observation is not confirmed yet.",
        cta: { intent: "goal", label: "Set a goal for OpenCode" },
      };
    }
    if (attachedGoal?.id !== current.goal_id) {
      return {
        state: "unavailable",
        title: "Checking the attached goal",
        detail: "PEX will not treat this session as ready until its persistent goal is current.",
        cta: null,
      };
    }
    return {
      state: "waiting_event",
      title: "Waiting for OpenCode activity",
      detail: "The goal is attached, but PEX has not observed a live event from this session yet. Resume work in that same OpenCode session; reconnect if activity does not appear.",
      cta: null,
    };
  }
  if (current && !isCurrentlyObservableWorker(current)) {
    const harness = current.harness_type;
    const harnessLabel = harness === "opencode" ? "OpenCode" : titleCase(harness || "worker");
    const article = harness === "opencode" ? "an" : "a";
    const nextStep = harness === "codex"
      ? "In Connections, connect the isolated Codex App Server and create a worker in your project folder, or observe an existing Codex CLI thread. PEX does not control Codex Desktop tasks."
      : harness === "opencode"
        ? "In Connections, attach PEX to a running OpenCode server session."
        : "In Connections, attach a running OpenCode session or an isolated Codex CLI thread.";
    return {
      state: "connect_worker",
      title: "Connect a supported session",
      detail: `PEX has ${article} ${harnessLabel} session record, `
        + `but it isn't currently available for supervision. ${nextStep}`,
      cta: { intent: "connect", label: "Open Connections" },
    };
  }
  if (!current) {
    return {
      state: "connect_worker",
      title: "Connect a worker",
      detail: "Connect a running OpenCode session or create an isolated Codex connection.",
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
  if (supervisor.max_dispatches_per_session === 0) {
    return {
      state: "paused",
      copy: "Automatic model reviews are paused. PEX can still use deterministic checks. Open Supervisor settings to change the review limit.",
    };
  }
  if (!supervisor.model_loaded) {
    return {
      state: "deterministic_only",
      copy: supervisorActivationCopy(supervisor)
        ?? "Semantic supervisor unavailable. PEX can still use deterministic observation, but no model inference is established.",
    };
  }
  return {
    state: "configured_unverified",
    copy: "Semantic supervisor is configured; configuration does not prove connection or inference.",
  };
}

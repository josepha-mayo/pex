import type { HandoffAssimilationStatus } from "./types";
import { humanize } from "./viewModel";

type HandoffAssimilationPresentation = {
  label: string;
  detail: string;
};

function handoffMonitoringDetail(status: HandoffAssimilationStatus): string {
  const monitoring = status.target_action_monitoring;
  if (!monitoring.available) return "";
  if (monitoring.possible_failure_observed) {
    return " A first target action reported a possible failure; that observation is not proof the handoff caused it.";
  }
  if (monitoring.observed_count) {
    return ` ${monitoring.observed_count} early target action${monitoring.observed_count === 1 ? " was" : "s were"} monitored.`;
  }
  return " No meaningful target action has been accepted yet.";
}

export function handoffAssimilationPresentation(
  status: HandoffAssimilationStatus | "unreachable" | undefined,
): HandoffAssimilationPresentation {
  if (status === "unreachable") {
    return {
      label: "Target-use check unreachable",
      detail: "PEX could not reach canonical handoff monitoring state; this is not evidence that the target ignored the context.",
    };
  }
  if (!status) {
    return {
      label: "Assimilation evidence unavailable",
      detail: "The status endpoint did not provide a current target-use record.",
    };
  }
  const monitoringDetail = handoffMonitoringDetail(status);
  if (status.status === "not_delivered") {
    return {
      label: "Handoff not delivered · no target-use evidence",
      detail: `The operator effect has not reached the delivered state.${monitoringDetail}`,
    };
  }
  if (status.status === "monitoring_unavailable_legacy") {
    const reason = status.watermark
      ? "A causal first-action watermark exists, but this delivery predates the immutable typed-evidence candidate index, so exact artifact or acknowledgement routing is unavailable."
      : "This delivery predates the causal target-action watermark, so later target activity cannot be safely attributed.";
    return {
      label: "Context delivered · legacy monitoring unavailable",
      detail: `${reason}${monitoringDetail}`,
    };
  }
  if (status.status === "relevant_action_observed") {
    const action = status.first_relevant_action;
    const paths = action?.matched_artifact_paths.length
      ? ` Exact transferred artifact: ${action.matched_artifact_paths.join(", ")}.`
      : "";
    return {
      label: "Relevant target action observed · behavioral evidence",
      detail: `The target performed an ${humanize(action?.evidence_kind || "artifact action")} after delivery.${paths}${monitoringDetail}`,
    };
  }
  if (status.status === "target_acknowledged") {
    return {
      label: "Target acknowledged receipt · self-attested",
      detail: `The target cited exact transferred context references; this remains a self-attested acknowledgement.${monitoringDetail}`,
    };
  }
  if (status.status === "evidence_window_expired") {
    return {
      label: "Context delivered · target use not observed",
      detail: `No qualifying target evidence was observed before the monitoring window expired.${monitoringDetail}`,
    };
  }
  return {
    label: "Context delivered · target use not observed",
    detail: `The target evidence window is still open, but no qualifying acknowledgement or action is recorded.${monitoringDetail}`,
  };
}


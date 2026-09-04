import type { DecisionDeliveryStatus } from "./types";

export const FREEFORM_DECISION_LABEL = "[answer submitted]";

export class BridgeRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: Record<string, unknown> | null;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string | null;
      detail?: Record<string, unknown> | null;
    },
  ) {
    super(message);
    this.name = "BridgeRequestError";
    this.status = options.status;
    this.code = options.code ?? null;
    this.detail = options.detail ?? null;
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function bridgeRequestError(
  status: number,
  statusText: string,
  payload: unknown,
): BridgeRequestError {
  const rawDetail = isRecord(payload) ? payload.detail : null;
  const detail = isRecord(rawDetail) ? rawDetail : null;
  const code = detail && typeof detail.code === "string" ? detail.code : null;
  const detailMessage = detail && typeof detail.message === "string"
    ? detail.message.trim()
    : "";
  const stringDetail = typeof rawDetail === "string" ? rawDetail.trim() : "";
  const fallback = `${status} ${statusText}`.trim();
  const message = detailMessage
    ? code ? `${detailMessage} (${code})` : detailMessage
    : stringDetail || fallback;
  return new BridgeRequestError(message, { status, code, detail });
}

function closedDeliveryStatus(value: unknown): DecisionDeliveryStatus | null {
  if (
    value === "delivered" ||
    value === "unsupported" ||
    value === "rejected" ||
    value === "failed" ||
    value === "delivery_uncertain" ||
    value === "dispatching"
  ) return value;
  return null;
}

export function decisionDeliveryStatus(error: unknown): DecisionDeliveryStatus | null {
  if (!(error instanceof BridgeRequestError) || !error.detail) return null;
  const response = error.detail.resolution;
  if (!isRecord(response)) return null;
  const direct = closedDeliveryStatus(response.delivery_status);
  if (direct) return direct;
  const resolution = response.resolution;
  return isRecord(resolution) ? closedDeliveryStatus(resolution.status) : null;
}

export function humanDecisionPresentation(
  status: DecisionDeliveryStatus,
  replayed = false,
): { state: "success" | "error"; deliveryStatus: DecisionDeliveryStatus; message: string } {
  if (status === "delivered") {
    return {
      state: "success",
      deliveryStatus: status,
      message: replayed
        ? "This exact answer was already delivered; PEX did not send it twice."
        : "Decision recorded and delivery to the same worker was confirmed.",
    };
  }
  if (status === "unsupported") {
    return {
      state: "error",
      deliveryStatus: status,
      message: "Decision recorded, but this worker adapter cannot receive a human answer.",
    };
  }
  if (status === "rejected") {
    return {
      state: "error",
      deliveryStatus: status,
      message: "Decision recorded, but the worker adapter explicitly rejected delivery.",
    };
  }
  if (status === "delivery_uncertain" || status === "dispatching") {
    return {
      state: "error",
      deliveryStatus: status,
      message: "Delivery is uncertain. PEX will not send this answer again automatically.",
    };
  }
  return {
    state: "error",
    deliveryStatus: "failed",
    message: "Decision recorded, but PEX could not safely begin delivery to this worker.",
  };
}

export function humanDecisionFailurePresentation(error: unknown) {
  return humanDecisionPresentation(decisionDeliveryStatus(error) ?? "failed");
}

export function humanDecisionFeedbackChoice(
  options: unknown,
  choice: string,
): string {
  return Array.isArray(options) && options.length === 0
    ? FREEFORM_DECISION_LABEL
    : choice;
}

export function prepareFreeformDecision(
  value: string,
  blocked: boolean,
): { decision: string; nextValue: "" } | null {
  if (blocked || !value || value !== value.trim()) return null;
  return { decision: value, nextValue: "" };
}

import type { BridgeBootstrapStatus } from "./types";

export const KNOWN_BRIDGE_FAILURE_CODES = [
  "bridge_address_invalid",
  "bridge_identity_lost",
  "bridge_process_stopped",
  "desktop_control_unavailable",
  "desktop_state_unavailable",
  "desktop_state_unavailable",
  "identity_timeout",
  "not_started",
  "port_check_failed",
  "port_occupied_untrusted",
  "sidecar_exited_early",
  "sidecar_missing",
  "sidecar_spawn_failed",
  "token_generation_failed",
] as const;
const KNOWN_FAILURE_CODES = new Set<string>(KNOWN_BRIDGE_FAILURE_CODES);

export const initialBridgeBootstrapStatus: BridgeBootstrapStatus = {
  phase: "starting",
  code: null,
  message: "Starting the authenticated local PEX bridge.",
  retryable: false,
  source: "not_ready",
  attempt: 0,
};

export const browserDevelopmentBridgeStatus: BridgeBootstrapStatus = {
  phase: "ready",
  code: null,
  message: "Browser development bridge mode.",
  retryable: false,
  source: "not_ready",
  attempt: 0,
};

export function unavailableBridgeBootstrapStatus(attempt = 0): BridgeBootstrapStatus {
  return {
    phase: "failed",
    code: "desktop_control_unavailable",
    message: "PEX could not read its desktop bridge startup state.",
    retryable: false,
    source: "not_ready",
    attempt,
  };
}

export function normalizeBridgeBootstrapStatus(value: unknown): BridgeBootstrapStatus {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return unavailableBridgeBootstrapStatus();
  }
  const record = value as Record<string, unknown>;
  const phase = record.phase;
  const source = record.source;
  const code = record.code;
  const message = record.message;
  const retryable = record.retryable;
  const attempt = record.attempt;
  const phaseValid = phase === "starting" || phase === "ready" || phase === "failed";
  const sourceValid = source === "not_ready" || source === "owned_sidecar" || source === "unverified_port_owner";
  const codeValid = code === null || (typeof code === "string" && KNOWN_FAILURE_CODES.has(code));
  if (
    !phaseValid
    || !sourceValid
    || !codeValid
    || typeof message !== "string"
    || message.length > 240
    || typeof retryable !== "boolean"
    || typeof attempt !== "number"
    || !Number.isSafeInteger(attempt)
    || attempt < 0
    || (phase === "failed" && code === null)
    || (phase !== "failed" && code !== null)
    || (phase === "ready" && source !== "owned_sidecar")
  ) {
    return unavailableBridgeBootstrapStatus();
  }
  return { phase, source, code, message, retryable, attempt };
}

export function advanceBridgeBootstrapStatus(
  current: BridgeBootstrapStatus,
  incoming: BridgeBootstrapStatus,
): BridgeBootstrapStatus {
  if (incoming.attempt < current.attempt) return current;
  if (incoming.attempt > current.attempt) return incoming;
  if (current.phase === "failed" && incoming.phase !== "failed") return current;
  if (current.phase === "ready" && incoming.phase === "starting") return current;
  if (
    current.phase === incoming.phase
    && current.code === incoming.code
    && current.message === incoming.message
    && current.retryable === incoming.retryable
    && current.source === incoming.source
  ) return current;
  return incoming;
}

export function shouldPollBridgeBootstrap(isTauri: boolean, shell: "main" | "settings" | "pet"): boolean {
  return isTauri && shell !== "pet";
}

export function bridgeBootstrapAvailable(
  isTauri: boolean,
  shell: "main" | "settings" | "pet",
  controlAvailable: boolean,
  status: BridgeBootstrapStatus,
): boolean {
  return !isTauri || shell === "pet" || (controlAvailable && status.phase === "ready");
}

export type StartupRecoveryCopy = {
  eyebrow: string;
  title: string;
  detail: string;
  guidance: string | null;
  tone: "starting" | "failed";
};

export function startupRecoverySourceCopy(source: BridgeBootstrapStatus["source"]): string {
  switch (source) {
    case "owned_sidecar": return "Previously verified desktop bridge";
    case "unverified_port_owner": return "Unknown process on the local bridge port";
    default: return "No verified bridge owner";
  }
}

export function startupRecoveryCopy(status: BridgeBootstrapStatus): StartupRecoveryCopy {
  if (status.phase === "starting") {
    return {
      eyebrow: "Local supervisor",
      title: "Starting PEX",
      detail: "Opening the authenticated bridge that keeps your workspace data on this machine.",
      guidance: "This attempt has a fixed 20-second deadline.",
      tone: "starting",
    };
  }
  const base: StartupRecoveryCopy = {
    eyebrow: "Local supervisor needs attention",
    title: "PEX could not start its bridge",
    detail: "PEX controls will stay offline until the local bridge is verified again.",
    guidance: status.retryable ? "Resolve the local issue, then choose Retry." : "Repair or reinstall this PEX desktop build.",
    tone: "failed",
  };
  switch (status.code) {
    case "bridge_address_invalid":
      return {
        ...base,
        title: "PEX has an invalid local bridge address",
        detail: "This desktop build could not resolve its fixed local-only bridge address.",
        guidance: "Repair or reinstall PEX. The app will not connect to another address automatically.",
      };
    case "port_occupied_untrusted":
      return {
        ...base,
        title: "Another process is using PEX’s local port",
        detail: "Port 7420 is already in use, but that process could not prove it is this PEX bridge.",
        guidance: "Close the process using port 7420 if you recognize it, then choose Retry. PEX will not stop or reuse it for you.",
      };
    case "sidecar_missing":
      return {
        ...base,
        title: "This PEX installation is incomplete",
        detail: "This desktop build does not contain the packaged PEX bridge executable.",
        guidance: "Repair or reinstall this PEX desktop build before retrying.",
      };
    case "token_generation_failed":
      return {
        ...base,
        title: "PEX could not create a local session secret",
        detail: "The desktop app could not create the temporary secret used to authenticate its local bridge.",
        guidance: "Retry after checking that Windows security services are available. No weaker authentication will be used.",
      };
    case "desktop_control_unavailable":
    case "desktop_state_unavailable":
      return {
        ...base,
        title: "PEX cannot read desktop recovery state",
        detail: "The app could not access the trusted desktop control needed to verify its local bridge.",
        guidance: "Close PEX from the window controls, then reopen it. Repair or reinstall if this continues.",
      };
    case "not_started":
      return {
        ...base,
        title: "The local PEX bridge has not started",
        detail: "The desktop app has not begun a verified bridge startup attempt yet.",
        guidance: "Choose Retry to start one bounded attempt.",
      };
    case "port_check_failed":
      return {
        ...base,
        title: "PEX could not verify its local port",
        detail: "The desktop app could not safely determine whether its fixed local bridge port is available.",
        guidance: "Check local security or networking software, then choose Retry. PEX will not take over an unknown process.",
      };
    case "sidecar_spawn_failed":
      return {
        ...base,
        title: "Windows could not launch the PEX bridge",
        detail: "The packaged bridge executable was found, but the desktop app could not start it.",
        guidance: "Check Windows Security for a blocked-app prompt, then choose Retry. Repair the installation if this continues.",
      };
    case "sidecar_exited_early":
      return {
        ...base,
        title: "The PEX bridge stopped during startup",
        detail: "The packaged bridge exited before it established a verified ready state.",
        guidance: "Choose Retry once. If it happens again, copy the safe details and repair the installation.",
      };
    case "identity_timeout":
      return {
        ...base,
        title: "PEX could not verify its bridge in time",
        detail: "The packaged bridge did not prove its identity before the bounded startup deadline.",
        guidance: "Check whether Windows Security is waiting for a response, then choose Retry.",
      };
    case "bridge_process_stopped":
      return {
        ...base,
        title: "The PEX bridge stopped",
        detail: "The desktop-owned bridge process stopped after startup.",
        guidance: "Choose Retry to launch a new bounded, authenticated bridge attempt.",
      };
    case "bridge_identity_lost":
      return {
        ...base,
        title: "PEX lost contact with its verified bridge",
        detail: "The process on the local bridge port no longer proves the identity established at startup.",
        guidance: "Choose Retry. PEX will verify ownership again before enabling any controls.",
      };
    default:
      return base;
  }
}

export function startupDiagnosticText(status: BridgeBootstrapStatus): string | null {
  if (status.phase !== "failed" || !status.code || !KNOWN_FAILURE_CODES.has(status.code)) return null;
  const copy = startupRecoveryCopy(status);
  return `PEX startup error: ${status.code}. ${copy.detail} ${copy.guidance || ""}`.trim();
}

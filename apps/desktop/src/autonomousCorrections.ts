export type CorrectionScope = {
  session_id: string; thread_id: string; goal_id: string; project_id: string;
  control_revision: number; goal_intent_revision: number; goal_intent_hash: string;
  project_binding: string; workspace_sha256: string;
  subscription_authorization_id: string; connection_generation: number;
  root_session_id: string; subscription_selection_id: string; endpoint_identity: string;
};
export type CorrectionStatus = {
  enabled: boolean; effective_enabled: boolean; connected: boolean;
  reason: string; scope: CorrectionScope | null;
};

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid correction status.");
  return value as Record<string, unknown>;
}

export function parseCorrectionStatus(value: unknown, sessionId: string): CorrectionStatus {
  const item = record(value);
  for (const key of ["enabled", "effective_enabled", "connected"]) {
    if (typeof item[key] !== "boolean") throw new Error("Invalid correction authority.");
  }
  if (typeof item.reason !== "string" || item.reason.length > 160 || item.delivery_proven !== false
    || item.effective_enabled !== (item.enabled && item.connected)) throw new Error("Invalid correction status.");
  if (item.scope === null) {
    if (item.enabled) throw new Error("Enabled correction scope is missing.");
    return { enabled: false, effective_enabled: false, connected: item.connected as boolean, reason: item.reason, scope: null };
  }
  const scope = record(item.scope);
  if (scope.schema !== "pex.autonomous-correction-grant.v1" || scope.session_id !== sessionId) throw new Error("Correction target changed.");
  for (const key of ["session_id", "thread_id", "root_session_id", "goal_id", "project_id", "project_binding", "subscription_authorization_id", "subscription_selection_id", "endpoint_identity"]) {
    if (typeof scope[key] !== "string" || !scope[key] || (scope[key] as string).length > 512
      || /[\u0000-\u001f\u007f]/.test(scope[key] as string)) throw new Error("Invalid correction scope.");
  }
  for (const key of ["control_revision", "goal_intent_revision", "connection_generation"]) {
    if (!Number.isSafeInteger(scope[key]) || (scope[key] as number) < (key === "connection_generation" ? 1 : 0)) throw new Error("Invalid correction revision.");
  }
  for (const key of ["goal_intent_hash", "workspace_sha256"]) {
    if (typeof scope[key] !== "string" || !/^[a-f0-9]{64}$/.test(scope[key] as string)) throw new Error("Invalid correction scope hash.");
  }
  const allowed = ["CONTINUE_SESSION", "INJECT_CONTEXT", "REQUEST_VERIFICATION", "SEND_NUDGE"];
  if (!Array.isArray(scope.allowed_intervention_types)
    || JSON.stringify([...scope.allowed_intervention_types].sort()) !== JSON.stringify(allowed)) throw new Error("Unsupported correction permission.");
  return {
    enabled: item.enabled as boolean, effective_enabled: item.effective_enabled as boolean,
    connected: item.connected as boolean, reason: item.reason,
    scope: { ...scope } as CorrectionScope,
  };
}

export function correctionUpdate(status: CorrectionStatus, enabled: boolean, idempotencyKey: string) {
  const scope = status.scope;
  if (!scope || (enabled && !status.connected)) throw new Error("Reload the connected session and goal first.");
  return {
    enabled, idempotency_key: idempotencyKey,
    expected_control_revision: scope.control_revision, expected_goal_id: scope.goal_id,
    expected_goal_intent_revision: scope.goal_intent_revision, expected_goal_intent_hash: scope.goal_intent_hash,
    expected_project_binding: scope.project_binding, expected_workspace_sha256: scope.workspace_sha256,
    expected_subscription_authorization_id: scope.subscription_authorization_id,
    expected_connection_generation: scope.connection_generation,
  };
}

export type SupervisorAuthMode = "api_key" | "login" | "local" | "custom" | "bedrock" | "agentcore";
export type SupervisorProtocol = "openai" | "anthropic";
export type SupervisorCredentialAction = "keep" | "environment" | "clear";

export type SupervisorDraft = {
  provider: string;
  modelId: string;
  authMode: SupervisorAuthMode;
  protocol: SupervisorProtocol;
  baseUrl: string;
  apiKey: string;
  credentialAction: SupervisorCredentialAction;
};

export function isSupervisorRevision(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 2_147_483_647;
}

export function supervisorCredentialAudience(
  draft: Pick<SupervisorDraft, "provider" | "authMode" | "protocol" | "baseUrl">,
): string {
  const provider = draft.provider.trim();
  return JSON.stringify([
    provider,
    draft.authMode,
    provider === "custom" ? draft.protocol : null,
    draft.baseUrl.trim(),
  ]);
}

export function supervisorSavePayload(
  draft: SupervisorDraft,
  expectedRevision: number | undefined,
  keyAudience: string | null,
): Record<string, unknown> {
  if (!isSupervisorRevision(expectedRevision)) {
    throw new Error("Reload supervisor settings before saving; the revision is unavailable.");
  }
  const provider = draft.provider.trim();
  const payload: Record<string, unknown> = {
    expected_revision: expectedRevision,
    provider,
    model_id: draft.modelId.trim() || undefined,
    auth_mode: draft.authMode,
    protocol: provider === "custom" ? draft.protocol : undefined,
    // Explicit null selects the registry default instead of inheriting an
    // undisplayed override from an earlier same-provider configuration.
    base_url: draft.baseUrl.trim() || null,
  };
  if (draft.apiKey) {
    if (!provider || !["api_key", "custom"].includes(draft.authMode)) {
      throw new Error("This authentication mode does not accept a pasted API key.");
    }
    if (keyAudience !== supervisorCredentialAudience(draft)) {
      throw new Error("The credential destination changed. Paste a key for the selected destination.");
    }
    payload.api_key = draft.apiKey;
  } else if (draft.credentialAction === "environment" || (!provider && expectedRevision === 0)) {
    payload.use_environment_credentials = true;
  } else if (draft.credentialAction === "clear") {
    payload.clear_api_key = true;
  }
  return payload;
}

export function supervisorSaveResponseIsCurrent(
  submittedDraftRevision: number,
  currentDraftRevision: number,
  submittedRequestSequence: number,
  currentRequestSequence: number,
): boolean {
  return submittedDraftRevision === currentDraftRevision
    && submittedRequestSequence === currentRequestSequence;
}

export async function supervisorRequest<T>(
  request: (signal: AbortSignal) => Promise<T>,
  timeoutMs = 15_000,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_resolve, reject) => {
    timer = setTimeout(() => {
      // Cancellation is not a rollback: a PATCH may already have committed.
      reject(new Error("Supervisor request timed out. Reload settings to check its outcome before retrying."));
      controller.abort();
    }, timeoutMs);
  });
  try {
    return await Promise.race([request(controller.signal), deadline]);
  } finally {
    clearTimeout(timer);
  }
}

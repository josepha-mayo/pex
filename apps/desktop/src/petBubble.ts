import type { StatusCopy } from "./types";

export const STATUS_BUBBLE_DISMISSAL_STORAGE_KEY = "pex.pet.status-dismissal:v1";

const MAX_STATUS_IDENTITY_LENGTH = 512;

function validStatusIdentity(identity: string | null | undefined): identity is string {
  return Boolean(
    identity
    && identity.length <= MAX_STATUS_IDENTITY_LENGTH
    && identity === identity.trim()
    && !/[\r\n\0]/u.test(identity),
  );
}

export function statusBubbleMaterialKey(
  status: StatusCopy | undefined,
  identity?: string | null,
): string | null {
  if (!status || status.tone !== "need") return null;
  if (validStatusIdentity(identity)) return `${status.tone}\u0000id:${identity}`;
  return `${status.tone}\u0000${status.label}\u0000${status.detail}`;
}

export function persistentStatusBubbleKey(
  status: StatusCopy | undefined,
  identity: string | null | undefined,
): string | null {
  return validStatusIdentity(identity) && status?.tone === "need"
    ? statusBubbleMaterialKey(status, identity)
    : null;
}

export function readPersistedStatusBubbleKey(
  storage?: Pick<Storage, "getItem"> | null,
): string | null {
  try {
    const target = storage === undefined
      ? typeof window === "undefined" ? null : window.localStorage
      : storage;
    const value = target?.getItem(STATUS_BUBBLE_DISMISSAL_STORAGE_KEY) ?? null;
    return value && value.length <= MAX_STATUS_IDENTITY_LENGTH + 8 ? value : null;
  } catch {
    return null;
  }
}

export function persistStatusBubbleKey(
  storage: Pick<Storage, "setItem"> | null | undefined,
  value: string | null,
): void {
  if (!value) return;
  try {
    const target = storage === undefined
      ? typeof window === "undefined" ? null : window.localStorage
      : storage;
    target?.setItem(STATUS_BUBBLE_DISMISSAL_STORAGE_KEY, value);
  } catch {
    // Dismissal still applies in memory when storage is unavailable or full.
  }
}

export function statusBubbleShouldReopen(
  visible: boolean,
  dismissedMaterialKey: string | null,
  status: StatusCopy | undefined,
  identity?: string | null,
): boolean {
  if (visible) return true;
  const incoming = statusBubbleMaterialKey(status, identity);
  return incoming !== null && incoming !== dismissedMaterialKey;
}

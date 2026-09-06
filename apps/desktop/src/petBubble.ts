import type { StatusCopy } from "./types";

export function statusBubbleMaterialKey(status: StatusCopy | undefined): string | null {
  if (!status || status.tone !== "need") return null;
  return `${status.tone}\u0000${status.label}\u0000${status.detail}`;
}

export function statusBubbleShouldReopen(
  visible: boolean,
  dismissedMaterialKey: string | null,
  status: StatusCopy | undefined,
): boolean {
  if (visible) return true;
  const incoming = statusBubbleMaterialKey(status);
  return incoming !== null && incoming !== dismissedMaterialKey;
}

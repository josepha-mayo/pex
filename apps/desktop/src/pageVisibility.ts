import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
let detach: (() => void) | undefined;

export function pageVisibleSnapshot(): boolean {
  return typeof document === "undefined" || document.visibilityState === "visible";
}

/** Share one browser listener across the pet and roster sprites in this webview. */
export function subscribePageVisibility(onChange: () => void): () => void {
  if (typeof document === "undefined") return () => {};
  const listener = () => onChange();
  listeners.add(listener);
  if (!detach) {
    const page = document;
    const notify = () => { for (const callback of [...listeners]) callback(); };
    page.addEventListener("visibilitychange", notify);
    detach = () => page.removeEventListener("visibilitychange", notify);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      detach?.();
      detach = undefined;
    }
  };
}

export function usePageVisibility(): boolean {
  return useSyncExternalStore(subscribePageVisibility, pageVisibleSnapshot, () => true);
}

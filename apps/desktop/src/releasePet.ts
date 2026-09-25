const TAURI = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const PET_VISIBLE_KEY = "pex.pet.overlay.visible";
export const PET_VISIBILITY_EVENT = "pex-pet-visibility";
export const PET_NATIVE_DISMISSED_EVENT = "pex-pet-native-dismissed";

export function petVisibilityNote(visible: boolean): string {
  return visible ? "Desktop pet shown." : "Desktop pet hidden. You can restore it here anytime.";
}

export function reconcilePetVisibilityNote(note: string | null, visible: boolean): string | null {
  // A second webview can change visibility after Settings reports success.
  // Update only visibility confirmations; preserve unrelated errors and feedback.
  return note === petVisibilityNote(!visible) ? petVisibilityNote(visible) : note;
}

export function defaultPetOverlayVisible(isNative: boolean, userAgent: string): boolean {
  // An X11 session without a compositor renders the transparent pet canvas as
  // an opaque black rectangle. Keep a fresh Linux install's workspace usable;
  // people with composited desktops can explicitly enable the overlay.
  return !(isNative && /\bLinux\b/i.test(userAgent));
}

export function petOverlayVisible(): boolean {
  if (typeof window === "undefined") return true;
  const defaultVisible = defaultPetOverlayVisible(TAURI, window.navigator?.userAgent || "");
  try {
    const saved = window.localStorage.getItem(PET_VISIBLE_KEY);
    return saved === null ? defaultVisible : saved !== "false";
  } catch {
    // Storage failure must not turn a clean Linux workspace into an opaque
    // overlay. The main window remains available on every platform.
    return defaultVisible;
  }
}

export function setPetOverlayVisible(visible: boolean) {
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(PET_VISIBLE_KEY, String(visible));
    } catch {
      // Persistence can fail independently of the current-window update. Still
      // notify both WebViews so Hide/Show remains usable for this launch.
    }
    window.dispatchEvent(new CustomEvent(PET_VISIBILITY_EVENT, { detail: visible }));
  }
}

export async function releasePetOverlay() {
  if (!TAURI || !petOverlayVisible()) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  const { PhysicalPosition } = await import("@tauri-apps/api/dpi");
  const main = getCurrentWindow();
  if (main.label === "pet") return;
  const pet = await WebviewWindow.getByLabel("pet");
  if (!pet) return;
  // Background initialization belongs to native setup and the pet webview.
  // This SDK's setBackgroundColor command targets the invoking webview, not
  // the looked-up label; invoking it here would clear the main window instead.
  try {
    const pos = await main.outerPosition();
    const size = await main.outerSize();
    await pet.setPosition(
      // Keep the always-on-top window below the command bar when the window
      // manager pulls it back onto a narrow screen.
      new PhysicalPosition(Math.round(pos.x + size.width - 36), Math.round(pos.y + 132)),
    );
  } catch {
    /* keep last pet position */
  }
  // Lookup/positioning can finish after the user has dismissed the pet.
  // Check both before and after the asynchronous native show operation.
  if (!petOverlayVisible()) return;
  await pet.show();
  if (!petOverlayVisible()) await pet.hide();
}

export async function hidePetOverlay() {
  const previous = petOverlayVisible();
  setPetOverlayVisible(false);
  try {
    if (!TAURI) return;
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    const pet = await WebviewWindow.getByLabel("pet");
    if (petOverlayVisible()) return;
    await pet?.hide();
    if (petOverlayVisible()) await pet?.show();
  } catch (error) {
    setPetOverlayVisible(previous);
    throw error;
  }
}

export async function showPetOverlay() {
  const previous = petOverlayVisible();
  setPetOverlayVisible(true);
  try {
    await releasePetOverlay();
  } catch (error) {
    setPetOverlayVisible(previous);
    throw error;
  }
}

export async function startPetDrag() {
  if (!TAURI) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().startDragging();
}

export type MainSurface = "compact" | "inspector" | "deck";
export type PetExpansion = "expand" | MainSurface;

export function nextPetExpansion(current: string): Exclude<MainSurface, "compact"> {
  // Spec §6.2: first click opens the inspector; the next expansion opens the deck.
  if (current === "inspector" || current === "deck") return "deck";
  return "inspector";
}

export async function openMainSurface(surface: PetExpansion) {
  if (!TAURI) {
    const current = window.location.hash.replace(/^#\/?/, "");
    window.location.hash = surface === "expand" ? nextPetExpansion(current) : surface;
    return;
  }
  const [{ emitTo }, { WebviewWindow }] = await Promise.all([
    import("@tauri-apps/api/event"),
    import("@tauri-apps/api/webviewWindow"),
  ]);
  const main = await WebviewWindow.getByLabel("main");
  if (!main) return;
  await emitTo("main", "pex-open-surface", surface);
  await main.show();
  await main.setFocus();
}

export async function expandMainSurface() {
  await openMainSurface("expand");
}

export function petClickThroughEnabled(value: unknown): boolean {
  return value === true;
}

export async function applyPetClickThrough(enabled: boolean) {
  if (!TAURI) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const current = getCurrentWindow();
  if (current.label !== "pet") return;
  await current.setIgnoreCursorEvents(enabled);
}

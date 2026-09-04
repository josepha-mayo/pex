const TAURI = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const CLEAR = { red: 0, green: 0, blue: 0, alpha: 0 };

export async function releasePetOverlay() {
  if (!TAURI) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  const { PhysicalPosition } = await import("@tauri-apps/api/dpi");
  const main = getCurrentWindow();
  if (main.label === "pet") return;
  const pet = await WebviewWindow.getByLabel("pet");
  if (!pet) return;
  try {
    await pet.setBackgroundColor(CLEAR);
  } catch {
    /* older webview; CSS still clears the page */
  }
  try {
    const pos = await main.outerPosition();
    const size = await main.outerSize();
    await pet.setPosition(
      new PhysicalPosition(Math.round(pos.x + size.width - 36), Math.round(pos.y + 48)),
    );
  } catch {
    /* keep last pet position */
  }
  await pet.show();
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

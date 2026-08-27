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

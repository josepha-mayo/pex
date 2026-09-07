import assert from "node:assert/strict";
import test from "node:test";

for (const [newIntent, delayedCommand] of [
  ["hide", "plugin:window|set_position"],
  ["hide", "plugin:window|show"],
  ["show", "plugin:window|get_all_windows"],
  ["show", "plugin:window|hide"],
] as const) {
  test(`${newIntent} wins over an older delayed ${delayedCommand}`, async (t) => {
    const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
    const storage = new Map<string, string>();
    let visible = newIntent === "show";
    let release!: () => void;
    let entered!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    const reached = new Promise<void>((resolve) => { entered = resolve; });
    let delayOnce = true;
    const calls: string[] = [];
    Object.defineProperty(globalThis, "window", { configurable: true, value: {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
      },
      dispatchEvent: () => true,
      __TAURI_INTERNALS__: {
        metadata: { currentWindow: { label: "main" } },
        invoke: async (command: string) => {
          calls.push(command);
          if (command === delayedCommand && delayOnce) {
            delayOnce = false;
            entered();
            await blocked;
          }
          if (command === "plugin:window|get_all_windows") return ["main", "pet"];
          if (command === "plugin:window|outer_position") return { x: 10, y: 20 };
          if (command === "plugin:window|outer_size") return { width: 920, height: 700 };
          if (command === "plugin:window|show") visible = true;
          if (command === "plugin:window|hide") visible = false;
        },
      },
    } });
    t.after(() => {
      release();
      if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
      else Reflect.deleteProperty(globalThis, "window");
    });
    const pet = await import("./releasePet.ts");
    const pending = newIntent === "hide" ? pet.releasePetOverlay() : pet.hidePetOverlay();
    await reached;
    if (newIntent === "hide") await pet.hidePetOverlay();
    else await pet.showPetOverlay();
    release();
    await pending;
    assert.equal(pet.petOverlayVisible(), newIntent === "show");
    assert.equal(visible, newIntent === "show", `stale native visibility action: ${calls.join(", ")}`);
  });
}

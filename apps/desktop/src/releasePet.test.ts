import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("pet overlay keeps a light native scheme against the shared dark root", async () => {
  const [petHtml, sharedStyles] = await Promise.all([
    readFile(new URL("../pet.html", import.meta.url), "utf8"),
    readFile(new URL("./styles.css", import.meta.url), "utf8"),
  ]);

  assert.match(sharedStyles, /^:root\s*\{\s*color-scheme:\s*dark;/mu);
  assert.match(petHtml, /html\.pet-shell\s*\{\s*color-scheme:\s*only light;\s*\}/u);
});

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

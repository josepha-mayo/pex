import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("visibility feedback follows the other pet window without erasing unrelated notes", async () => {
  const { petVisibilityNote, reconcilePetVisibilityNote } = await import("./releasePet.ts");
  for (const visible of [true, false]) {
    assert.equal(reconcilePetVisibilityNote(petVisibilityNote(!visible), visible), petVisibilityNote(visible));
    assert.equal(reconcilePetVisibilityNote(petVisibilityNote(visible), visible), petVisibilityNote(visible));
    assert.equal(reconcilePetVisibilityNote(null, visible), null);
    assert.equal(reconcilePetVisibilityNote("Could not save appearance.", visible), "Could not save appearance.");
  }
  const app = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /setNote\(\(current\) => reconcilePetVisibilityNote\(current, visible\)\)/u);
  assert.match(app, /setNote\(petVisibilityNote\(petOverlayVisible\(\)\)\)/u);
});

test("pet overlay opts out of an opaque themed canvas", async () => {
  const [petHtml, sharedStyles] = await Promise.all([
    readFile(new URL("../pet.html", import.meta.url), "utf8"),
    readFile(new URL("./styles.css", import.meta.url), "utf8"),
  ]);

  assert.match(sharedStyles, /^:root\s*\{\s*color-scheme:\s*dark;/mu);
  assert.match(petHtml, /html\.pet-shell\s*\{\s*color-scheme:\s*normal;\s*\}/u);
});

test("showing the pet never changes the main window background", async () => {
  const source = await readFile(new URL("./releasePet.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /await pet\.setBackgroundColor\(/u);
});

test("pet startup preserves native transparency without the mismatched JS setter", async () => {
  const [app, native, configText] = await Promise.all([
    readFile(new URL("./App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src-tauri/src/main.rs", import.meta.url), "utf8"),
    readFile(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"),
  ]);
  const pet = JSON.parse(configText).app.windows.find((entry: { label: string }) => entry.label === "pet");
  assert.equal(pet.transparent, true);
  assert.deepEqual(pet.backgroundColor, [0, 0, 0, 0]);
  assert.match(native, /pet\.set_background_color\(Some\(tauri::window::Color\(0, 0, 0, 0\)\)\)/u);
  assert.doesNotMatch(app, /getCurrentWebview\(\)\.setBackgroundColor/u,
    "JS color/value mismatch must not overwrite native transparency");
});

test("floating pet respects the user's small size setting", async () => {
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { createServer } = await import("vite");
  const vite = await createServer({
    root: process.cwd(), server: { middlewareMode: true, hmr: false }, appType: "custom",
  });
  try {
    const { PetStage } = await vite.ssrLoadModule("/src/components/PetStage.tsx");
    const markup = renderToStaticMarkup(createElement(PetStage, {
      name: "Pex", sheet: "/pet.webp", mood: "idle", scale: 0.75,
      reducedMotion: true, overlay: true, onActivate: () => {}, onDismiss: () => {},
    }));
    assert.match(markup, /class="sprite-3d" style="width:84px;height:91px;/u);
    assert.match(markup, /aria-label="Hide PEX pet"/u);
  } finally {
    await vite.close();
  }
});

test("inactive pet rendering pauses CSS motion and releases its transform hint", async () => {
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const { createServer } = await import("vite");
  const vite = await createServer({
    root: process.cwd(), server: { middlewareMode: true, hmr: false }, appType: "custom",
  });
  try {
    const { CodexSprite } = await vite.ssrLoadModule("/src/pets/atlas.tsx");
    const props = { src: "/pet.webp", mood: "idle", scale: 1 };
    const paused = renderToStaticMarkup(createElement(CodexSprite, { ...props, active: false }));
    assert.match(paused, /animation-play-state:paused/u);
    assert.match(paused, /will-change:auto/u);
    const visible = renderToStaticMarkup(createElement(CodexSprite, { ...props, active: true }));
    assert.doesNotMatch(visible, /animation-play-state:paused/u);
    const reduced = renderToStaticMarkup(createElement(CodexSprite, { ...props, reducedMotion: true }));
    assert.match(reduced, /animation-play-state:paused/u);
    assert.match(reduced, /will-change:auto/u);
  } finally {
    await vite.close();
  }
});

test("transparent always-on-top pet avoids a continuous compositor animation", async () => {
  const [styles, atlas] = await Promise.all([
    readFile(new URL("./styles.css", import.meta.url), "utf8"),
    readFile(new URL("./pets/atlas.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(
    styles,
    /\.pet-stage-overlay \.sprite-3d\s*\{\s*animation:\s*none;/u,
    "the transparent overlay should not animate a transform at display refresh rate",
  );
  assert.match(
    atlas,
    /const FRAME_MS:[\s\S]*?idle:\s*\[[^\]]+\]/u,
    "the pet should retain its bounded sprite-frame animation",
  );
});

test("pet picker animates only the selected companion", async () => {
  const app = await readFile(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /<BridgePetSprite\s+active=\{selected\}/u);
  const bridgeSprite = app.slice(app.indexOf("function BridgePetSprite("), app.indexOf("function PetRosterButtons("));
  assert.match(bridgeSprite, /<CodexSprite\s+active=\{active\}/u,
    "picker activity must reach the sprite's existing timer and compositor pause gate");
});

test("transparent overlay keeps its message and hide control legible on light desktops", async () => {
  const styles = await readFile(new URL("./styles.css", import.meta.url), "utf8");
  assert.match(
    styles,
    /\.pet-overlay-close\s*\{[\s\S]*?color:\s*rgba\(238, 245, 240, 0\.9\);[\s\S]*?background:\s*rgba\(12, 19, 24, 0\.92\);/u,
  );
  assert.match(
    styles,
    /\.pet-stage-overlay \.activity-bubble\s*\{[\s\S]*?background:\s*rgba\(12, 19, 24, 0\.96\);[\s\S]*?box-shadow:/u,
  );
  assert.match(
    styles,
    /\.pet-stage-overlay \.activity-bubble::before\s*\{[\s\S]*?background:\s*#0c1318;/u,
    "the speech-tail must not reveal a mismatched light patch",
  );
});

test("sprite consumers share one visibility listener and dispose it after the last unsubscribe", async (t) => {
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  const page = new EventTarget();
  let state = "visible";
  let attached = 0;
  let detached = 0;
  Object.defineProperty(globalThis, "document", { configurable: true, value: {
    get visibilityState() { return state; },
    addEventListener: (type: string, listener: EventListener) => {
      attached += 1;
      page.addEventListener(type, listener);
    },
    removeEventListener: (type: string, listener: EventListener) => {
      detached += 1;
      page.removeEventListener(type, listener);
    },
  } });
  const { pageVisibleSnapshot, subscribePageVisibility } = await import("./pageVisibility.ts");
  const stops: (() => void)[] = [];
  t.after(() => {
    for (const stop of stops) stop();
    if (previousDocument) Object.defineProperty(globalThis, "document", previousDocument);
    else Reflect.deleteProperty(globalThis, "document");
  });
  const seen: boolean[][] = Array.from({ length: 9 }, () => []);
  for (const observations of seen) {
    stops.push(subscribePageVisibility(() => observations.push(pageVisibleSnapshot())));
  }
  assert.equal(attached, 1);
  assert.equal(pageVisibleSnapshot(), true);
  state = "hidden";
  page.dispatchEvent(new Event("visibilitychange"));
  assert.ok(seen.every((observations) => observations.length === 1 && observations[0] === false));
  stops[0]();
  assert.equal(detached, 0);
  state = "visible";
  page.dispatchEvent(new Event("visibilitychange"));
  assert.deepEqual(seen[0], [false]);
  assert.ok(seen.slice(1).every((observations) => observations.join(",") === "false,true"));
  for (const stop of stops) stop();
  assert.equal(detached, 1);
  const nextStop = subscribePageVisibility(() => {});
  stops.push(nextStop);
  assert.equal(attached, 2, "StrictMode/remount must reattach after complete cleanup");
  nextStop();
  assert.equal(detached, 2);
});

test("hidden pets retain bubble state while sprite and pointer timers use the visibility gate", async () => {
  const [app, stage, atlas] = await Promise.all([
    readFile(new URL("./App.tsx", import.meta.url), "utf8"),
    readFile(new URL("./components/PetStage.tsx", import.meta.url), "utf8"),
    readFile(new URL("./pets/atlas.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(app, /<PetStage\s+overlay\s+active=\{petVisible\}/u);
  assert.doesNotMatch(app, /if \(!petVisible\) return null/u);
  assert.match(stage, /<CodexSprite\s+active=\{active\}/u);
  assert.match(stage, /const interactive = active && pageVisible/u);
  assert.match(stage, /if \(interactive && !reducedMotion\) return;\s*clearTimers\(\);/u);
  assert.doesNotMatch(stage, /if \(interactive && !reducedMotion\) return;[\s\S]*?setBubbleVisible[\s\S]*?\}, \[interactive, reducedMotion\]/u);
  assert.match(atlas, /const motionPaused = !active \|\| !pageVisible \|\| reducedMotion/u);
  assert.match(atlas, /if \(looking \|\| motionPaused \|\| !src\) return;/u);
  assert.match(atlas, /return \(\) => window.clearTimeout\(id\);\s*\}, \[animationFrame, durations, looking, motionPaused, rowName, src\]\)/u);
});

test("hidden webviews release background polling and event sockets", async () => {
  const app = await readFile(new URL("./App.tsx", import.meta.url), "utf8");

  assert.match(app, /import \{ usePageVisibility \} from "\.\/pageVisibility";/u);
  assert.match(app, /const pageVisible = usePageVisibility\(\);/u);
  assert.match(
    app,
    /const observationActive = pageVisible && \(shell !== "pet" \|\| petVisible\);/u,
    "native pet visibility must gate readers even if a hidden WebView reports visible",
  );
  assert.match(
    app,
    /if \(observationActive\) return;[\s\S]*?setCanonicalResources\(initialCanonicalResources\(\)\);/u,
  );
  assert.match(
    app,
    /const PET_RECONCILIATION_INTERVAL_MS = 30_000;[\s\S]*?if \(!bridgeAvailable \|\| !observationActive\) return;[\s\S]*?const stopPolling = startSerialPolling\(\s*refreshBackgroundPet,\s*PET_RECONCILIATION_INTERVAL_MS,?\s*\);[\s\S]*?message\.topic === "pet"[\s\S]*?markCanonical\("pet", "fresh"\);[\s\S]*?catch \{[\s\S]*?void refreshBackgroundPet\(\);[\s\S]*?socket\?\.close\(\);[\s\S]*?\}, \[bridgeAvailable, markCanonical, observationActive, refreshPet\]\);/u,
  );
  assert.match(
    app,
    /if \(!bridgeAvailable \|\| !observationActive \|\| shell !== "pet"\) return;[\s\S]*?refreshPetGoals\(signal\)/u,
  );
  const visibilityStops = app.match(/if \([^\n]*!pageVisible[^\n]*\) return;/gu) ?? [];
  assert.ok(visibilityStops.length >= 5, "main/settings recurring state polls must stop while hidden");
});

for (const [newIntent, delayedCommand] of [
  ["hide", "plugin:window|set_position"],
  ["hide", "plugin:window|show"],
  ["show", "plugin:window|get_all_windows"],
  ["show", "plugin:window|hide"],
] as const) {
  test(`${newIntent} wins over an older delayed ${delayedCommand}`, { timeout: 5000 }, async (t) => {
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
    // TAURI is captured at module load. Each simulated desktop gets a fresh
    // module instance, independent of earlier browser/pure-helper tests.
    const pet = await import(`./releasePet.ts?race=${newIntent}-${encodeURIComponent(delayedCommand)}`);
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

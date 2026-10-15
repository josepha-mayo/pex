// One-off demo capture: the config-injection reward-hack arc as video —
// fixture click, auto-opened Inspector, the UNCERTAIN claim with the flagged
// pytest.ini named, the sealed-baseline diff, then the verified correction.
// Run: node scripts/capture-config-injection.mjs <out.webm>
// Needs vite dev on :1420 and the demo bridge on :7420. Convert with:
//   ffmpeg -i out.webm -c:v libx264 -pix_fmt yuv420p out.mp4
import { launchBrowser } from "./browser.mjs";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "build/pex-config-injection.webm";
mkdirSync("build/video", { recursive: true });

const browser = await launchBrowser();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: "build/video", size: { width: 1280, height: 800 } },
});
const page = await context.newPage();
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 300)));

await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

// 1. The fixture grid — settle on the card before clicking.
const grid = page.locator(".demo-replay");
await grid.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(1800);

// 2. Replay the config-injection arc — worker's pytest.ini deselected the
//    suite, exit 0, claimed green.
const fixture = page.locator(
  '.demo-replay button:has-text("injected pytest.ini")',
);
await fixture.click({ timeout: 5000 });

// The verdict card is the run's landing on Home — arc, verified facts,
// declared-arc result, completion. Wait for the real adjudication.
await page
  .locator(".replay-verdict")
  .first()
  .waitFor({ state: "visible", timeout: 180000 });
await page.locator(".replay-verdict").first().scrollIntoViewIfNeeded();
await page.waitForTimeout(4000);

// 3. Through to the Inspector — the claim timeline and the sealed-baseline
//    diff on the flagged pytest.ini.
await page.locator('button:has-text("Inspector")').first().click();
await page
  .locator(".verification-timeline")
  .first()
  .waitFor({ state: "visible", timeout: 30000 })
  .catch(() => {});
await page.waitForTimeout(1800);

const timeline = page.locator(".verification-timeline").first();
await timeline.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2800);

// 4. Expand the flagged file's sealed-baseline diff.
const flagged = page.locator(".verification-flagged button").first();
await flagged.scrollIntoViewIfNeeded().catch(() => {});
await flagged.click({ timeout: 4000 }).catch(() => {});
await page.waitForTimeout(2800);

// 5. The supervision log — the integrity incident beside the verdict.
const log = page.locator(".supervision-log").first();
await log.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2400);

await context.close();
const video = page.video();
if (video) {
  await video.saveAs(out);
  console.log(`saved ${out}`);
}
await browser.close();

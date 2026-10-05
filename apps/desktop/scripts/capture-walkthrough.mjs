// One-off demo capture: records the replay judge path as a video —
// fixture click, auto-opened Inspector, claim timeline, supervision log,
// flagged-file diff, in-browser evidence-pack verification.
// Run: node scripts/capture-walkthrough.mjs <out.webm>
// Needs vite dev on :1420 and the demo bridge on :7420. Convert with:
//   ffmpeg -i out.webm -c:v libx264 -pix_fmt yuv420p out.mp4
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "build/pex-walkthrough.webm";
mkdirSync("build/video", { recursive: true });

const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: "build/video", size: { width: 1280, height: 800 } },
  acceptDownloads: true,
});
const page = await context.newPage();

await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

// 1. The fixture grid with its arc summaries.
const grid = page.locator(".demo-replay");
await grid.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2200);

// 2. Replay the flagship arc — "Replaying…" state, then the Inspector opens.
const fixture = page.locator(
  '.demo-replay button:has-text("Reward hacking: edited acceptance test")',
);
await fixture.click({ timeout: 5000 });
await page.waitForTimeout(1500);

// The replay POST adjudicates the trajectory; the Inspector auto-opens.
await page
  .locator('button:has-text("Inspector")')
  .first()
  .waitFor({ state: "visible", timeout: 180000 })
  .catch(() => {});
// Wait for the adjudicated verdict section to exist (replay complete).
await page
  .locator(".verification-timeline")
  .first()
  .waitFor({ state: "visible", timeout: 180000 })
  .catch(() => {});
await page.waitForTimeout(1800);

// 3. Claim timeline — worker statements beside verdicts.
const timeline = page.locator(".verification-timeline").first();
await timeline.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2600);

// 4. Expand a flagged file's sealed-baseline diff.
const flagged = page.locator(".verification-flagged button").first();
await flagged.scrollIntoViewIfNeeded().catch(() => {});
await flagged.click({ timeout: 4000 }).catch(() => {});
await page.waitForTimeout(2600);

// 5. The supervision log — bounded intervention in one glance.
const log = page.locator(".supervision-log").first();
await log.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2400);

// 6. Evidence pack — in-browser digest recomputation.
const packBtn = page.locator('button:has-text("Evidence pack")').first();
await packBtn.scrollIntoViewIfNeeded().catch(() => {});
await packBtn.click({ timeout: 4000 }).catch(() => {});
await page.waitForTimeout(1500);
const packDetails = page.locator("details.pack-verification summary").first();
await packDetails.click({ timeout: 4000 }).catch(() => {});
await packDetails.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2600);

await context.close();
const video = page.video();
if (video) {
  await video.saveAs(out);
  console.log(`saved ${out}`);
}
await browser.close();

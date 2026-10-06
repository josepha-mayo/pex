// Demo capture: records the durable-ruling arc as a video — a worker dispute
// escalates, the human's ruling journals onto the goal ledger, and a second
// attached replay is caught by that ruling (not the goal text).
// Run: node scripts/capture-ruling-arc.mjs <out.webm>
// Needs vite dev on :1420 and the demo bridge on :7420. Convert with:
//   ffmpeg -i out.webm -c:v libx264 -pix_fmt yuv420p out.mp4
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "build/pex-ruling-arc.webm";
mkdirSync("build/video", { recursive: true });

const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: "build/video", size: { width: 1280, height: 800 } },
});
const page = await context.newPage();

const nav = (label) =>
  page.locator(".surface-switch button", { hasText: label }).first();
const deckTab = (label) =>
  page.locator("aside button", { hasText: label }).first();

await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

// 1. The fixture grid.
const grid = page.locator(".demo-replay");
await grid.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(1800);

// 2. Replay the worker-dispute fixture — the standoff escalates to the human.
// The Inspector auto-opens once adjudication lands.
const dispute = page.locator(
  '.demo-replay button:has-text("disputes the nudge")',
);
await dispute.click({ timeout: 8000 });
await page
  .locator(".verification-timeline, .supervision-log")
  .first()
  .waitFor({ state: "visible", timeout: 180000 })
  .catch(() => {});
await page.waitForTimeout(2200);

// 3. Deck → Decisions — the dispute card quotes the worker verbatim.
await nav("Deck").click({ timeout: 5000 });
await page.waitForTimeout(1200);
await deckTab("Decisions").click({ timeout: 5000 });
const card = page.locator(".decision-card").first();
await card.waitFor({ state: "visible", timeout: 120000 });
await card.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2800);

// 4. Type the ruling and record it — the card leaves the inbox.
const rulingBox = page.locator('input[id^="general-decision-answer-"]').first();
await rulingBox.click({ timeout: 10000 });
await rulingBox.pressSequentially("Do not modify the sealed baseline test file", {
  delay: 45,
});
await page.waitForTimeout(900);
await page
  .locator('button[type="submit"]:has-text("Record answer")')
  .first()
  .click({ timeout: 5000 });
await page.waitForTimeout(3000);

// 5. Context tab — the journaled ruling sits atop the durable ledger.
await deckTab("Context").click({ timeout: 5000 });
await page.waitForTimeout(2600);

// 6. Home → attach the next replay to the ruled goal.
await nav("Home").click({ timeout: 5000 });
await page.waitForTimeout(1500);
const attachToggle = page.locator('.replay-attach input[type="checkbox"]');
await attachToggle.scrollIntoViewIfNeeded().catch(() => {});
await attachToggle.check({ timeout: 5000 }).catch(() => {});
await page.waitForTimeout(1400);

// 7. Replay the second-act trajectory against the ruled goal — the nudge
// cites the human's recorded ruling, not the goal text.
const continuity = page.locator(
  '.demo-replay button:has-text("Second-act replay")',
);
await continuity.click({ timeout: 8000 });
await page
  .locator(".supervision-log")
  .first()
  .waitFor({ state: "visible", timeout: 180000 })
  .catch(() => {});
await page.waitForTimeout(1800);

// 8. Deck → Interventions — the nudge's evidence entry cites the journaled
// ruling verbatim. Expand the evidence list so the citation is on camera.
await nav("Deck").click({ timeout: 5000 });
await page.waitForTimeout(1000);
await deckTab("Interventions").click({ timeout: 5000 });
await page.waitForTimeout(1600);
const nudgeRow = page.locator('.audit-row:has-text("Send Nudge")').first();
await nudgeRow.scrollIntoViewIfNeeded().catch(() => {});
await nudgeRow.locator("details summary").first().click({ timeout: 4000 }).catch(() => {});
await page.waitForTimeout(3400);

await context.close();
const video = page.video();
if (video) {
  await video.saveAs(out);
  console.log(`saved ${out}`);
}
await browser.close();

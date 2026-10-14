// Records the durable-intent arc as a video: a worker disputes PEX's nudge
// and stops unresolved → the verdict card routes to Decisions → a typed human
// ruling journals onto the goal ledger → a compliant second act attaches to
// the ruled goal → Deck > Goals shows one intent governing both runs.
// Run: node scripts/capture-judge-arc.mjs <out.webm>
// Needs vite dev on :1420 and the demo bridge on :7420. Convert with:
//   ffmpeg -i out.webm -c:v libx264 -pix_fmt yuv420p out.mp4
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "build/pex-judge-arc.webm";
mkdirSync("build/video", { recursive: true });

const launchOpts = process.env.PEX_BROWSER_EXE
  ? { executablePath: process.env.PEX_BROWSER_EXE }
  : {};
const browser = await chromium.launch(launchOpts);
const context = await browser.newContext({
  recordVideo: { dir: "build/video", size: { width: 1280, height: 800 } },
});
const page = await context.newPage();
const RULING = "Do not modify the sealed baseline test file - flag it instead.";

await page.goto("http://127.0.0.1:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2600);

// 1. The fixture grid + journey checklist collapsed state.
const grid = page.locator(".demo-replay");
await grid.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2000);

// 2. Run the dispute fixture — worker justifies, stops unresolved.
await page
  .locator('.demo-replay button:has-text("Worker disputes the nudge")')
  .click({ timeout: 8000 });
// Verdict card lands with the ruling CTA.
await page
  .locator('button:has-text("open Decisions")')
  .first()
  .waitFor({ state: "visible", timeout: 180000 });
await page.waitForTimeout(2200);

// 3. The CTA routes to the waiting decision.
await page.locator('button:has-text("open Decisions")').first().click();
await page
  .locator(".decision-card")
  .first()
  .waitFor({ state: "visible", timeout: 15000 });
await page.waitForTimeout(2000);

// 4. Record the ruling — free text, journaled to the goal ledger.
const input = page.locator(".decision-card input").first();
await input.fill(RULING);
await page.waitForTimeout(900);
await page
  .locator('.decision-card button:has-text("Record")')
  .first()
  .click()
  .catch(async () => {
    await page.locator(".decision-card button[type=submit]").first().click();
  });
await page.waitForTimeout(3200);

// 5. Inspector on the dispute session — the journaled ruling + provenance.
const disputeId = await page.evaluate(async () => {
  const rows = await (await fetch("/v1/sessions")).json();
  const list = Array.isArray(rows) ? rows : rows.sessions || [];
  const hit = list.find((s) => s.id.includes("nudge_dispute_eval"));
  return hit ? hit.id : null;
});
if (disputeId) {
  await page.goto(
    `http://127.0.0.1:1420/#inspector/${encodeURIComponent(disputeId)}`,
    { waitUntil: "networkidle" },
  );
  await page.waitForTimeout(2600);
  const rulings = page.locator(".goal-rulings").first();
  await rulings.scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(2400);
}

// 6. Back on Home: attach the compliant second act to the ruled goal —
// the dispute session stays selected, so its goal is the attach target.
await page.goto("http://127.0.0.1:1420/#", { waitUntil: "networkidle" });
await page.waitForTimeout(2600);
const attach = page.locator('label.replay-attach:has-text("Attach") input');
if (await attach.count()) {
  await attach.check().catch(() => {});
}
await page
  .locator('.demo-replay button:has-text("the worker complies")')
  .click({ timeout: 8000 });
await page
  .locator(".replay-verdict")
  .first()
  .waitFor({ state: "visible", timeout: 180000 });
await page.waitForTimeout(2400);

// 7. Deck > Goals — one intent governing both runs, ruled x1.
await page.goto("http://127.0.0.1:1420/#deck", { waitUntil: "networkidle" });
await page.waitForTimeout(3200);
await page.locator('button:has-text("Goals")').first().click();
await page.waitForTimeout(1600);
const card = page.locator(".goal-card").first();
await card.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2800);

await context.close();
const video = page.video();
if (video) {
  await video.saveAs(out);
  console.log(`saved ${out}`);
}
await browser.close();

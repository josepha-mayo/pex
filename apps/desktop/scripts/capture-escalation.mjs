// Captures the worker-initiated escalation artifacts from a bridge serving the
// 2026-10-14 live tamper home (goal goal_bdea5cf2…, session ses_ec4b20a7…):
// the ASK_HUMAN intervention the worker opened via pex_request_decision, and
// the durable ruling it received after the worker's turn ended.
//
// Run with the demo stack up (bridge :7420 + vite :1420):
//   node apps/desktop/scripts/capture-escalation.mjs            # stills
//   node apps/desktop/scripts/capture-escalation.mjs --video    # webm in build/video/
import { launchBrowser } from "./browser.mjs";
import { mkdirSync } from "node:fs";

const UI = process.env.PEX_UI_URL ?? "http://[::1]:1420";
const SESSION = "opencode:ses_ec4b20a7effe7JIN0SWxV87kc1";
const VIDEO = process.argv.includes("--video");

const browser = await launchBrowser();
const context = await browser.newContext({
  viewport: { width: 1280, height: 900 },
  ...(VIDEO
    ? { recordVideo: { dir: "build/video", size: { width: 1280, height: 900 } } }
    : {}),
});
if (VIDEO) mkdirSync("build/video", { recursive: true });
const page = await context.newPage();

const shot = async (name) => {
  if (!VIDEO) await page.screenshot({ path: `build/${name}`, fullPage: false });
};
const dwell = (ms) => page.waitForTimeout(ms);

// Inspector deep-linked to the escalation session: session card (PEX ×N chip)
// plus the supervision log row for the worker's own request_decision call.
await page.goto(`${UI}/#inspector/${encodeURIComponent(SESSION)}`, {
  waitUntil: "domcontentloaded",
});
await dwell(VIDEO ? 8000 : 6000);
await shot("escalation-inspector.png");

// Expand the goal "Checks and details" disclosure to reach Recorded rulings.
const details = page
  .locator('summary:has-text("Checks and details")')
  .first();
if (await details.count()) {
  await details.scrollIntoViewIfNeeded();
  await details.click({ timeout: 6000 }).catch(() => {});
  await dwell(VIDEO ? 2500 : 1500);
}
const rulings = page.locator(".goal-rulings").first();
if (await rulings.count()) {
  await rulings.scrollIntoViewIfNeeded();
  await dwell(VIDEO ? 2500 : 600);
}
await shot("escalation-rulings.png");

// Deck -> Interventions: the ASK_HUMAN row shows diagnosis + the honest
// session_terminal delivery receipt.
await page
  .locator('button:has-text("Deck"), [role="tab"]:has-text("Deck")')
  .first()
  .click({ timeout: 6000 })
  .catch(() => {});
await dwell(4000);
await page
  .locator('button:has-text("Interventions"), [role="tab"]:has-text("Interventions")')
  .first()
  .click({ timeout: 6000 })
  .catch(() => {});
await dwell(VIDEO ? 8000 : 6000);
await page
  .waitForSelector('article:has-text("decision"), :has-text("mcp_request_decision")', {
    timeout: 15000,
  })
  .catch(() => {});
const card = page
  .locator('article:has-text("test_csv_utils"), article:has-text("forbidden")')
  .first();
if (await card.count()) {
  await card.scrollIntoViewIfNeeded();
  await dwell(VIDEO ? 2500 : 500);
}
await shot("escalation-interventions.png");

if (VIDEO) await dwell(1500); // let the last frame breathe before the recorder stops
await context.close();
await browser.close();
console.log(VIDEO ? "wrote build/video/*.webm" : "wrote build/escalation-*.png");

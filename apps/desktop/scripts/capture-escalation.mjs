// Captures the worker-initiated escalation artifacts from a bridge serving the
// 2026-10-14 live tamper home (goal goal_bdea5cf2…, session ses_ec4b20a7…):
// the ASK_HUMAN intervention the worker opened via pex_request_decision, and
// the durable ruling it received after the worker's turn ended.
//
// Run with the demo stack up (bridge :7420 + vite :1420):
//   node apps/desktop/scripts/capture-escalation.mjs
import { launchBrowser } from "./browser.mjs";

const UI = process.env.PEX_UI_URL ?? "http://127.0.0.1:1420";
const SESSION = "opencode:ses_ec4b20a7effe7JIN0SWxV87kc1";

const browser = await launchBrowser();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

// Inspector deep-linked to the escalation session: session card (PEX ×N chip)
// plus the supervision log row for the worker's own request_decision call.
await page.goto(`${UI}/#inspector/${encodeURIComponent(SESSION)}`, {
  waitUntil: "domcontentloaded",
});
await page.waitForTimeout(6000);
await page.screenshot({ path: "build/escalation-inspector.png", fullPage: false });

// Expand the goal "Checks and details" disclosure to reach Recorded rulings.
const details = page
  .locator('summary:has-text("Checks and details")')
  .first();
if (await details.count()) {
  await details.scrollIntoViewIfNeeded();
  await details.click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(1500);
}
const rulings = page.locator(".goal-rulings").first();
if (await rulings.count()) {
  await rulings.scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);
}
await page.screenshot({ path: "build/escalation-rulings.png", fullPage: false });

// Deck -> Interventions: the ASK_HUMAN row shows diagnosis + the honest
// session_terminal delivery receipt.
await page
  .locator('button:has-text("Deck"), [role="tab"]:has-text("Deck")')
  .first()
  .click({ timeout: 6000 })
  .catch(() => {});
await page.waitForTimeout(4000);
await page
  .locator('button:has-text("Interventions"), [role="tab"]:has-text("Interventions")')
  .first()
  .click({ timeout: 6000 })
  .catch(() => {});
await page.waitForTimeout(6000);
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
  await page.waitForTimeout(500);
}
await page.screenshot({ path: "build/escalation-interventions.png", fullPage: false });

await browser.close();
console.log("wrote build/escalation-*.png");

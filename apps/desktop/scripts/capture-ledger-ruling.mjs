import { chromium } from "playwright";
const browser = await chromium.launch({
  executablePath: process.env.PEX_BROWSER_EXE || "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://[::1]:1420", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(5000);
// Deck -> Context: the recorded ruling should appear as a human decision.
await page.locator('button:has-text("Deck"), [role="tab"]:has-text("Deck")').first().click({ timeout: 6000 }).catch(() => {});
await page.waitForTimeout(4000);
await page.locator('button:has-text("Context"), [role="tab"]:has-text("Context")').first().click({ timeout: 4000 }).catch(() => {});
await page.waitForTimeout(6000);
await page.waitForSelector('article:has-text("Keep the requirement")', { timeout: 20000 }).catch(() => {});
const ruling = page.locator('article:has-text("Keep the requirement")').first();
if (await ruling.count()) {
  await ruling.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
}
await page.screenshot({ path: "build/ledger-ruling-context.png", fullPage: false });
// Deck -> Interventions: the audit row should show the journaled ledger ref.
await page.locator('button:has-text("Interventions"), [role="tab"]:has-text("Interventions")').first().click({ timeout: 4000 }).catch(() => {});
await page.waitForTimeout(6000);
await page.waitForSelector('article:has-text("Journaled to the goal")', { timeout: 20000 }).catch(() => {});
const audit = page.locator('article:has-text("Journaled to the goal")').first();
if (await audit.count()) {
  await audit.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await audit.screenshot({ path: "build/ledger-ruling-audit.png" });
}
await page.screenshot({ path: "build/ledger-ruling-interventions.png", fullPage: false });
await browser.close();

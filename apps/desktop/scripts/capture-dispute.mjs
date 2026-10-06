import { chromium } from "playwright";
const browser = await chromium.launch({
  executablePath: process.env.PEX_BROWSER_EXE || "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(4000);
// Home metric "need you" navigates to Deck -> Decisions
const need = page.locator('button:has-text("need you")').first();
try { await need.click({ timeout: 4000 }); } catch {
  await page.locator('button:has-text("Deck"), [role="tab"]:has-text("Deck")').first().click({ timeout: 3000 }).catch(() => {});
}
await page.waitForTimeout(4000);
const decisions = page.locator('button:has-text("Decisions"), [role="tab"]:has-text("Decisions")').first();
try { await decisions.click({ timeout: 3000 }); } catch {}
await page.waitForTimeout(4000);
await page.screenshot({ path: "build/dispute-decisions.png", fullPage: false });
const card = page.locator('.decision-card:has-text("answered PEX")').first();
if (await card.count()) await card.screenshot({ path: "build/dispute-card.png" });
await browser.close();

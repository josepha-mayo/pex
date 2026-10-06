import { chromium } from "playwright";
const browser = await chromium.launch({
  executablePath: process.env.PEX_BROWSER_EXE || "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://[::1]:1420", { waitUntil: "domcontentloaded" });
await page.waitForTimeout(5000);
// Home metric "need you" navigates to Deck -> Decisions
const need = page.locator('button:has-text("need you"), [role="button"]:has-text("need you")').first();
try { await need.click({ timeout: 4000 }); } catch {
  await page.locator('button:has-text("Deck"), [role="tab"]:has-text("Deck")').first().click({ timeout: 3000 }).catch(() => {});
}
await page.waitForTimeout(4000);
const decisions = page.locator('button:has-text("Decisions"), [role="tab"]:has-text("Decisions")').first();
try { await decisions.click({ timeout: 3000 }); } catch {}
await page.waitForTimeout(4000);
await page.screenshot({ path: "build/dispute-decisions.png", fullPage: false });
const card = page.locator('.decision-card:has-text("answered PEX")').first();
if (await card.count()) {
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({ path: "build/dispute-card.png" });
  // Fill the ruling field to show the affordance, then leave it unsubmitted.
  const input = card.locator('input').first();
  if (await input.count()) {
    await input.fill("Keep the requirement; restore the sealed test file.");
    await page.waitForTimeout(300);
    await card.screenshot({ path: "build/dispute-card-resolve.png" });
  }
}
await browser.close();

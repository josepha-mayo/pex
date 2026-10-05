// One-off capture: Evidence-pack browser verification panel in the Inspector.
// Run: node scripts/capture-pack-verify.mjs <session-id> <out.png>
import { chromium } from "playwright";

const sessionId = process.argv[2];
const out = process.argv[3] || "build/pack-verify.png";

const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);

if (sessionId) {
  try {
    await page.locator(`button.worker-choice[title="${sessionId}"]`).click({ timeout: 4000 });
  } catch {
    await page.locator('button.worker-choice:has-text("Recorded replay")').last().click({ timeout: 3000 }).catch(() => {});
  }
  await page.waitForTimeout(800);
}

const inspect = page.locator('button:has-text("Inspect current state"), button:has-text("Inspect")').first();
try {
  await inspect.click({ timeout: 3000 });
} catch {}
await page.waitForTimeout(1000);

await page.locator('button:has-text("Evidence pack")').click({ timeout: 5000 });
await page.waitForSelector(".pack-verification", { timeout: 15000 });

// Expand the check list and scroll it into view.
await page.locator(".pack-verification summary").click();
const block = page.locator(".pack-verification").first();
await block.scrollIntoViewIfNeeded();
await page.waitForTimeout(500);

await page.screenshot({ path: out, fullPage: false });
console.log("wrote", out);
await browser.close();

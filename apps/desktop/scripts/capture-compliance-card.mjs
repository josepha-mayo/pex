// Screenshot the verdict card for the positive-control fixture
// (ruling_compliance_eval): a worker that complies with the recorded
// ruling is verified rather than blocked — the ledger governs both ways.
// Run: node scripts/capture-compliance-card.mjs
// Needs vite dev on :1420 and the demo bridge on :7420.
import { chromium } from "playwright";

const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:1420", { waitUntil: "domcontentloaded" });

const fixtureButton = page.locator(
  'button:has-text("complies with the recorded ruling")',
);
await fixtureButton.waitFor({ state: "visible", timeout: 30000 });
await fixtureButton.click();

const card = page.locator(".replay-verdict").first();
await card.waitFor({ state: "visible", timeout: 300000 });
await page.locator("text=Declared arc").waitFor({ timeout: 60000 });
await page.waitForTimeout(800);
await card.scrollIntoViewIfNeeded();
await card.screenshot({ path: "build/compliance-card.png" });
await browser.close();

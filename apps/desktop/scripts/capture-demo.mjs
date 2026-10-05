// One-off demo capture: screenshot the Inspector on a replayed session.
// Run: node scripts/capture-demo.mjs  (needs vite dev on :1420 and the demo
// bridge on :7420 with at least one replayed session).
import { chromium } from "playwright";

const sessionId = process.argv[2] || process.env.PEX_DEMO_SESSION || "";
const out = process.argv[3] || "build/demo-inspector.png";

const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);

if (sessionId) {
  // Click the target session row in the worker rail (title = session id).
  try {
    await page.locator(`button.worker-choice[title="${sessionId}"]`).click({ timeout: 4000 });
  } catch {
    // Fallback: any replay row.
    await page.locator('button.worker-choice:has-text("Recorded replay")').last().click({ timeout: 3000 }).catch(() => {});
  }
  await page.waitForTimeout(800);
}

// Open inspector if a button exists.
const inspect = page.locator('button:has-text("Inspect current state"), button:has-text("Inspect")').first();
try {
  await inspect.click({ timeout: 3000 });
} catch {}
await page.waitForTimeout(1000);

// The claim-verification report is open by default — no expansion needed.
await page.waitForTimeout(600);

// Scroll the verdict timeline into view before shooting.
const timeline = page.locator(".verification-timeline").first();
try {
  await timeline.scrollIntoViewIfNeeded({ timeout: 3000 });
  await page.waitForTimeout(400);
} catch {}

await page.screenshot({ path: out, fullPage: true });
console.log("wrote", out);
await browser.close();

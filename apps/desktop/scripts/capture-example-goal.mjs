// One-off demo capture: screenshot the goal composer after the
// "Load a worked example" fill. Run: node scripts/capture-example-goal.mjs
// (needs vite dev on :1420 and the demo bridge on :7420).
import { chromium } from "playwright";

const outAfter = process.argv[2] || "build/goal-example.png";
const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(1200);

// Select a replay session so a workspace is bound.
const replayRow = page.locator('button.worker-choice:has-text("Recorded replay")').first();
try {
  await replayRow.click({ timeout: 4000 });
} catch {}
await page.waitForTimeout(800);

// The composer lives on the Inspector tab inside a collapsed details.
await page.locator('button:has-text("Inspector")').first().click({ timeout: 4000 });
await page.waitForTimeout(800);
const editor = page.locator('details.goal-editor > summary:has-text("goal")').first();
await editor.scrollIntoViewIfNeeded().catch(() => {});
await editor.click({ timeout: 5000 });
await page.waitForTimeout(400);

const exampleBtn = page.locator('button.linklike:has-text("Load a worked example")');
await exampleBtn.click({ timeout: 5000 });
await page.waitForTimeout(500);

// Open optional details so the fill is visible in one frame.
await page.locator('details.goal-editor details.goal-options > summary:has-text("Optional details")').click();
await page.waitForTimeout(400);

const form = page.locator("details.goal-editor");
await form.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(300);
await page.locator("text=Goal name").scrollIntoViewIfNeeded().catch(() => {});
await page.screenshot({ path: outAfter, fullPage: false });
console.log(`saved ${outAfter}`);
await browser.close();

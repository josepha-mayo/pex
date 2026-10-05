import { chromium } from "playwright";

const sessionId = "synthetic:replay-tampered_acceptance_eval-f9b4e4f5";
const out = "docs/demo/assets/pex-tamper-diff-c281f0f.png";

const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

try {
  await page.locator(`button.worker-choice[title="${sessionId}"]`).click({ timeout: 4000 });
} catch {
  await page.locator('button.worker-choice:has-text("Recorded replay")').last().click({ timeout: 3000 }).catch(() => {});
}
await page.waitForTimeout(800);

const inspect = page.locator('button:has-text("Inspect current state"), button:has-text("Inspect")').first();
try { await inspect.click({ timeout: 3000 }); } catch {}
await page.waitForTimeout(1200);

// Click a flagged-file diff chip to expand the sealed-baseline diff.
try {
  await page.locator("button.flag-file").first().click({ timeout: 4000 });
  console.log("diff chip clicked");
} catch { console.log("no diff chip found"); }
await page.waitForTimeout(1200);

// Scroll the diff into view inside the scrollable inspector.
try {
  await page.locator(".flag-diff, .flag-diff-note").first().scrollIntoViewIfNeeded();
} catch {}
await page.waitForTimeout(500);

await page.screenshot({ path: out });
console.log("wrote", out);
await browser.close();

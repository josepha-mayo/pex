import { chromium } from "playwright";

const sessionId = process.env.PEX_SESSION_ID || "opencode:ses_ef462b2baffeRVDEyHgFv6KRin";
const out = "../../docs/demo/assets/pex-live-handoff-d02df03.png";

const browser = await chromium.launch({
  executablePath:
    process.env.PEX_BROWSER_EXE ||
    "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

try {
  await page.locator(`button.worker-choice[title="${sessionId}"]`).click({ timeout: 4000 });
  console.log("worker picked by title");
} catch {
  try { await page.locator('button.worker-choice:has-text("Live")').first().click({ timeout: 3000 }); console.log("worker picked by badge"); }
  catch { console.log("no worker button"); }
}
await page.waitForTimeout(800);

const inspect = page.locator('button:has-text("Inspect current state"), button:has-text("Inspect")').first();
try { await inspect.click({ timeout: 3000 }); console.log("inspector opened"); } catch {}
await page.waitForTimeout(1500);

try {
  await page.locator(".handoff-row").first().scrollIntoViewIfNeeded();
  console.log("handoff row visible");
} catch { console.log("no handoff row"); }
await page.waitForTimeout(600);

await page.screenshot({ path: out });
console.log("wrote", out);
await browser.close();

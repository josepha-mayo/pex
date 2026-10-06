// Screenshot the "Challenge the supervisor" panel on Home, expanded with the
// schema template loaded.
import { chromium } from "playwright";
const browser = await chromium.launch({
  executablePath: process.env.PEX_BROWSER_EXE || "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 1500 } });
await page.goto("http://[::1]:1420", { waitUntil: "domcontentloaded" });
await page.waitForSelector('.demo-challenge', { timeout: 30000 });
await page.waitForTimeout(1500);
const block = page.locator('.demo-challenge').first();
await block.locator('summary').click();
await page.waitForTimeout(400);
await block.locator('button.linklike').click();
await page.waitForTimeout(300);
await block.scrollIntoViewIfNeeded();
await page.waitForTimeout(400);
await block.screenshot({ path: "build/demo-challenge.png" });
await browser.close();

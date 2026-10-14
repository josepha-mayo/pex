// Screenshot the "Challenge the supervisor" panel on Home, expanded with the
// schema template loaded.
import { launchBrowser } from "./browser.mjs";
const browser = await launchBrowser();
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

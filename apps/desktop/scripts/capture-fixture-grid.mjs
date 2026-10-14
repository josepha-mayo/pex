// Screenshot the Recorded-replay fixture block on Home.
import { launchBrowser } from "./browser.mjs";
const browser = await launchBrowser();
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
await page.goto("http://localhost:1420", { waitUntil: "domcontentloaded" });
const block = page.locator('.demo-replay').first();
await block.waitFor({ state: "visible", timeout: 30000 });
await page.waitForTimeout(1500);
await block.scrollIntoViewIfNeeded();
await page.waitForTimeout(500);
await block.screenshot({ path: "build/fixture-grid.png" });
await browser.close();

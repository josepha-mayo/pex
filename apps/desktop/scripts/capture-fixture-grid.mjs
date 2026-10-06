// Screenshot the Recorded-replay fixture block on Home.
import { chromium } from "playwright";
const browser = await chromium.launch({
  executablePath: process.env.PEX_BROWSER_EXE || "C:/Program Files (x86)/Microsoft/EdgeCore/154.0.4258.53/msedge.exe",
});
const page = await browser.newPage({ viewport: { width: 1280, height: 1400 } });
await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
const block = page.locator('.demo-replay').first();
await block.scrollIntoViewIfNeeded();
await page.waitForTimeout(500);
await block.screenshot({ path: "build/fixture-grid.png" });
await browser.close();

import { launchBrowser } from "./browser.mjs";

const browser = await launchBrowser();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto("http://localhost:1420/", { waitUntil: "domcontentloaded" });
await page.waitForSelector(".worker-choice", { timeout: 30000 });
await page.waitForSelector(".verdict-chip", { timeout: 15000 }).catch(() => {});
await page.locator(".worker-rail").screenshot({ path: "../../build/rail-chip.png" });
await browser.close();
console.log("captured build/rail-chip.png");

// One-off screenshot: the premature-stop verdict card with the claim
// ledger — the "same words, different verdicts" visual for the Pages site.
// Run: node scripts/capture-verdict-png.mjs <out.png>
// Needs vite dev on :1420 and the demo bridge on :7420.
import { launchBrowser } from "./browser.mjs";

const out = process.argv[2] || "build/pex-verdict-card.png";

const browser = await launchBrowser();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 1.5,
});
const page = await context.newPage();
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 300)));

await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

const fixture = page.locator(
  '.demo-replay button:has-text("False completion")',
);
await fixture.click({ timeout: 5000 });
// The pending placeholder shares .replay-verdict — the claims list only
// exists once adjudication lands, so that is the wait target.
await page
  .locator(".replay-verdict-claims")
  .first()
  .waitFor({ state: "visible", timeout: 180000 });
await page.waitForTimeout(1200);

const card = page.locator(".replay-verdict").first();
await card.scrollIntoViewIfNeeded();
await page.waitForTimeout(800);
await card.screenshot({ path: out });

await context.close();
await browser.close();
console.log(`screenshot -> ${out}`);

// One-off demo capture: the claim-ledger beat as video — the worker says
// "All tests passed" twice; PEX contradicts the first (premature stop) and
// verifies the second (real pytest evidence). Same words, different
// verdicts — the thesis rendered.
// Run: node scripts/capture-claim-ledger.mjs <out.webm>
// Needs vite dev on :1420 and the demo bridge on :7420. Convert with:
//   ffmpeg -i out.webm -c:v libx264 -pix_fmt yuv420p out.mp4
import { launchBrowser } from "./browser.mjs";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "build/pex-claim-ledger.webm";
mkdirSync("build/video", { recursive: true });

const browser = await launchBrowser();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: "build/video", size: { width: 1280, height: 800 } },
});
const page = await context.newPage();
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 300)));

await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

// 1. Fixture grid — settle, then run the "start here" premature-stop arc.
const grid = page.locator(".demo-replay");
await grid.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(1800);

const fixture = page.locator(
  '.demo-replay button:has-text("False completion")',
);
await fixture.click({ timeout: 5000 });

// 2. Wait for the verdict — the pending placeholder shares .replay-verdict,
//    so the claims list is the true adjudication-landed signal.
await page
  .locator(".replay-verdict-claims")
  .first()
  .waitFor({ state: "visible", timeout: 180000 });
await page.waitForTimeout(1500);
const ledger = page.locator(".replay-verdict-claims").first();
if (await ledger.count()) {
  await ledger.scrollIntoViewIfNeeded();
}
await page.waitForTimeout(5500);

// 3. Slow scroll across the ledger rows so each verdict reads on camera.
const rows = page.locator(".replay-verdict-claim");
const n = await rows.count();
for (let i = 0; i < n; i++) {
  await rows.nth(i).scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(1400);
}

// 4. Land back on the full verdict card for the closing frame.
await page.locator(".replay-verdict").first().scrollIntoViewIfNeeded();
await page.waitForTimeout(3000);

await context.close();
await browser.close();
console.log(`captured -> ${out} (build/video/*.webm)`);

// Demo capture: records the worker↔supervisor MCP arc — a replayed live run
// where the real OpenCode worker called pex_pex_get_goal before editing and
// pex_pex_verify_claim before claiming done. The session row shows the
// "PEX ×2" chip, the Inspector shows the consultation fact, and the evidence
// pack carries the calls in its signed event ledger.
// Run: node scripts/capture-mcp-eval.mjs <out.webm>
// Needs vite dev on :1420 and the demo bridge on :7420. Convert with:
//   ffmpeg -i out.webm -c:v libx264 -pix_fmt yuv420p out.mp4
import { launchBrowser } from "./browser.mjs";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "build/pex-mcp-eval.webm";
mkdirSync("build/video", { recursive: true });

const browser = await launchBrowser();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: "build/video", size: { width: 1280, height: 800 } },
});
const page = await context.newPage();

const nav = (label) =>
  page.locator(".surface-switch button", { hasText: label }).first();
const deckTab = (label) =>
  page.locator("aside button", { hasText: label }).first();

await page.goto("http://localhost:1420", { waitUntil: "networkidle" });
await page.waitForTimeout(2500);

// 1. The fixture grid — the captured worker-MCP run is a first-class card.
const grid = page.locator(".demo-replay");
await grid.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(1800);

// 2. Replay it — the deterministic arc adjudicates, then the Inspector
// auto-opens on the recorded session.
const fixture = page.locator(
  '.demo-replay button:has-text("asks PEX to verify")',
);
await fixture.click({ timeout: 8000 });
await page
  .locator(".verification-timeline, .supervision-log")
  .first()
  .waitFor({ state: "visible", timeout: 180000 })
  .catch(() => {});
await page.waitForTimeout(2200);

// 3. Inspector — "Worker ↔ PEX tools · worker consulted supervision ×2" sits
// in the session facts beside the recorded-replay provenance.
const pexFact = page.locator('dt:has-text("Worker ↔ PEX tools")').first();
await pexFact.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(3200);

// 4. Deck → Interventions — the run's REQUEST_VERIFICATION lands in the
// audit trail alongside the journaled adjudication.
await nav("Deck").click({ timeout: 5000 });
await page.waitForTimeout(1200);
await deckTab("Interventions").click({ timeout: 5000 });
await page.waitForTimeout(2000);
const verifyRow = page
  .locator('.audit-row:has-text("Request Verification"), .audit-row:has-text("Send Nudge")')
  .first();
await verifyRow.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2800);

// 5. Home/Now — the session rail card carries the PEX ×2 chip next to its
// recorded-replay badge: the consulted-supervision signal scans at a glance.
await nav("Home").click({ timeout: 5000 });
await page.waitForTimeout(1200);
const chip = page.locator(".pex-calls-badge").first();
await chip.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(3200);

await context.close();
const video = page.video();
if (video) {
  await video.saveAs(out);
  console.log(`saved ${out}`);
}
await browser.close();

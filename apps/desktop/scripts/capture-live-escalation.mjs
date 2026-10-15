// One-off capture: the LIVE tamper-escalation arc — a real OpenCode worker
// (nemotron-3-ultra-free) read the seeded tamper task, noticed it conflicts
// with the sealed goal's forbidden outcomes, and escalated to a human via
// pex.request_decision before touching the test file. The Inspector shows
// the pending question + the recorded human ruling.
// Run: node scripts/capture-live-escalation.mjs <out.webm>
// Needs vite dev on :1420 and the demo bridge on :7420 with the live session.
import { launchBrowser } from "./browser.mjs";
import { mkdirSync } from "node:fs";

const out = process.argv[2] || "build/pex-live-escalation.webm";
const sessionId = process.argv[3] || "opencode:ses_ebefc8663ffe25ZFYxcnozWjlS";
mkdirSync("build/video", { recursive: true });

const browser = await launchBrowser();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: "build/video", size: { width: 1280, height: 800 } },
});
const page = await context.newPage();
page.on("pageerror", (e) => console.log("[pageerror]", String(e).slice(0, 300)));

await page.goto(`http://localhost:1420/#inspector/${encodeURIComponent(sessionId)}`, {
  waitUntil: "networkidle",
});
await page.waitForTimeout(3500);

// Let the inspector settle on the live session, then scroll the intervention
// history so the ASK_HUMAN card and the recorded ruling are both visible.
const inspector = page.locator(".inspector, main, body").first();
await inspector.scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(2000);

// Scroll slowly through the surface so motion reads on video.
for (let i = 0; i < 6; i++) {
  await page.mouse.wheel(0, 420);
  await page.waitForTimeout(1400);
}
for (let i = 0; i < 6; i++) {
  await page.mouse.wheel(0, -420);
  await page.waitForTimeout(1400);
}
await page.waitForTimeout(2000);

await page.screenshot({ path: "build/live-escalation-inspector.png", fullPage: false });
await context.close();
await browser.close();
console.log("captured", out);

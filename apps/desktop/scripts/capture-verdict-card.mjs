// Screenshot the verdict card for premature_stop_eval — the "start here"
// fixture: narration check, verified facts, stats, declared arc, completion.
// Run: node scripts/capture-verdict-card.mjs
// Needs vite dev on :1420 and the demo bridge on :7420.
import { launchBrowser } from "./browser.mjs";

const browser = await launchBrowser();
try {
  // Tall viewport so the verdict card is on-screen without scrolling —
  // element screenshots through nested scroll containers can clip the
  // wrong painted region.
  const page = await browser.newPage({ viewport: { width: 1280, height: 2400 } });
  await page.goto("http://localhost:1420", { waitUntil: "domcontentloaded" });

  const fixtureButton = page.locator(
    '.demo-replay button:has-text("False completion without tests")',
  );
  await fixtureButton.waitFor({ state: "visible", timeout: 30000 });
  await fixtureButton.click();

  const card = page.locator(".replay-verdict").first();
  await card.waitFor({ state: "visible", timeout: 300000 });
  await card.locator("text=premature_stop_eval").waitFor({ timeout: 60000 });
  await card.locator("text=Narration check").waitFor({ timeout: 60000 });
  await page.waitForTimeout(800);
  const box = await card.boundingBox();
  await page.screenshot({
    path: "build/verdict-card.png",
    clip: box ? { x: box.x, y: box.y, width: box.width, height: box.height } : undefined,
  });
  console.log("captured build/verdict-card.png");
} finally {
  await browser.close();
}

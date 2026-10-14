// Shared browser resolution for the capture scripts: PEX_BROWSER_EXE wins,
// then the newest installed EdgeCore runtime, then Playwright's bundled
// chromium. Hardcoded Edge version paths go stale on every browser update —
// resolve dynamically instead.
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const EDGECORE_ROOT = "C:/Program Files (x86)/Microsoft/EdgeCore";

function edgeCandidates() {
  const dirs = [EDGECORE_ROOT, "C:/Program Files (x86)/Microsoft/Edge/Application"];
  const found = [];
  for (const root of dirs) {
    try {
      for (const entry of readdirSync(root)) {
        if (!/^\d+\.\d+\.\d+\.\d+$/.test(entry)) continue;
        const exe = join(root, entry, "msedge.exe");
        if (existsSync(exe)) found.push(exe);
      }
    } catch {
      // directory absent
    }
  }
  // Version-directory names sort lexically for our purposes only after
  // zero-padding; pick the max by numeric compare instead.
  return found.sort((a, b) => {
    const pa = a.split(/[\\/]/).at(-2).split(".").map(Number);
    const pb = b.split(/[\\/]/).at(-2).split(".").map(Number);
    for (let i = 0; i < 4; i += 1) if (pa[i] !== pb[i]) return pa[i] - pb[i];
    return 0;
  });
}

export async function launchBrowser(options = {}) {
  const envPath = process.env.PEX_BROWSER_EXE;
  const candidates = envPath ? [envPath] : [...edgeCandidates(), null];
  let lastError;
  for (const executablePath of candidates) {
    try {
      return await chromium.launch({ executablePath, ...options });
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError ?? new Error("no browser candidate found");
}

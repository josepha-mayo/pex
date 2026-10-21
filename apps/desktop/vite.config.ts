import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  // The hosted-only build never copies desktop public assets or pet sprites.
  publicDir: mode === "hosted" ? false : "public",
  plugins: [react()],
  clearScreen: false,
  // WEB-ONLY default: `uv run python scripts/demo.py` serves this web UI via
  // vite dev (or `vite preview` for the prebuilt dist with --prebuilt).
  // The packaged Tauri desktop is frozen/optional — no Rust/Tauri needed here.
  server: {
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
    // Browser-mode UI makes same-origin /v1 calls; forward them (and the
    // events socket) to the local bridge. Origin is rewritten to the trusted
    // vite origin so mutations and websockets pass the bridge origin guard.
    // Dev-only surface: JSON mutations from foreign sites still cannot
    // preflight, though bodiless POSTs to this proxy can spoof the trusted
    // origin — acceptable on require_auth=False dev bridges, which only exist
    // behind Settings.for_test.
    proxy: {
      // Isolated hosted replay service only; never forward this entry to /v1.
      ...(process.env.PEX_REPLAY_URL ? {
        "/api/replay": { target: process.env.PEX_REPLAY_URL, changeOrigin: true },
      } : {}),
      "/v1": {
        // demo.py moves the bridge when PEX_DEMO_PORT is set — the proxy must
        // follow, or the UI renders a different bridge's canonical state.
        target: process.env.PEX_BRIDGE_URL ?? "http://127.0.0.1:7420",
        changeOrigin: true,
        ws: true,
        headers: { origin: "http://127.0.0.1:1420" },
      },
    },
  },
  build: {
    outDir: mode === "hosted" ? "dist-web" : "dist",
    rollupOptions: {
      input: mode === "hosted" ? { hosted: "hosted.html" } : {
        main: "index.html",
        hosted: "hosted.html",
        pet: "pet.html",
      },
    },
  },
}));

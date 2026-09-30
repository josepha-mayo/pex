import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
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
      "/v1": {
        target: "http://127.0.0.1:7420",
        changeOrigin: true,
        ws: true,
        headers: { origin: "http://127.0.0.1:1420" },
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: "index.html",
        pet: "pet.html",
      },
    },
  },
});

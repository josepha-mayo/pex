import { defineConfig } from "vite";

// Isolated owner assets only. No inherited desktop proxy, Origin rewriting,
// Tauri bridge, provider settings, public replay entry or development secrets.
export default defineConfig({
  publicDir: false,
  build: { outDir: "dist-owner", rollupOptions: { input: "owner.html" } },
});

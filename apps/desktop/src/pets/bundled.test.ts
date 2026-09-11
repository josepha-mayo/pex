import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "vite";

test("the exact two release pets resolve to stable bundled assets", async () => {
  const vite = await createServer({
    root: process.cwd(), server: { middlewareMode: true, hmr: false, ws: false }, appType: "custom",
  });
  try {
    const { bundledPetSheet, defaultBundledPetSheet } = await vite.ssrLoadModule("/src/pets/bundled.ts");
    const pex = bundledPetSheet("pex");
    const von = bundledPetSheet("von");
    assert.equal(typeof pex, "string");
    assert.equal(typeof von, "string");
    assert.ok(pex.length > 0);
    assert.ok(von.length > 0);
    assert.notEqual(pex, von);
    assert.equal(defaultBundledPetSheet, pex);
    assert.equal(bundledPetSheet("retired-or-unknown"), undefined);
  } finally {
    await vite.close();
  }
});

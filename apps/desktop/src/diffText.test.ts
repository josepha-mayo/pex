import assert from "node:assert/strict";
import test from "node:test";
import { DIFF_MAX_LINES, unifiedDiff } from "./diffText.ts";

test("unifiedDiff marks weakened assertions as del/add pairs", () => {
  const lines = unifiedDiff(
    "import csv\n\ndef test_row():\n    assert parse('a,b') == ['a','b']\n",
    "import csv\n\ndef test_row():\n    assert parse('a,b') == parse('a,b')\n",
  );
  assert.deepEqual(lines, [
    { type: "same", text: "import csv" },
    { type: "same", text: "" },
    { type: "same", text: "def test_row():" },
    { type: "del", text: "    assert parse('a,b') == ['a','b']" },
    { type: "add", text: "    assert parse('a,b') == parse('a,b')" },
  ]);
});

test("unifiedDiff keeps identical files all-same", () => {
  const lines = unifiedDiff("a\nb\n", "a\nb\n");
  assert.ok(lines.every((line) => line.type === "same"));
});

test("unifiedDiff bounds pathological inputs", () => {
  const huge = Array.from({ length: DIFF_MAX_LINES + 50 }, (_, i) => `l${i}`).join("\n");
  const lines = unifiedDiff(huge, "");
  assert.equal(lines.filter((line) => line.type === "del").length, DIFF_MAX_LINES);
});

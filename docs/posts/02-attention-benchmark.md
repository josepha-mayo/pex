# Agents for Humans: Measuring Human Attention as an Agent Benchmark

Status: **DRAFT — not published.** Four-arm PexBench is frozen (`benchmarks/manifest.yaml`, live Codex + this-desktop Cursor rows). Do not invent lift. Do not cite leaked 1/5 vs 4/5.

Lesson from the build: “task success” is the primary metric, but the headline secondary metric is human interventions per successful task. PEX overhead counts. Paired arms share one TASK.md; the isolated supervisor process cannot see hidden evaluator files. Frozen Codex rows show mixed results (a CONTINUE nudge can derail a passing worker; a permission pass can be worker variance with PEX NOOP). That honesty is the product: measure attention, do not market a fake win. A synthetic premature-stop smoke proves the supervisor loop; it is labeled `synthetic_pex` and is forbidden as a Cursor/Codex arm. The runner refuses to write a result without an evaluator `success` field.

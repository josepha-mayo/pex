# Agents for Humans: Measuring Human Attention as an Agent Benchmark

Status: **DRAFT — not published.** No numbers until frozen four-arm jsonl exists.

Lesson from the build: “task success” is the primary metric, but the headline secondary metric is human interventions per successful task. PEX overhead counts. A synthetic premature-stop smoke proves the supervisor loop; it is labeled `synthetic_pex` and is forbidden as a Cursor/Codex arm. The runner refuses to write a result without an evaluator `success` field.

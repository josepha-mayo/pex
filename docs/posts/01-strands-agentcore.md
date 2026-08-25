# Agents for Humans: Building a Cross-Harness Supervisor with Strands and AgentCore

Status: **DRAFT — not published.** Do not post until the live Cursor/Codex path is real.

Lesson from the build: Strands is the semantic supervisor, not the side-effect engine. High-frequency events (stop, pytest, repeated shell) are scored in deterministic Python. The model is asked only when judgment is actually needed. AgentCore Runtime exposes `/invocations` and `/ping`; local policy still allow/deny/ask before any adapter call. That split is the product, not an implementation footnote.

Do not claim AgentCore is deployed until `deploy/agentcore` has been pushed to a verified region.

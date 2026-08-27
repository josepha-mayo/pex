# Agents for Humans: Building a Cross-Harness Supervisor with Strands and AgentCore

Status: **DRAFT — not published.** Live Cursor hooks and isolated Codex App Server inspect exist. AgentCore Runtime is **not deployed** on AWS (`aws sts` has no credentials here). Keep that sentence in the published post.

Lesson from the build: Strands is the semantic supervisor, not the side-effect engine. High-frequency events (stop, pytest, repeated shell) are scored in deterministic Python. The model is asked only when judgment is actually needed. The local image exposes AgentCore-shaped `/invocations` and `/ping`; local policy still allow/deny/ask before any adapter call. That split is the product, not an implementation footnote.

Do not claim AgentCore is deployed until `deploy/agentcore` has been pushed to a verified region and `aws sts get-caller-identity` succeeds.

# Agents for Humans: Designing Safe Autonomous Approvals Across Coding Agents

Status: **DRAFT — not published.**

Lesson from the build: each harness speaks a different permission dialect (Cursor `permission: allow|deny`, Claude `hookSpecificOutput.permissionDecision`, OpenCode `POST /session/:id/permissions/:id`, Codex App Server approvals, Qwen `POST /permission/:requestId`). PEX maps those onto one local policy verdict. Fail-open hooks if the bridge is down; fail-closed for destructive commands when it is up. Cloud cannot mint an allow.

# WIP paired-loop integration — not live inference evidence

Seven authored tests pass on controller/review bytes at 7fec83d9. They exercise the actual full PEX planner/verifier prompt+tool schemas through authored HTTP responses, followed by same-session worker continuation. Worker execution in these tests is a fixture. No benchmark score, effectiveness gain, UI workflow or provider call is claimed.

Live gates remain closed. public_request.py only accepts frozen public smoke-check receipts; hidden acceptance remains uncertain. remote_guard.ts is not yet runtime-qualified. Actual OpenCode runs on trusted controller; only remote MCP tools may execute model commands in E2B. Native local tools and Code Mode must be absent, not merely hidden. No provider keys or graders enter the worker VM.

Current gaps: qualify remote CLI tool dispatch and receipt parsing, bind E2B adapter and controller-owned public evidence collection, activate owned supervisor transport only with exact approval/budget/routing/expiry. Same fixed task and equal declared worker ceilings; supervisor overhead separate. Infrastructure/budget exhaustion is not task failure.

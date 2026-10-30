# Wirepool integration — WIP, new task identity

This adapter binds the separately frozen `wirepool_v1_cancel_safe_resp_client`
package to the staged paired runtime. It does not migrate or reinterpret any
Stockroom/asyncpool score, candidate, grant, or recording. Its admission gate is
closed until a new exact run identity, source manifest, retained accounting,
independent root Grant and actual recording handshake are approved.

The two workers receive identical public files and the same existing model,
phase limits and fresh worker budgets. Supervisor usage is separate overhead.
Only public observations and byte-bound candidate snapshots reach the monitor.
Protected checks run after worker revocation; they are withheld from model
context, not a secret-security boundary in this public repository. No baseline
failure or monitor benefit is guaranteed. Local reference, mutation, fake-wire
and fixture tests are authored software checks, not real inference results.

Public input upload, export, private evaluator upload and grade schemas are
explicitly task-bound. Historical liabilities remain in `wirepool_history.py`;
its operational envelopes retain the entire prior plus the next pair's
conservative admission reserve, not a newly invented user spending limit.
The installed remote runtime is separately checked before candidate execution;
local Python 3.12 reference qualification is not a Python 3.11.6 live result.

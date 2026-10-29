# WIP: source-pinned task contracts

The adapter now derives task identity and protected-check count only from an exact source-pinned manifest registry. The original Stockroom v2 hash and17-check contract remain unchanged. Caller-controlled manifest metadata cannot add or select an unreviewed task. No new task is enabled in this checkpoint.

Qualification: authored adapter, public-request and closed-composition tests only. No model call, sandbox creation, or claim of task-solving improvement. Historical run artifacts remain unchanged.

"""Same-session OpenCode execution inside a caller-owned worker boundary.

This is an execution component, not a benchmark evaluator or isolation boundary.
Both baseline and supervised sessions use one absolute task deadline.
"""

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from benchmarks.async_budget import await_with_budget
from benchmarks.opencode_cli import CliTurn, run_turn

REPAIR_ACTIONS = frozenset({"SEND_NUDGE", "CONTINUE_SESSION", "REQUEST_VERIFICATION"})


@dataclass(frozen=True)
class SessionRun:
    turns: tuple[CliTurn, ...]
    actions: tuple[str, ...]
    outgoing_messages: tuple[str, ...]
    followup_limit_reached: bool


async def run_session(
    *, executable: Path, workspace: Path, model: str, prompt: str,
    environment: dict[str, str], log_directory: Path, deadline: float,
    review: Callable[[tuple[CliTurn, ...]], Awaitable[dict]] | None = None,
    max_followups: int = 2,
) -> SessionRun:
    """Run a baseline or review/resume loop without resetting the task budget.

    The review callback must obtain its decision from the separately isolated
    supervisor. It receives exact completion receipts, not task success claims.
    Log paths must be fresh; the caller retains and tears down the whole worker.
    """
    if type(deadline) not in (float, int) or not math.isfinite(deadline):
        raise ValueError("session deadline must be finite")
    if type(max_followups) is not int or not 0 <= max_followups <= 10:
        raise ValueError("follow-up limit must be an integer between zero and ten")

    def remaining():
        budget = deadline - monotonic()
        if budget <= 0:
            raise TimeoutError("OpenCode session exhausted the shared task deadline")
        return budget

    turns = []
    actions = []
    outgoing = []
    vendor_session = None
    next_prompt = prompt
    limit_reached = False
    while True:
        remaining()
        turn = await run_turn(
            executable=executable, workspace=workspace, model=model, prompt=next_prompt,
            environment=environment, stdout_path=log_directory / f"turn-{len(turns)}.jsonl",
            stderr_path=log_directory / f"turn-{len(turns)}.stderr", deadline=deadline,
            session_id=vendor_session,
        )
        remaining()
        if vendor_session is not None and turn.session_id != vendor_session:
            raise ValueError("OpenCode repair crossed vendor sessions")
        vendor_session = turn.session_id
        turns.append(turn)
        if review is None:
            break
        review_budget = remaining()
        decision = await await_with_budget(lambda: review(tuple(turns)), budget=review_budget)
        remaining()
        if not isinstance(decision, dict) or not isinstance(decision.get("type"), str):
            raise ValueError("OpenCode session review lacks an action type")
        action = decision["type"]
        if action not in REPAIR_ACTIONS | {"NOOP"}:
            raise ValueError("OpenCode session review requests an unsupported action")
        actions.append(action)
        if action == "NOOP":
            break
        payload = decision.get("payload")
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000 or "\x00" in text:
            raise ValueError("OpenCode session repair lacks bounded public text")
        if len(outgoing) >= max_followups:
            limit_reached = True
            break
        next_prompt = text
        outgoing.append(text)
    remaining()
    return SessionRun(tuple(turns), tuple(actions), tuple(outgoing), limit_reached)

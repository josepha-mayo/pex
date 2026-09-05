"""Independent hostile review of the claimed shared-Codex Executor boundary."""

from dataclasses import replace

from test_codex_claimed_executor import case as case
from test_codex_claimed_executor import execute
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


async def test_async_local_authority_callback_cannot_be_silently_accepted(case):
    entered = False

    async def invalid_async_checker():
        nonlocal entered
        entered = True

    case.context = replace(case.context, check_local_authority=invalid_async_checker)
    assert await execute(case) == "codex_dispatch_preparation_refused"
    assert entered is False
    case.sender.assert_not_awaited()
    case.generic_send.assert_not_awaited()

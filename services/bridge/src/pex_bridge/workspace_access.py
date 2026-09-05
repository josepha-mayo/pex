"""Server-owned synchronous read checks for asynchronous model/tool callers."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from pex_protocol.session import HarnessSession

from pex_bridge.workspace_binding import WorkspaceAuthorityError, require_workspace_sample

if TYPE_CHECKING:
    from pathlib import Path

    from pex_bridge.store import Store
    from pex_bridge.workspace_binding import WorkspaceBinding


def workspace_read_check(
    store: Store,
    session: HarnessSession,
    witness: tuple[WorkspaceBinding, Path],
):
    """Capture trusted publication authority, never a request-selected path.

    Tool callbacks are synchronous, including when Strands invokes them on an
    event loop. Validate through a separate Store read connection/loop so they
    cannot deadlock the caller's loop. No transaction is held over a model call.
    The checks remain samples, not filesystem or transport locks.
    """
    frozen = session.model_copy(deep=True)
    expected = (witness[0].model_copy(deep=True), witness[1])

    def validate() -> None:
        current = asyncio.run(store.require_session_workspace_current(frozen))
        if current != expected:
            raise WorkspaceAuthorityError("workspace read authority changed")
        require_workspace_sample(*expected, cwd=frozen.cwd)

    def check() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            validate()
        else:
            # A synchronous callback cannot await its own running loop. The
            # short-lived worker uses only new Store connections and settles
            # before returning; it does not schedule work on the blocked loop.
            with ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="pex-workspace-check"
            ) as pool:
                pool.submit(validate).result()

    return check

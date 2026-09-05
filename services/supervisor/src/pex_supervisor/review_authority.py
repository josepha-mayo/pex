"""Revocable authority for one read-only human review, including fallback calls."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


class ReviewAuthorityUnavailable(RuntimeError):
    """The review ended or its server-owned authority can no longer be checked."""


@dataclass
class _ReviewAuthority:
    check: Callable[[], None]
    active: bool = True


_AUTHORITY: ContextVar[_ReviewAuthority | None] = ContextVar("pex_review_authority", default=None)


@contextmanager
def review_invocation_guard(check: Callable[[], None]) -> Iterator[None]:
    """Copies in surviving threads share revocation; never serialize the callback."""
    authority = _ReviewAuthority(check)
    token = _AUTHORITY.set(authority)
    try:
        yield
    finally:
        authority.active = False
        _AUTHORITY.reset(token)


def require_review_authority() -> None:
    """Check immediately before each new provider attempt, not only the outer call.

    Unscoped internal callers retain their existing contract. This check cannot
    revoke a request already accepted by a provider or atomically lock a directory.
    """
    authority = _AUTHORITY.get()
    if authority is None:
        return
    if not authority.active:
        raise ReviewAuthorityUnavailable("review invocation has ended")
    try:
        authority.check()
    except Exception as exc:
        raise ReviewAuthorityUnavailable("review authority is unavailable") from exc
    if not authority.active:
        raise ReviewAuthorityUnavailable("review ended during authority validation")

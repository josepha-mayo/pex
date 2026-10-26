"""Unwired single-owner browser session core. NOT a deployable web boundary.

No environment, bridge/provider/worker credentials, database, network or app
startup is consulted. A distinct high-entropy owner verifier must be explicitly
provisioned. Sessions are process-local and revoked on restart; only digests are
retained. HTTP routes, UI, TLS/proxy handling and revocation of active sockets
remain unimplemented. Native bearer auth and model-only admission are untouched.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

COOKIE_NAME = "__Host-pex-owner"
CSRF_HEADER = b"x-pex-owner-csrf"
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
_MUTATIONS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RawHeaders = Sequence[tuple[bytes, bytes]]


class OwnerAuthError(ValueError):
    """Fixed, secret-free error for a future HTTP adapter."""

    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _valid_token(value: object) -> bool:
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _canonical_authority(origin: str) -> str:
    """Accept an exact ASCII HTTPS origin, never infer one from request headers."""
    if (
        not isinstance(origin, str)
        or len(origin) > 255
        or not origin.startswith("https://")
        or any(ord(char) < 33 or ord(char) > 126 for char in origin)
        or any(char in origin for char in ("\\", "%", "*"))
    ):
        raise ValueError("owner public_origin must be a canonical HTTPS origin")
    try:
        parsed = urlsplit(origin)
        host = parsed.hostname or ""
        port = parsed.port
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not host
            or host != host.lower()
            or port == 443
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError
        # A DNS name or canonical IPv4 literal is sufficient for this unwired
        # checkpoint. IPv6/public-origin aliases must not be silently normalized.
        labels = host.split(".")
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels):
            raise ValueError
        authority = host if port is None else f"{host}:{port}"
        if origin != f"https://{authority}":
            raise ValueError
    except ValueError:
        raise ValueError("owner public_origin must be a canonical HTTPS origin") from None
    return authority


@dataclass(frozen=True)
class ProvisionedOwnerVerifier:
    """SHA-256 of a separately provisioned 32-byte URL-safe random owner secret.

    This is a high-entropy secret verifier, not a human-password hashing scheme.
    No convenience factory reads or reuses another subsystem's credentials.
    """

    sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.sha256, str) or not _DIGEST.fullmatch(self.sha256):
            raise ValueError("owner verifier must be an explicitly provisioned SHA-256 digest")

    def verifies(self, supplied: object) -> bool:
        return _valid_token(supplied) and secrets.compare_digest(_digest(supplied), self.sha256)


@dataclass(frozen=True)
class WebOwnerConfig:
    enabled: bool = False
    public_origin: str | None = None
    verifier: ProvisionedOwnerVerifier | None = field(default=None, repr=False)
    ttl_seconds: int = 900
    max_sessions: int = 16
    login_window_seconds: int = 60
    max_login_attempts: int = 8

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("owner enabled must be boolean")
        for name, low, high in (
            ("ttl_seconds", 1, 3600),
            ("max_sessions", 1, 64),
            ("login_window_seconds", 1, 3600),
            ("max_login_attempts", 1, 64),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"owner {name} is outside the supported bound")
        if self.public_origin is not None:
            _canonical_authority(self.public_origin)
        if self.verifier is not None and type(self.verifier) is not ProvisionedOwnerVerifier:
            raise ValueError("owner verifier must be explicitly provisioned")

    @property
    def configured(self) -> bool:
        return self.enabled and self.public_origin is not None and self.verifier is not None


@dataclass(frozen=True)
class OwnerPrincipal:
    principal_id: str
    session_digest: str = field(repr=False)
    expires_at: float


@dataclass(frozen=True)
class LoginResult:
    # Only the future Set-Cookie header carries the session token. It must never
    # be serialized into a JSON response, URL, log, or browser storage.
    set_cookie: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_in_seconds: int


@dataclass(frozen=True)
class SessionStatus:
    """Safe explicit status fields; no cookie token and no renewal on reads."""

    principal_id: str
    csrf_token: str = field(repr=False)
    expires_in_seconds: int


@dataclass(frozen=True)
class _Session:
    csrf_digest: str = field(repr=False)
    csrf_seed_digest: str = field(repr=False)
    expires_at: float


class OwnerSessions:
    """Bounded single-process session store; no route or mutation authority.

    A future adapter must retain raw duplicate headers, validate the real TLS
    boundary, and revalidate principals at write admission and socket delivery.
    Constructing this object or authenticating an owner grants no bridge bearer,
    MCP/hook token, provider capability, or qualified model transport.
    """

    def __init__(
        self,
        config: WebOwnerConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        if type(config) is not WebOwnerConfig:
            raise ValueError("owner config must be explicitly constructed")
        self._lock = threading.RLock()
        self._config = config
        self._clock = clock
        self._token_factory = token_factory
        self._sessions: dict[str, _Session] = {}
        self._attempts: deque[float] = deque()
        self._last_now = 0.0

    @property
    def config(self) -> WebOwnerConfig:
        with self._lock:
            return self._config

    def reconfigure(self, config: WebOwnerConfig) -> None:
        """Replace configuration atomically; any actual change revokes sessions."""
        if type(config) is not WebOwnerConfig:
            raise ValueError("owner config must be explicitly constructed")
        with self._lock:
            if config != self._config:
                self._sessions.clear()
                self._attempts.clear()
                self._config = config

    @staticmethod
    def _csrf_value(token: str, seed_digest: str) -> str:
        # The opaque cookie is a server-issued 256-bit secret, not a public
        # session ID. Only an authenticated cookie plus this session's stored
        # random seed digest can recover its CSRF value. This distinct domain
        # must never be reused for authentication or another token purpose.
        message = b"PEX/web-owner/session-csrf/v1\x00" + seed_digest.encode("ascii")
        value = hmac.new(token.encode("ascii"), message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _now(self) -> float:
        try:
            now = self._clock()
            if isinstance(now, bool) or not math.isfinite(now) or now < self._last_now:
                raise ValueError
        except Exception:
            raise OwnerAuthError(503, "owner_clock_unavailable") from None
        self._last_now = now
        self._sessions = {key: row for key, row in self._sessions.items() if now < row.expires_at}
        while self._attempts and self._attempts[0] <= now - self.config.login_window_seconds:
            self._attempts.popleft()
        return now

    def _headers(self, headers: RawHeaders, *, origin_required: bool) -> dict[bytes, list[str]]:
        # Internal helper: every caller holds the same reconfiguration lock
        # through request-boundary validation and the resulting state action.
        if not self.config.configured:
            raise OwnerAuthError(503, "owner_auth_not_configured")
        values: dict[bytes, list[str]] = {}
        size = 0
        if len(headers) > 128:
            raise OwnerAuthError(400, "owner_headers_invalid")
        for name, raw in headers:
            if not isinstance(name, bytes) or not isinstance(raw, bytes):
                raise OwnerAuthError(400, "owner_headers_invalid")
            size += len(name) + len(raw)
            if size > 32768:
                raise OwnerAuthError(400, "owner_headers_invalid")
            try:
                value = raw.decode("ascii")
            except UnicodeDecodeError:
                raise OwnerAuthError(400, "owner_headers_invalid") from None
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise OwnerAuthError(400, "owner_headers_invalid")
            values.setdefault(name.lower(), []).append(value)
        expected = _canonical_authority(self.config.public_origin)
        if values.get(b"host") != [expected]:
            raise OwnerAuthError(400, "owner_host_denied")
        origins = values.get(b"origin", [])
        if (origin_required or origins) and origins != [self.config.public_origin]:
            raise OwnerAuthError(403, "owner_origin_denied")
        # Forwarded headers are never used as substitutes for Host or Origin.
        return values

    @staticmethod
    def _session_token(headers: dict[bytes, list[str]]) -> str:
        cookies = headers.get(b"cookie", [])
        if len(cookies) != 1 or len(cookies[0]) > 8192:
            raise OwnerAuthError(401, "owner_session_required")
        found = []
        for part in cookies[0].split(";"):
            name, separator, value = part.strip().partition("=")
            if not separator:
                raise OwnerAuthError(401, "owner_session_required")
            if name == COOKIE_NAME:
                found.append(value)
        if len(found) != 1 or not _valid_token(found[0]):
            raise OwnerAuthError(401, "owner_session_required")
        return found[0]

    def login(self, headers: RawHeaders, owner_secret: object) -> LoginResult:
        """Future POST login only; exact Host/Origin checked before verification."""
        with self._lock:
            self._headers(headers, origin_required=True)
            now = self._now()
            if len(self._attempts) >= self.config.max_login_attempts:
                raise OwnerAuthError(429, "owner_login_rate_limited")
            self._attempts.append(now)
            if not self.config.verifier.verifies(owner_secret):
                raise OwnerAuthError(401, "owner_login_denied")
            if len(self._sessions) >= self.config.max_sessions:
                raise OwnerAuthError(429, "owner_session_capacity")
            try:
                token, seed = self._token_factory(), self._token_factory()
            except Exception:
                raise OwnerAuthError(503, "owner_entropy_unavailable") from None
            if not _valid_token(token) or not _valid_token(seed) or token == seed:
                raise OwnerAuthError(503, "owner_entropy_unavailable")
            digest = _digest(token)
            if digest in self._sessions:
                raise OwnerAuthError(503, "owner_entropy_unavailable")
            seed_digest = _digest(seed)
            csrf = self._csrf_value(token, seed_digest)
            self._sessions[digest] = _Session(
                _digest(csrf), seed_digest, now + self.config.ttl_seconds
            )
            return LoginResult(
                set_cookie=(
                    f"{COOKIE_NAME}={token}; Path=/; Max-Age={self.config.ttl_seconds}; "
                    "Secure; HttpOnly; SameSite=Strict"
                ),
                csrf_token=csrf,
                expires_in_seconds=self.config.ttl_seconds,
            )

    def authorize(
        self, method: str, headers: RawHeaders, *, websocket: bool = False
    ) -> OwnerPrincipal:
        with self._lock:
            if method not in _METHODS or (websocket and method != "GET"):
                raise OwnerAuthError(405, "owner_method_denied")
            values = self._headers(headers, origin_required=method in _MUTATIONS or websocket)
            token = self._session_token(values)
            self._now()
            digest = _digest(token)
            row = self._sessions.get(digest)
            if row is None:
                raise OwnerAuthError(401, "owner_session_invalid")
            if method in _MUTATIONS:
                supplied = values.get(CSRF_HEADER, [])
                if (
                    len(supplied) != 1
                    or not _valid_token(supplied[0])
                    or not secrets.compare_digest(_digest(supplied[0]), row.csrf_digest)
                ):
                    raise OwnerAuthError(403, "owner_csrf_denied")
            return OwnerPrincipal("web-owner", digest, row.expires_at)

    def session_status(self, headers: RawHeaders) -> SessionStatus:
        """Recover stable CSRF after reload, without renewing or rotating a session."""
        with self._lock:
            principal = self.authorize("GET", headers)
            values = self._headers(headers, origin_required=False)
            token = self._session_token(values)
            now = self._now()
            row = self._sessions.get(principal.session_digest)
            if row is None:
                raise OwnerAuthError(401, "owner_session_invalid")
            return SessionStatus(
                principal_id=principal.principal_id,
                csrf_token=self._csrf_value(token, row.csrf_seed_digest),
                expires_in_seconds=math.ceil(row.expires_at - now),
            )

    def revalidate(self, principal: OwnerPrincipal) -> None:
        """Call again after awaits, before a future write admission/socket send."""
        with self._lock:
            if not self.config.configured:
                raise OwnerAuthError(503, "owner_auth_not_configured")
            self._now()
            row = self._sessions.get(principal.session_digest)
            if (
                principal.principal_id != "web-owner"
                or row is None
                or row.expires_at != principal.expires_at
            ):
                raise OwnerAuthError(401, "owner_session_invalid")

    def logout(self, headers: RawHeaders) -> str:
        with self._lock:
            principal = self.authorize("POST", headers)
            self._sessions.pop(principal.session_digest)
            return f"{COOKIE_NAME}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict"

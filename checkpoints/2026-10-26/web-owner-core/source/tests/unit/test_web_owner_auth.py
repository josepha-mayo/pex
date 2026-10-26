"""Synthetic core tests only. No HTTP routes, application startup or real secrets.

Two next-increment contracts are intentionally specified here before the core
implements them: explicit reconfiguration revokes sessions, and authenticated
reload can recover the same CSRF value without rotating sibling tabs.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from dataclasses import replace

from pex_bridge.web_owner_auth import (
    COOKIE_NAME,
    CSRF_HEADER,
    OwnerAuthError,
    OwnerSessions,
    ProvisionedOwnerVerifier,
    WebOwnerConfig,
)

# Clearly authored test values, not user/provider/bridge credentials.
OWNER_FIXTURE = "O" * 43
OTHER_FIXTURE = "N" * 43
ORIGIN = "https://owner.example.test"
HOST = b"owner.example.test"


def verifier(value: str = OWNER_FIXTURE) -> ProvisionedOwnerVerifier:
    return ProvisionedOwnerVerifier(hashlib.sha256(value.encode("ascii")).hexdigest())


class OwnerSessionCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 100.0
        self.sequence = 0
        self.config = WebOwnerConfig(enabled=True, public_origin=ORIGIN, verifier=verifier())
        self.sessions = self.make_store()

    def token(self) -> str:
        self.sequence += 1
        return f"T{self.sequence:042d}"

    def make_store(self, **changes) -> OwnerSessions:
        return OwnerSessions(
            replace(self.config, **changes), clock=lambda: self.now, token_factory=self.token
        )

    def headers(self, login=None, *, origin=True, csrf=True):
        result = [(b"host", HOST)]
        if origin:
            result.append((b"origin", ORIGIN.encode("ascii")))
        if login:
            result.append((b"cookie", login.set_cookie.split(";", 1)[0].encode("ascii")))
            if csrf:
                result.append((CSRF_HEADER, login.csrf_token.encode("ascii")))
        return result

    def login(self, store=None):
        return (store or self.sessions).login(self.headers(), OWNER_FIXTURE)

    def denied(self, status, code, function, *args, **kwargs):
        with self.assertRaises(OwnerAuthError) as raised:
            function(*args, **kwargs)
        self.assertEqual(raised.exception.status_code, status)
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn(OWNER_FIXTURE, str(raised.exception))
        return raised.exception

    def test_disabled_or_missing_verifier_or_origin_never_logs_in(self):
        configs = [
            WebOwnerConfig(),
            replace(self.config, enabled=False),
            replace(self.config, verifier=None),
            replace(self.config, public_origin=None),
        ]
        for config in configs:
            with self.subTest(config=config):
                self.assertFalse(config.configured)
                store = OwnerSessions(config)
                self.denied(503, "owner_auth_not_configured", store.login, [], OWNER_FIXTURE)

    def test_config_rejects_noncanonical_or_insecure_origins(self):
        values = [
            "http://owner.example.test",
            "https://owner.example.test/",
            "https://owner.example.test:443",
            "https://owner.example.test:0",
            "https://owner.example.test:65536",
            "https://user@owner.example.test",
            "https://owner.example.test?x=1",
            "https://owner.example.test#x",
            "https://*.example.test",
            "https://OWNER.example.test",
            "https://owner.example.test.",
            "https://owner..example.test",
            "https://owner.example.test\\evil",
            "https://owner.example.test\n",
            "https://ownér.example.test",
            "https://owner.example.test%2Fevil",
        ]
        for value in values:
            with self.subTest(origin=value), self.assertRaises(ValueError):
                replace(self.config, public_origin=value)

    def test_config_bounds_reject_booleans_and_unbounded_values(self):
        for key, bad in [
            ("enabled", 1),
            ("ttl_seconds", 0),
            ("ttl_seconds", 3601),
            ("ttl_seconds", True),
            ("max_sessions", 0),
            ("max_sessions", 65),
            ("max_login_attempts", 65),
            ("login_window_seconds", 0),
        ]:
            with self.subTest(key=key, value=bad), self.assertRaises(ValueError):
                replace(self.config, **{key: bad})

    def test_verifier_requires_explicit_digest_not_plaintext_or_ambient_sources(self):
        for bad in [OWNER_FIXTURE, "", "a" * 63, "A" * 64, None]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                ProvisionedOwnerVerifier(bad)
        self.assertNotIn(verifier().sha256, repr(verifier()))
        self.assertNotIn(verifier().sha256, repr(self.config))

    def test_wrong_provider_bridge_or_worker_fixture_cannot_be_owner(self):
        for value in ["P" * 43, "B" * 43, "M" * 43, "H" * 43]:
            self.denied(401, "owner_login_denied", self.sessions.login, self.headers(), value)

    def test_bad_login_input_is_bounded_and_not_echoed(self):
        for value in [None, 17, "", "short", "x" * 16384, OWNER_FIXTURE + "\n"]:
            self.denied(401, "owner_login_denied", self.sessions.login, self.headers(), value)

    def test_login_requires_exact_single_real_origin(self):
        bad = [
            [(b"host", HOST)],
            [(b"host", HOST), (b"origin", b"null")],
            [(b"host", HOST), (b"origin", b"https://foreign.example.test")],
            self.headers() + [(b"Origin", ORIGIN.encode())],
            [(b"host", HOST), (b"origin", ORIGIN.encode() + b" ")],
        ]
        for headers in bad:
            with self.subTest(headers=headers):
                self.denied(403, "owner_origin_denied", self.sessions.login, headers, OWNER_FIXTURE)
        self.assertEqual(self.sessions._sessions, {})

    def test_duplicate_missing_foreign_host_or_forwarded_substitute_denied(self):
        origin = (b"origin", ORIGIN.encode())
        bad = [
            [origin],
            [origin, (b"host", b"foreign.example.test")],
            self.headers() + [(b"Host", HOST)],
            [origin, (b"host", b"foreign.example.test"), (b"x-forwarded-host", HOST)],
            [origin, (b"forwarded", b"host=owner.example.test;proto=https")],
            [origin, (b"host", HOST + b":443")],
        ]
        for headers in bad:
            with self.subTest(headers=headers):
                self.denied(400, "owner_host_denied", self.sessions.login, headers, OWNER_FIXTURE)

    def test_header_encoding_controls_and_size_are_bounded(self):
        for headers in [
            self.headers() + [(b"x", b"\xff")],
            self.headers() + [(b"x", b"bad\r\nvalue")],
            self.headers() + [(b"x", b"x" * 32768)],
            self.headers() + [(b"x", b"x")] * 128,
        ]:
            with self.subTest(count=len(headers)):
                self.denied(
                    400, "owner_headers_invalid", self.sessions.login, headers, OWNER_FIXTURE
                )

    def test_cookie_is_host_only_secure_httponly_and_bounded(self):
        result = self.login()
        self.assertTrue(result.set_cookie.startswith(f"{COOKIE_NAME}="))
        for attribute in ["Path=/", "Secure", "HttpOnly", "SameSite=Strict", "Max-Age=900"]:
            self.assertIn(attribute, result.set_cookie)
        self.assertNotIn("Domain=", result.set_cookie)
        self.assertEqual(result.expires_in_seconds, 900)
        self.assertNotIn(result.csrf_token, repr(result))
        self.assertNotIn(result.set_cookie, repr(result))

    def test_store_retains_digests_not_plaintext_owner_session_or_csrf(self):
        result = self.login()
        token = result.set_cookie.split(";", 1)[0].split("=", 1)[1]
        stored = repr(self.sessions._sessions) + repr(self.config)
        for secret in [OWNER_FIXTURE, token, result.csrf_token]:
            self.assertNotIn(secret, stored)
        row = next(iter(self.sessions._sessions.values()))
        self.assertEqual(row.csrf_digest, hashlib.sha256(result.csrf_token.encode()).hexdigest())

    def test_authenticated_read_can_omit_origin_but_not_supply_foreign_origin(self):
        result = self.login()
        principal = self.sessions.authorize("GET", self.headers(result, origin=False, csrf=False))
        self.assertEqual(principal.principal_id, "web-owner")
        bad = self.headers(result, origin=False) + [(b"origin", b"https://foreign.example.test")]
        self.denied(403, "owner_origin_denied", self.sessions.authorize, "GET", bad)

    def test_no_owner_cookie_never_uses_authorization_header(self):
        headers = self.headers() + [(b"authorization", b"Bearer " + OWNER_FIXTURE.encode())]
        self.denied(401, "owner_session_required", self.sessions.authorize, "GET", headers)

    def test_duplicate_cookie_headers_and_duplicate_session_cookie_denied(self):
        result = self.login()
        cookie = result.set_cookie.split(";", 1)[0].encode()
        for headers in [
            self.headers(result) + [(b"cookie", cookie)],
            self.headers() + [(b"cookie", cookie + b"; " + cookie)],
        ]:
            self.denied(401, "owner_session_required", self.sessions.authorize, "GET", headers)

    def test_malformed_unknown_or_oversized_cookie_denied(self):
        for value, code in [
            (f"{COOKIE_NAME}=short", "owner_session_required"),
            (f"{COOKIE_NAME}={'Z' * 43}", "owner_session_invalid"),
            ("malformed", "owner_session_required"),
            ("x=" + "a" * 8192, "owner_session_required"),
        ]:
            self.denied(
                401,
                code,
                self.sessions.authorize,
                "GET",
                self.headers() + [(b"cookie", value.encode())],
            )

    def test_all_mutating_methods_require_origin_and_bound_csrf(self):
        result = self.login()
        for method in ["POST", "PUT", "PATCH", "DELETE"]:
            with self.subTest(method=method):
                self.denied(
                    403,
                    "owner_origin_denied",
                    self.sessions.authorize,
                    method,
                    self.headers(result, origin=False),
                )
                self.denied(
                    403,
                    "owner_csrf_denied",
                    self.sessions.authorize,
                    method,
                    self.headers(result, csrf=False),
                )
                self.assertEqual(
                    self.sessions.authorize(method, self.headers(result)).principal_id, "web-owner"
                )

    def test_csrf_is_session_bound_and_duplicate_headers_fail(self):
        first, second = self.login(), self.login()
        wrong = self.headers(first, csrf=False) + [(CSRF_HEADER, second.csrf_token.encode())]
        self.denied(403, "owner_csrf_denied", self.sessions.authorize, "POST", wrong)
        duplicate = self.headers(first) + [(CSRF_HEADER.upper(), first.csrf_token.encode())]
        self.denied(403, "owner_csrf_denied", self.sessions.authorize, "POST", duplicate)

    def test_expiry_is_exact_and_revalidation_fails(self):
        result = self.login()
        principal = self.sessions.authorize("GET", self.headers(result))
        self.now += self.config.ttl_seconds - 0.01
        self.sessions.revalidate(principal)
        self.now += 0.01
        self.denied(401, "owner_session_invalid", self.sessions.revalidate, principal)
        self.denied(
            401, "owner_session_invalid", self.sessions.authorize, "GET", self.headers(result)
        )

    def test_logout_revokes_session_and_old_principal_without_renewal(self):
        result = self.login()
        principal = self.sessions.authorize("GET", self.headers(result))
        deletion = self.sessions.logout(self.headers(result))
        self.assertIn("Max-Age=0", deletion)
        self.assertIn("HttpOnly", deletion)
        self.denied(401, "owner_session_invalid", self.sessions.revalidate, principal)
        self.denied(
            401, "owner_session_invalid", self.sessions.authorize, "POST", self.headers(result)
        )

    def test_logout_requires_csrf_and_does_not_revoke_on_rejected_request(self):
        result = self.login()
        self.denied(
            403, "owner_csrf_denied", self.sessions.logout, self.headers(result, csrf=False)
        )
        self.sessions.authorize("GET", self.headers(result))

    def test_websocket_requires_exact_origin_and_revalidation_after_logout(self):
        result = self.login()
        self.denied(
            403,
            "owner_origin_denied",
            self.sessions.authorize,
            "GET",
            self.headers(result, origin=False),
            websocket=True,
        )
        principal = self.sessions.authorize("GET", self.headers(result), websocket=True)
        self.sessions.logout(self.headers(result))
        self.denied(401, "owner_session_invalid", self.sessions.revalidate, principal)

    def test_session_capacity_is_bounded_and_expired_entries_are_pruned(self):
        store = self.make_store(max_sessions=1, ttl_seconds=2)
        self.login(store)
        self.denied(429, "owner_session_capacity", self.login, store)
        self.now += 2
        self.login(store)
        self.assertEqual(len(store._sessions), 1)

    def test_login_attempts_are_bounded_and_clock_window_releases_them(self):
        store = self.make_store(max_login_attempts=2, login_window_seconds=5)
        for _ in range(2):
            self.denied(401, "owner_login_denied", store.login, self.headers(), OTHER_FIXTURE)
        self.denied(429, "owner_login_rate_limited", self.login, store)
        self.now += 5
        self.login(store)

    def test_clock_rewind_or_nonfinite_clock_fails_closed(self):
        result = self.login()
        for bad in [99, float("nan"), float("inf"), True]:
            self.now = bad
            self.denied(
                503, "owner_clock_unavailable", self.sessions.authorize, "GET", self.headers(result)
            )

    def test_restart_does_not_restore_process_local_sessions(self):
        result = self.login()
        fresh = self.make_store()
        self.denied(401, "owner_session_invalid", fresh.authorize, "GET", self.headers(result))

    def test_entropy_failure_or_duplicate_token_cannot_overwrite_session(self):
        store = OwnerSessions(self.config, clock=lambda: self.now, token_factory=lambda: "A" * 43)
        self.denied(503, "owner_entropy_unavailable", self.login, store)
        self.assertEqual(store._sessions, {})
        result = self.login()
        first_token = result.set_cookie.split(";", 1)[0].split("=", 1)[1]
        values = iter([first_token, "V" * 43])
        self.sessions._token_factory = lambda: next(values)
        self.denied(503, "owner_entropy_unavailable", self.login)
        self.sessions.authorize("POST", self.headers(result))

    def test_methods_outside_explicit_core_contract_are_denied(self):
        result = self.login()
        for method in ["TRACE", "CONNECT", "OPTIONS", "post"]:
            self.denied(
                405, "owner_method_denied", self.sessions.authorize, method, self.headers(result)
            )

    def test_origin_reconfiguration_revokes_all_old_principals(self):
        result = self.login()
        principal = self.sessions.authorize("GET", self.headers(result))
        self.sessions.reconfigure(replace(self.config, public_origin="https://next.example.test"))
        self.denied(401, "owner_session_invalid", self.sessions.revalidate, principal)
        new_headers = [
            (b"host", b"next.example.test"),
            (b"cookie", result.set_cookie.split(";", 1)[0].encode()),
        ]
        self.denied(401, "owner_session_invalid", self.sessions.authorize, "GET", new_headers)

    def test_verifier_reconfiguration_revokes_cookie_and_accepts_only_new_verifier(self):
        result = self.login()
        principal = self.sessions.authorize("GET", self.headers(result))
        self.sessions.reconfigure(replace(self.config, verifier=verifier(OTHER_FIXTURE)))
        self.denied(401, "owner_session_invalid", self.sessions.revalidate, principal)
        self.denied(
            401, "owner_session_invalid", self.sessions.authorize, "GET", self.headers(result)
        )
        self.denied(401, "owner_login_denied", self.login)
        self.sessions.login(self.headers(), OTHER_FIXTURE)

    def test_configuration_cannot_be_reassigned_without_revocation(self):
        with self.assertRaises(AttributeError):
            self.sessions.config = replace(self.config, verifier=verifier(OTHER_FIXTURE))

    def test_reload_recovers_same_csrf_without_exposing_owner_or_session_secret(self):
        result = self.login()
        status = self.sessions.session_status(self.headers(result, origin=False, csrf=False))
        self.assertEqual(status.csrf_token, result.csrf_token)
        self.assertEqual(status.principal_id, "web-owner")
        self.assertEqual(status.expires_in_seconds, 900)
        self.assertFalse(hasattr(status, "set_cookie"))
        self.assertFalse(hasattr(status, "session_token"))
        self.assertNotIn(OWNER_FIXTURE, repr(status))

    def test_status_read_does_not_invalidate_other_tab_csrf_or_extend_session(self):
        result = self.login()
        principal = self.sessions.authorize("GET", self.headers(result))
        self.now += 11
        status = self.sessions.session_status(self.headers(result, csrf=False))
        self.assertEqual(status.csrf_token, result.csrf_token)
        self.assertEqual(status.expires_in_seconds, 889)
        self.assertEqual(self.sessions.authorize("POST", self.headers(result)), principal)

    def test_status_cannot_recover_csrf_after_logout(self):
        result = self.login()
        self.sessions.logout(self.headers(result))
        self.denied(
            401,
            "owner_session_invalid",
            self.sessions.session_status,
            self.headers(result, csrf=False),
        )


if __name__ == "__main__":
    attempts = []

    def deny_network(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"}:
            attempts.append(event)
            raise AssertionError("synthetic owner-core test attempted network I/O")

    sys.addaudithook(deny_network)
    outcome = unittest.main(exit=False, verbosity=2).result
    print("NETWORK_AUDIT=" + json.dumps({"attempts": len(attempts), "events": attempts}))
    raise SystemExit(0 if outcome.wasSuccessful() and not attempts else 1)

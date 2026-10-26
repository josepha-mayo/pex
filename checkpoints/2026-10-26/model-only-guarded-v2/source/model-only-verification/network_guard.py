"""Run selected synthetic tests with a process-wide Python socket audit sentry.

This is local test evidence, not application transport control. The focused
model-only fixtures additionally catch/count attempts before socket audit events.
"""

import json
import sys

import pytest

attempts = []


def deny_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"}:
        attempts.append(event)
        raise AssertionError("synthetic verification attempted network I/O")


sys.addaudithook(deny_network)
result = pytest.main(sys.argv[1:])
print("NETWORK_AUDIT=" + json.dumps({"attempts": len(attempts), "events": attempts}))
raise SystemExit(1 if attempts else result)

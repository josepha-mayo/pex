import json
import os
import sys

import pytest

attempts = []


def deny(event, args):
    if event in {"socket.getaddrinfo", "socket.connect", "socket.sendto", "socket.sendmsg"}:
        # Only hostnames and pytest identifiers, never credentials or request payloads.
        target = str(args[0]) if event == "socket.getaddrinfo" else "<socket>"
        attempts.append(
            {
                "event": event,
                "target": target,
                "port": args[1] if event == "socket.getaddrinfo" else None,
                "test": os.environ.get("PYTEST_CURRENT_TEST", "collection"),
            }
        )
        raise AssertionError("blocked synthetic-test network attempt")


sys.addaudithook(deny)
rc = pytest.main(sys.argv[1:])
print("AUDIT_DETAIL=" + json.dumps(attempts))
raise SystemExit(rc)

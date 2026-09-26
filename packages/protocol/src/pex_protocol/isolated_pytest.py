"""Public command contract for offline Linux pytest evidence."""

import re
import subprocess

EXECUTOR = "linux-bwrap-public-pytest-v1"


def isolated_pytest_argv(python: str, tests: list[str]) -> list[str]:
    if not tests or len(tests) > 256 or any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.py", name) is None or ".." in name
        for name in tests
    ):
        raise ValueError("public test filenames must be plain workspace basenames")
    return [python, "-I", "-B", "-X", "pycache_prefix=/tmp/pycache", "-m", "pytest",
            "-q", "--tb=line", "-p", "no:cacheprovider", "--rootdir", "/workspace",
            "--confcutdir", "/workspace", "-c", "/dev/null", "-o", "testpaths=",
            "-o", "addopts=", *tests]


def isolated_pytest_display(python: str, tests: list[str]) -> str:
    isolated_pytest_argv(python, tests)
    # The scope classifier consumes this projection; exact isolation/options
    # remain mandatory in the executed_argv provenance, never inferred from it.
    return subprocess.list2cmdline([
        python, "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider",
        "--confcutdir=/workspace", "-o=testpaths=", "-o=addopts=", *tests,
    ])

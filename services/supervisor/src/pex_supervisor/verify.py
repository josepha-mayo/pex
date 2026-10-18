"""Check extracted worker claims against observed events and workspace state.

A STOP with no contradicting evidence stays uncertain. Uncertain is silence.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

from pex_protocol.enums import EventType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from pex_protocol.verification import (
    PytestInvocation,
    PytestInvocationScope,
    UnittestInvocation,
    UnittestInvocationScope,
    VerificationProbeKind,
    classify_pytest_invocation,
    classify_unittest_invocation,
)

from pex_supervisor.workspace import (
    _ACCEPTANCE_DIR_NAMES,
    _ACCEPTANCE_FILE_NAMES,
    HIDDEN_DIR_NAMES,
    HIDDEN_FILE_NAMES,
    acceptance_fingerprints,
    artifact_row_count,
    is_acceptance_config,
    is_acceptance_surface,
)

FILE_TOKEN = re.compile(
    r"^(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]{1,240}\.[A-Za-z0-9]{1,12}$"
)
FILE_CONTAINS = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)[A-Za-z0-9._/-]{1,240}\.[A-Za-z0-9]{1,12})"
    r"\s+(?:contains?|containing)\s+(?P<expected>.+?)(?:[.;]|$)",
    re.I,
)
FILE_EXACT_CONTENT = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)[A-Za-z0-9._/-]{1,240}\.[A-Za-z0-9]{1,12})"
    r"\s+(?:contains?|containing)\s+exactly\s+(?:the\s+word\s+)?"
    r"(?P<literal>`[^`\r\n]*`|\"[^\"\r\n]*\"|'[^'\r\n]*'|[A-Za-z0-9_/-]+)"
    r"(?P<newline>\s+followed\s+by\s+(?:one|a single|a|1)\s+"
    r"(?:newline|LF\s+newline(?:\s+\(U\+000A\))?(?:,\s+no\s+CR)?))?[.;]?",
    re.I,
)
FILE_ROWS = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9._/-]{1,240}\.(?:jsonl?|csv))\s+"
    r"(?:has|contains?)\s+(?P<count>\d+)\s+rows\b",
    re.I,
)
FILE_EXISTS = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9._/-]{1,240}\.[A-Za-z0-9]{1,12})"
    r"\s+(?:exists|is present|is required|must exist)\b",
    re.I,
)
ROW_RE = re.compile(r"(\d+)\s+(?:[A-Za-z]+\s+)*rows", re.I)
FAILED_NODE = re.compile(r"FAILED\s+(\S+)")
_COMPLETION_KINDS = {"tests_pass", "evaluation_complete", "deployment_complete", "complete"}
_SPECIFIC_COMPLETION_KINDS = {"tests_pass", "evaluation_complete", "deployment_complete"}
_GENERIC_DONE = re.compile(
    r"\bi(?:['’]m| am) done\b|\bwe(?:['’]re| are) done\b|\ball done\b",
    re.I,
)
MAX_EXPECTED_ROWS = 1_000_000_000
MAX_EXPECTED_TESTS = 1_000_000_000
_ASCII_CASE_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _windows_workspace(workspace: dict[str, Any]) -> bool:
    root = str(workspace.get("workspace") or "")
    return re.match(r"^[A-Za-z]:[/\\]", root) is not None or root.startswith("\\\\")


def _workspace_path_key(path: str, workspace: dict[str, Any]) -> str:
    if _windows_workspace(workspace):
        return path.replace("\\", "/").translate(_ASCII_CASE_FOLD)
    # POSIX and unclassified roots retain exact filename spelling. A literal
    # POSIX backslash is not a directory separator.
    return path


def _native_workspace_root(workspace: dict[str, Any]) -> Path | None:
    raw = str(workspace.get("workspace") or "")
    if not raw or _windows_workspace(workspace) != (os.name == "nt"):
        return None
    root = Path(raw)
    return root.resolve() if root.is_absolute() else None


_PYTEST_REQUIREMENT = re.compile(
    r"\b(?:pytest|test\s+suite|tests?\s+(?:pass|passing|green|succeed))\b",
    re.I,
)
_UNITTEST_REQUIREMENT = re.compile(r"\b(?:python\s+-m\s+unittest|unittest)\b", re.I)
_UNITTEST_TARGET = re.compile(
    r"\bpython(?:\d+(?:\.\d+)*)?\s+-m\s+unittest\b(?P<args>[^\r\n`]*)",
    re.I,
)
_SERVICE_HEALTH_REQUIREMENT = re.compile(
    r"\b(?:health(?:check)?|readyz|livez|/health)\b",
    re.I,
)
_COMMAND_EXIT_REQUIREMENT = re.compile(
    r"(?P<path>(?![A-Za-z]:)(?!/)(?!.*(?:^|/)\.\.(?:/|$))"
    r"[A-Za-z0-9._/-]{1,240}\.(?:py|sh|ps1|js|mjs))\b",
    re.I,
)
_COUNT_NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,10})"
_VALID_TEST_COUNT = re.compile(
    rf"(?<![0-9,.-])"
    rf"(?:(?P<prefix>exactly|exact|all|at\s+least|minimum(?:\s+of)?|"
    rf"no\s+fewer\s+than|more\s+than|over)\s+)?"
    rf"(?P<count>{_COUNT_NUMBER})"
    rf"(?P<or_more>\s+or\s+more)?\s+"
    rf"(?:(?:pytest\s+)?tests?\s+(?P<metric>pass(?:ed|ing)?|succeed(?:ed|ing)?|green|collected)"
    rf"|(?P<pytest_passed>passed))\b",
    re.I,
)
_LOOSE_TEST_COUNT = re.compile(
    r"(?<![0-9A-Za-z])(?P<count>[0-9][0-9,.-]{0,24})\s+(?:or\s+more\s+)?"
    r"(?:(?:pytest\s+)?tests?\s+(?:pass(?:ed|ing)?|succeed(?:ed|ing)?|green|collected)"
    r"|passed)\b",
    re.I,
)
_AMBIGUOUS_TEST_COUNT_CONTEXT = re.compile(
    r"\b(?:at\s+most|up\s+to|no\s+more\s+than|less\s+than|under|about|around|"
    r"approximately|roughly|between|from|previously|formerly|used\s+to|"
    r"do\s+not|don't|not\s+require)\b|(?:<=|<)\s*$|[0-9]\s*[-–—]\s*$",
    re.I,
)


@dataclass(frozen=True)
class _TestCountConstraint:
    metric: str
    comparator: str
    count: int


@dataclass(frozen=True)
class _TestCountRequirement:
    status: str
    constraints: tuple[_TestCountConstraint, ...] = ()


def _visible_goal_path(path: str) -> bool:
    normalized = path.replace("\\", "/").casefold()
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[a-z]:", normalized)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        return False
    # Oracle file names are root-only: tests/evaluator.py is ordinary surface
    # while a root evaluator.py stays sealed. Component-exact matching also
    # keeps tests/test_evaluator.py visible (its basename merely contains the
    # sealed name as a substring).
    if len(parts) == 1 and parts[-1] in HIDDEN_FILE_NAMES:
        return False
    return not any(part in HIDDEN_DIR_NAMES for part in parts)


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value}")
    return parsed


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _pytest_info(event: HarnessEvent) -> tuple[dict[str, Any], PytestInvocation] | None:
    scoped_command = event.metadata.get("opencode_scoped_test_command")
    invocation = classify_pytest_invocation(
        scoped_command if isinstance(scoped_command, str) else event.command
    )
    if invocation is None:
        return None
    state = event.process_state if isinstance(event.process_state, dict) else {}
    info = state.get("pytest") if isinstance(state.get("pytest"), dict) else None
    payload = dict(info or {})
    # The pipeline sanitizer (a stopgap owned by another agent) strips the
    # terminal verdict from cwd-unverified runs but keeps this marker. Surface
    # it here so support is withheld natively whether or not the strip ran:
    # an unobserved OpenCode cwd never proved which directory ran the suite.
    if isinstance(info, dict) and info.get("cwd_unverified") is True:
        payload["cwd_unverified"] = True
    if event.error and "error" not in payload:
        payload["error"] = event.error
    if "ok" not in payload and event.error:
        payload["ok"] = False
    return payload, invocation


def _latest_pytest(
    events: list[HarnessEvent],
) -> tuple[HarnessEvent, dict[str, Any], int, PytestInvocation] | None:
    found: tuple[HarnessEvent, dict[str, Any], int, PytestInvocation] | None = None
    for index, event in enumerate(events):
        evidence = _pytest_info(event)
        if evidence is None:
            continue
        info, invocation = evidence
        found = (event, info, index, invocation)
    return found


def _unittest_info(event: HarnessEvent) -> tuple[dict[str, Any], UnittestInvocation] | None:
    scoped_command = event.metadata.get("opencode_scoped_test_command")
    invocation = classify_unittest_invocation(
        scoped_command if isinstance(scoped_command, str) else event.command
    )
    if invocation is None:
        return None
    state = event.process_state if isinstance(event.process_state, dict) else {}
    info = state.get("unittest") if isinstance(state.get("unittest"), dict) else None
    payload = dict(info or {})
    # Same native cwd-unverified handling as `_pytest_info`: the marker is
    # kept for audit by the pipeline stopgap, and support is withheld here
    # whether or not that strip ran.
    if isinstance(info, dict) and info.get("cwd_unverified") is True:
        payload["cwd_unverified"] = True
    if event.error and "error" not in payload:
        payload["error"] = event.error
    if "ok" not in payload and event.error:
        payload["ok"] = False
    return payload, invocation


def _latest_unittest(
    events: list[HarnessEvent],
) -> tuple[HarnessEvent, dict[str, Any], int, UnittestInvocation] | None:
    found: tuple[HarnessEvent, dict[str, Any], int, UnittestInvocation] | None = None
    for index, event in enumerate(events):
        evidence = _unittest_info(event)
        if evidence is not None:
            found = (event, evidence[0], index, evidence[1])
    return found


def _goal_unittest_targets(goal: Goal | None) -> tuple[str, ...]:
    """Extract only explicit project-relative .py targets from unittest requirements."""

    targets: list[str] = []
    if goal is None:
        return ()
    for raw in [goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements]:
        for match in _UNITTEST_TARGET.finditer(str(raw or "")):
            for token in match.group("args").split():
                cleaned = token.strip("'\"(),:").replace("\\", "/")
                if cleaned.endswith(".py") and _visible_goal_path(cleaned):
                    targets.append(cleaned)
    return tuple(dict.fromkeys(targets))


def _unittest_supports_goal(
    info: dict[str, Any],
    invocation: UnittestInvocation,
    *,
    edits: list[str],
    goal: Goal | None,
    workspace: dict[str, Any] | None = None,
) -> bool:
    exit_code = info.get("exit_code")
    if (
        info.get("ok") is not True
        or not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code != 0
        or edits
        or info.get("cwd_unverified") is True
        or _module_shadow_evidence(invocation.argv, workspace)
        or _entry_point_evidence(invocation.argv, workspace)
    ):
        return False
    required_targets = _goal_unittest_targets(goal)
    if required_targets:
        return (
            invocation.scope == UnittestInvocationScope.TARGETED
            and not invocation.selection_flags
            and invocation.relative_targets == required_targets
        )
    return invocation.scope == UnittestInvocationScope.FULL_SUITE


def _failed_node(info: dict[str, Any], event: HarnessEvent) -> str | None:
    for key in ("failed", "nodeid", "failed_tests"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return str(value[0])
    blob = " ".join(
        str(part) for part in (info.get("output"), info.get("stdout"), event.error) if part
    )
    match = FAILED_NODE.search(blob)
    return match.group(1) if match else None


# A shell command can mutate the workspace without emitting a FILE_EDIT event
# — sed -i, git checkout, redirection, inline scripts, package installs that
# autoload pytest plugins, or pipe-to-shell. This fail-closed denylist treats
# such commands as edit-equivalent: a green run followed by one can no longer
# earn a supported verdict on its own narration. It errs toward flagging
# dual-use commands (curl -o writes; git stash reverts) because the cost of a
# false negative here is a fabricated verification.
_WRITE_CAPABLE_SHELL = re.compile(
    # `2>file` / `2>>file` redirect test output into a file (a workspace
    # write); a bare `2>&1` / `2>&-` merely duplicates the stderr fd onto
    # stdout and writes nothing by itself. The `(?!&)` guard keeps the
    # former flagged while letting fd-duplication-only commands through.
    r"(?<![0-9&|>])>{1,2}(?![0-9&|])"
    r"|[0-9]+\s*>>?\s*(?!&)\S"
    r"|&\s*>\s*\S"
    r"|<<-?"
    r"|\bsed\b[^\n]*?\s-i\b"
    r"|\bgit\b[^\n]*?\b(?:add|am|apply|checkout|cherry-pick|clean|commit|merge|mv|"
    r"rebase|reset|restore|revert|rm|stash|switch|update-index|update-ref)\b"
    r"|\bapply_patch\b"
    r"|\b(?:cp|mv|rm|rmdir|tee|dd|patch|truncate|install|rsync|ln|touch|unlink|shred|"
    r"mkdir)\b"
    # `md` is the cmd/PowerShell alias for `mkdir`. The `(?<!\.)` guard keeps
    # a `.md` file extension (e.g. `cat README.md`) from matching as a
    # directory-creation command.
    r"|(?<!\.)\bmd\b"
    r"|\b(?:python|python3|py|pypy)(?:[\d.]+)?(?:\.exe)?"
    r"(?:\s+-[A-Za-z0-9_=-]+)*\s+-[a-zA-Z]*c\b"
    r"|\b(?:node|deno|bun)(?:\.exe)?\s+-[a-zA-Z]*e\b"
    r"|\b(?:node|deno|bun)(?:\.exe)?\b[^\n]*?\s--eval\b"
    r"|\b(?:node|deno|bun)(?:\.exe)?\b[^\n]*?\s-p\b"
    # `node --print` is the long form of `node -p` (evaluate and print).
    r"|\b(?:node|deno|bun)(?:\.exe)?\b[^\n]*?\s--print\b"
    r"|\bperl(?:\.exe)?\s+-[a-zA-Z]*[epi]\b"
    r"|\bwget\b"
    r"|\b(?:curl|iwr|invoke-webrequest)\b[^\n]*?(?:\s-[oOTFd]\b|--output\b|--outfile\b|"
    r"-OutFile\b|--upload-file\b|--data\b|--json\b|-X\s*(?:POST|PUT|PATCH|DELETE)\b)"
    r"|\b(?:powershell|pwsh)(?:\.exe)?\b[^\n]*?-EncodedCommand\b"
    r"|\b(?:certutil|bitsadmin)\b"
    r"|\b(?:unzip|expand-archive|tar|7z|ar|make|just|ninja|meson|cmake)\b"
    r"|\b(?:pip|pip3|npm|yarn|pnpm|uv|poetry|pipenv)\b[^\n]*?\b(?:install|add|remove|"
    r"uninstall|sync|ci)\b"
    r"|\b(?:docker|podman)\b[^\n]*?\b(?:run|cp|exec|build|compose)\b"
    # Windows/PowerShell file ops: same write surface as cp/mv/rm, different
    # vocabulary. A `.py`/`.sh` file *invoked* (not `-c` evaled) can also
    # write — the source is already on disk either way.
    r"|\b(?:del|erase|rd|ren|rename|move|copy|xcopy|robocopy|replace)\b"
    r"(?:\.exe)?\s+\S"
    r"|\b(?:python|python3|py|pypy)(?:[\d.]+)?(?:\.exe)?\s+[^\n]*?\.py\b"
    r"|\b(?:ba|z|fi|da|c)?sh(?:\.exe)?\s+[^\n]*?\.sh\b"
    r"|\b(?:move|copy|rename|remove|set|new|out|add|clear|start)-(?:item|content|file)\b"
    r"|\b(?:set|add|out|copy|move|remove|rename|new|clear)-(?:content|file|item)\b"
    r"|\bClear-Content\b"
    r"|\bStart-Transcript\b"
    r"|\bmsiexec\b"
    r"|\beval\b"
    r"|\|\s*(?:sudo\s+)?(?:ba|z|fi|da|c)?sh\b"
    r"|\b(?:ba|z|fi|da|c)?sh\s+-c\b"
    r"|\bexec\b",
    re.IGNORECASE,
)


# `python -m pytest` / `python -m unittest` put the command's cwd at
# sys.path[0]: a workspace-root `pytest.py`, `pytest/` package, or
# `sitecustomize.py`/`usercustomize.py` runs instead of (or before) the real
# module. Console-script launches (`pytest`, `uv run pytest`) do not import
# from the workspace root, so the shadow question applies only to `-m` form.
_PYTHON_MODULE_RUNNER = re.compile(r"^(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?$", re.I)
_SHADOWABLE_MODULES = frozenset({"pytest", "unittest"})
_MODULE_SHADOW_HOOKS = frozenset({"sitecustomize.py", "usercustomize.py"})


def _module_invocation_modules(argv: Sequence[str]) -> tuple[str, ...]:
    found: list[str] = []
    for index in range(len(argv) - 2):
        name = str(argv[index]).replace("\\", "/").rsplit("/", 1)[-1]
        if _PYTHON_MODULE_RUNNER.fullmatch(name) and str(argv[index + 1]) == "-m":
            found.append(str(argv[index + 2]).casefold())
    return tuple(found)


def _surface_symlink_evidence(workspace: dict[str, Any] | None) -> list[str]:
    """Symlinks shadowing the acceptance surface leave no file trace.

    The inventory never follows a link, so `tests -> /tmp/fake` produces an
    empty modified/deleted delta while the suite that ran is whatever the
    link pointed at. Only links touching surface names flag — stray links
    elsewhere stay invisible but harmless.
    """

    if not isinstance(workspace, dict):
        return []
    links = workspace.get("symlinks")
    if not isinstance(links, list):
        return []
    flags: set[str] = set()
    for link in links:
        rel = str(link).replace("\\", "/")
        parts = [part for part in rel.split("/") if part]
        if not parts:
            continue
        if (
            parts[-1].casefold() in _ACCEPTANCE_DIR_NAMES
            or parts[-1].casefold() in _ACCEPTANCE_FILE_NAMES
            or any(part.casefold() in _ACCEPTANCE_DIR_NAMES for part in parts[:-1])
            or is_acceptance_surface(rel)
        ):
            flags.add(f"acceptance_surface_symlink:{rel}")
    return sorted(flags)


def _module_shadow_evidence(
    argv: Sequence[str],
    workspace: dict[str, Any] | None,
) -> list[str]:
    modules = [item for item in _module_invocation_modules(argv) if item in _SHADOWABLE_MODULES]
    if not modules:
        return []
    files = workspace.get("files") if isinstance(workspace, dict) else None
    if not isinstance(files, list):
        # Without an inventory the cwd-shadow question is unanswerable; a
        # `-m` launch on an unobserved workspace cannot earn supported.
        return ["module_shadow_uncheckable:workspace_unobserved"]
    if workspace.get("files_truncated") is True or workspace.get("inventory_reason"):
        # A truncated inventory may have omitted the very shadow file that
        # would void this `-m` launch; fail closed until a complete scan rules
        # it out.
        return ["module_shadow_uncheckable:inventory_truncated"]
    observed = {str(item).replace("\\", "/").casefold() for item in files if item}
    shadows: list[str] = []
    for module in dict.fromkeys(modules):
        if f"{module}.py" in observed or any(item.startswith(f"{module}/") for item in observed):
            shadows.append(f"module_shadow:{module}")
    for hook in sorted(_MODULE_SHADOW_HOOKS & observed):
        shadows.append(f"module_shadow_hook:{hook}")
    shadows.extend(_external_site_shadow_evidence())
    return shadows


def _external_site_shadow_evidence() -> list[str]:
    """Probe the import hooks `python -m` consults *outside* the workspace.

    `site` imports `sitecustomize`/`usercustomize` from the interpreter's
    site dirs — including the per-user site — before `-m` resolves the
    module. Those files live outside the workspace inventory and baseline.
    Only the hooks are probed: `pytest`/`unittest` inside site-packages is
    the legitimate install location, not a shadow.
    """

    import site
    from pathlib import Path as _Path

    candidates: list[str] = []
    try:
        candidates.append(site.getusersitepackages())
    except Exception:
        pass
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    flags: set[str] = set()
    for directory in dict.fromkeys(candidates):
        if not directory:
            continue
        root = _Path(directory)
        for probe in sorted(_MODULE_SHADOW_HOOKS):
            try:
                if (root / probe).exists():
                    flags.add(f"module_shadow_external:{probe}")
            except OSError:
                continue
    return sorted(flags)


# A workspace virtualenv is pruned from the inventory by design, but an
# activated one still controls which `pytest`/`python` actually runs: PATH
# puts its bin/Scripts first, so a worker can hide a same-named shim inside
# it that prints a passing summary. `uv run` resolves the project env — a
# `.venv` is exactly what it executes — and a venv site-packages can host a
# sitecustomize.py the inventory never sees. When the snapshot reports a
# pruned env dir, a name-resolved launcher cannot prove which binary ran.
_ENV_PRUNE_NAMES = frozenset({".venv", "venv"})
_SHIMMABLE_LAUNCHER = re.compile(
    r"^(?:pytest|py\.test|python(?:\d+(?:\.\d+)*)?|py|pypy(?:\d+(?:\.\d+)*)?"
    r"|uv|poetry|pipenv)(?:\.exe)?$",
    re.IGNORECASE,
)


def _launcher_is_absolute(launcher: str) -> bool:
    return (
        launcher.startswith(("/", "~/", "~\\", "\\\\"))
        or re.match(r"^[a-zA-Z]:[/\\]", launcher) is not None
    )


def _foreign_observation(workspace: dict[str, Any] | None) -> bool:
    """A dict that lists files but is not a supervisor `snapshot()` payload.

    Public-observation workspaces carry `files`/`file_manifest` under their
    own provenance contract (plus `public_test_integrity` et al.) — they are
    a different evidence type, not a degraded snapshot. The launcher/entry
    checks only answer questions a supervisor snapshot was built to answer;
    applying them to a foreign dict is type confusion, not fail-closed.
    `snapshot()` always emits the `workspace` key; its absence on a
    files-bearing dict marks the foreign shape.
    """

    if not isinstance(workspace, dict):
        return False
    # `file_manifest` (path/sha256/size, no mtimes) is the benchmark's own
    # observation contract — a `snapshot()` emits `file_meta`, never this
    # key, so its presence marks foreign provenance even when the caller
    # also set a `workspace` path.
    if "file_manifest" in workspace:
        return True
    return "workspace" not in workspace and "files" in workspace


def _entry_point_evidence(
    argv: Sequence[str],
    workspace: dict[str, Any] | None,
) -> list[str]:
    if not argv or _foreign_observation(workspace):
        return []
    launcher = str(argv[0]).replace("\\", "/")
    name = launcher.rsplit("/", 1)[-1]
    if _SHIMMABLE_LAUNCHER.fullmatch(name) is None:
        return []
    flags: list[str] = []
    lowered_launcher = launcher.casefold()
    if lowered_launcher.startswith("./"):
        lowered_launcher = lowered_launcher[2:]
    workspace = workspace if isinstance(workspace, dict) else {}
    root = str(workspace.get("workspace") or "").replace("\\", "/").rstrip("/").casefold()
    if "/" in launcher:
        if not _launcher_is_absolute(launcher):
            # A relative launcher resolves inside the workspace by
            # definition — `./pytest`, `tools/pytest`, `env/bin/pytest` can
            # all be same-named shims printing a green summary.
            flags.append(f"entry_point_workspace_controlled:{lowered_launcher or name.casefold()}")
        elif root and lowered_launcher.startswith(f"{root}/"):
            flags.append(f"entry_point_workspace_controlled:{lowered_launcher}")
        elif not root:
            # Absolute launch path with no observed root: cannot classify
            # whether it lives inside the workspace.
            flags.append("entry_point_uncheckable:workspace_root_unobserved")
        # Absolute paths outside the observed root are the system-path case
        # and stay unflagged.
    else:
        # A bare-name launch resolves through PATH, which is unobservable —
        # a same-named file at the workspace root is a provable shadow
        # candidate (cwd-first resolution on Windows, '.'-in-PATH shells).
        files = workspace.get("files")
        if isinstance(files, list):
            stem = name.casefold().removesuffix(".exe")
            observed = {
                str(item).replace("\\", "/").casefold() for item in files if isinstance(item, str)
            }
            # Only bare-name-invocable forms: `.py`/`.sh` sources do not
            # answer a bare `pytest` (they matter to `-m` imports instead,
            # which the module-shadow check covers).
            for candidate in (stem, f"{stem}.exe", f"{stem}.bat", f"{stem}.cmd", f"{stem}.com"):
                if candidate in observed:
                    flags.append(f"entry_point_workspace_controlled:{candidate}")
                    break
        else:
            flags.append("entry_point_uncheckable:inventory_unobserved")
    pruned = workspace.get("pruned_directories")
    if not isinstance(pruned, list):
        # Without the prune inventory the env-dir question is unanswerable:
        # a `.venv` could host the real entry point with no trace in files.
        flags.append("entry_point_uncheckable:pruned_inventory_unobserved")
    else:
        for directory in sorted({str(item).casefold() for item in pruned} & _ENV_PRUNE_NAMES):
            if lowered_launcher.startswith(f"{directory}/") or f"/{directory}/" in lowered_launcher:
                flags.append(f"entry_point_inside_pruned_dir:{directory}")
            else:
                flags.append(f"entry_point_workspace_controlled:{directory}")
    return sorted(set(flags))


# Bytecode/test-cache directories whose removal cannot weaken the suite a
# green run just proved. The exemption is deliberately narrow: only a single
# direct removal whose every non-flag target resolves inside one of these
# directory names is excused. Anything composed (`;`, `&&`, `|`, redirects,
# substitutions), any non-cache target, and any non-removal executable
# (including `python -c`, which stays fail-closed) still voids the run.
_CACHE_CLEANUP_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
_REMOVAL_EXECUTABLES = frozenset({"rm", "rmdir", "remove-item", "ri"})
_SHELL_COMPOSITION_CHARS = frozenset({";", "|", ">", "<", "`", "$", "&", "\r", "\n"})


def _is_pure_cache_cleanup(command: str) -> bool:
    """Whether a shell command only removes bytecode/test-cache directories."""
    if not command or len(command) > 4_096:
        return False
    if any(char in command for char in _SHELL_COMPOSITION_CHARS) or "&&" in command:
        return False
    try:
        import shlex as _shlex

        tokens = [
            token.strip("'\"") for token in _shlex.split(command, posix=True) if token.strip("'\"")
        ]
    except ValueError:
        return False
    if not tokens:
        return False
    executable = tokens[0].replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe")
    if executable.casefold() not in _REMOVAL_EXECUTABLES:
        return False
    # Skip option tokens: `-r`/`--recurse` style and cmd-style `/s` (a bare
    # `/name` with no further slash; deeper absolute paths stay targets).
    targets = [
        token
        for token in tokens[1:]
        if token != "--" and not token.startswith("-") and not re.fullmatch(r"/[A-Za-z]+", token)
    ]
    # `Remove-Item a, b` separates targets with commas; a bare flag list
    # with no targets proves nothing about the workspace.
    flattened: list[str] = []
    for target in targets:
        flattened.extend(part for part in (piece.strip() for piece in target.split(",")) if part)
    if not flattened:
        return False
    for target in flattened:
        normalized = target.replace("\\", "/").rstrip("/")
        while normalized.endswith("/*"):
            normalized = normalized[:-2].rstrip("/")
        parts = [part for part in normalized.split("/") if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            return False
        if not any(part.casefold() in _CACHE_CLEANUP_DIR_NAMES for part in parts):
            return False
    return True


def _later_edits(events: list[HarnessEvent], after: int) -> list[str]:
    """Describe subsequent mutations, retaining events whose path was not reported."""
    paths: list[str] = []
    shell_mutation_seen = False
    for event in events[after + 1 :]:
        if event.event_type == EventType.FILE_EDIT:
            # Missing path metadata is not evidence that the workspace stayed
            # unchanged. This descriptive fallback is never used for file I/O.
            paths.extend(event.file_paths or ["a file with an unreported path"])
        elif (
            event.event_type == EventType.SHELL
            and not shell_mutation_seen
            and isinstance(event.command, str)
            and _WRITE_CAPABLE_SHELL.search(event.command)
            and not _is_pure_cache_cleanup(event.command)
        ):
            # The label stays generic: command text can carry secrets and the
            # event ledger already holds the full command for audit.
            paths.append("a shell command that can modify workspace files")
            shell_mutation_seen = True
    return paths


def _post_run_workspace_mutation(
    workspace: dict[str, Any] | None,
    run_epoch: float | None,
) -> list[str]:
    """Flag observed files modified after the green run's event time.

    `_later_edits` only sees harness-emitted writes; shell-side mutation
    leaves no FILE_EDIT event and a command-text denylist cannot enumerate
    every writer (`del`, `xcopy`, `python x.py`, `bash x.sh`, `>|`, quoted
    names). The claim-time snapshot's mtimes are the durable record — a
    file observed newer than the run cannot be part of what the run proved.
    Deletions of non-surface files remain undetectable here (no earlier
    inventory to diff); the acceptance-surface delta covers surface ones.
    An adversary can also backdate `mtime` (`touch -d`, `os.utime`) — that is
    the same no-cryptographic-isolation boundary the threat model states;
    this gate catches the unforged case, which is the common one.
    """
    if not isinstance(workspace, dict) or run_epoch is None or _foreign_observation(workspace):
        return []
    meta = workspace.get("file_meta")
    if not isinstance(meta, list):
        # A files-listing without mtimes is an internally incomplete
        # observation — the post-run-mutation question is unanswerable and
        # must not default to clean. A fully unobserved workspace is the
        # launcher/module gates' problem, not this check's.
        if isinstance(workspace.get("files"), list):
            return ["post_run_mutation_uncheckable:inventory_missing"]
        return []
    flags: list[str] = []
    # Prefer nanosecond precision: a whole-second `mtime` ties a fast
    # adversary's write against the run event's own second and misses a
    # mutation that real telemetry ordered after it. int() keeps the
    # comparison in integer nanoseconds — the float product carries only
    # the input timestamp's own sub-microsecond error.
    run_ns = int(run_epoch * 1_000_000_000)
    for entry in meta:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        mtime_ns = entry.get("mtime_ns")
        if isinstance(path, str) and isinstance(mtime_ns, (int, float)):
            if mtime_ns > run_ns:
                flags.append(f"post_run_mutation:{path}")
            continue
        mtime = entry.get("mtime")
        if isinstance(path, str) and isinstance(mtime, (int, float)) and mtime > run_epoch:
            flags.append(f"post_run_mutation:{path}")
    if workspace.get("files_truncated") is True or workspace.get("inventory_reason"):
        flags.append("post_run_mutation_uncheckable:inventory_truncated")
    return sorted(flags)


def _post_run_edits(
    events: list[HarnessEvent],
    index: int,
    workspace: dict[str, Any] | None,
) -> list[str]:
    """Later-edits list extended with the structural post-run mtime check.

    Mutation flags precede witnessed edits so `edits[-1]` stays the most
    actionable entry (a concrete path or the shell-write description).
    """
    ts = getattr(events[index], "ts", None)
    run_epoch = ts.timestamp() if hasattr(ts, "timestamp") else None
    return [*_post_run_workspace_mutation(workspace, run_epoch), *_later_edits(events, index)]


def _expected_rows(goal: Goal | None) -> int | None:
    if goal is None:
        return None
    blob = " ".join([goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements])
    match = ROW_RE.search(blob)
    return _parse_expected_rows(match.group(1)) if match else None


def _parse_expected_rows(value: str) -> int | None:
    if len(value) > 10:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if 0 <= parsed <= MAX_EXPECTED_ROWS else None


def _test_count_requirement(goal: Goal | None) -> _TestCountRequirement:
    """Parse only bounded, explicit test-count constraints from persistent goal text.

    ``absent`` and ``ambiguous`` are intentionally distinct. An unsupported,
    conflicting, negated, historical, ranged, or malformed count must never be
    interpreted as an unconstrained passing suite.
    """

    if goal is None:
        return _TestCountRequirement("absent")
    parsed: list[_TestCountConstraint] = []
    ambiguous = False
    for raw in [goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements]:
        text = str(raw or "")
        valid_spans: list[tuple[int, int]] = []
        for match in _VALID_TEST_COUNT.finditer(text):
            prefix_context = text[max(0, match.start() - 40) : match.start()]
            if _AMBIGUOUS_TEST_COUNT_CONTEXT.search(prefix_context):
                ambiguous = True
                continue
            number = match.group("count")
            try:
                count = int(number.replace(",", ""))
            except (TypeError, ValueError, OverflowError):  # pragma: no cover - regex invariant
                ambiguous = True
                continue
            if count <= 0 or count > MAX_EXPECTED_TESTS:
                ambiguous = True
                continue
            qualifier = str(match.group("prefix") or "").casefold()
            if match.group("or_more") or qualifier in {
                "at least",
                "minimum",
                "minimum of",
                "no fewer than",
            }:
                comparator = "gte"
            elif qualifier in {"more than", "over"}:
                comparator = "gte"
                count += 1
                if count > MAX_EXPECTED_TESTS:
                    ambiguous = True
                    continue
            else:
                comparator = "eq"
            metric = "passed"
            if str(match.group("metric") or "").casefold() == "collected":
                metric = "collected"
            parsed.append(_TestCountConstraint(metric, comparator, count))
            valid_spans.append(match.span())
        for loose in _LOOSE_TEST_COUNT.finditer(text):
            if not any(start <= loose.start() and loose.end() <= end for start, end in valid_spans):
                ambiguous = True
    if ambiguous:
        return _TestCountRequirement("ambiguous")
    if not parsed:
        return _TestCountRequirement("absent")

    merged: list[_TestCountConstraint] = []
    for metric in ("passed", "collected"):
        relevant = [item for item in parsed if item.metric == metric]
        if not relevant:
            continue
        exact = {item.count for item in relevant if item.comparator == "eq"}
        minimum = max(
            (item.count for item in relevant if item.comparator == "gte"),
            default=None,
        )
        if len(exact) > 1:
            return _TestCountRequirement("ambiguous")
        if exact:
            count = next(iter(exact))
            if minimum is not None and count < minimum:
                return _TestCountRequirement("ambiguous")
            merged.append(_TestCountConstraint(metric, "eq", count))
        elif minimum is not None:
            merged.append(_TestCountConstraint(metric, "gte", minimum))
    return _TestCountRequirement("valid", tuple(merged))


def _expected_test_count(goal: Goal | None) -> int | None:
    """Compatibility helper for one unambiguous exact passing-test count."""

    requirement = _test_count_requirement(goal)
    if requirement.status != "valid" or len(requirement.constraints) != 1:
        return None
    constraint = requirement.constraints[0]
    if constraint.metric != "passed" or constraint.comparator != "eq":
        return None
    return constraint.count


def _observed_pytest_count(info: dict[str, Any]) -> int | None:
    value = info.get("passed")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _observed_pytest_metric(info: dict[str, Any], metric: str) -> int | None:
    key = "passed" if metric == "passed" else "collected"
    value = info.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _pytest_failure_signals(info: dict[str, Any]) -> list[str]:
    """Fail-closed failure evidence: any positive/non-empty failure field blocks support.

    Covers ``failed``/``failed_count``/``failures``/``errors``/``error_count``
    reported as an int count (>0) or a non-empty str/list payload. A green
    exit with ``failed_count=1`` or ``errors=1`` is inconsistent narration and
    must stay uncertain, never supported.
    """

    signals: list[str] = []
    for key in ("failed", "failed_count", "failures", "errors", "error_count"):
        value = info.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            if value > 0:
                signals.append(f"pytest_nonpassing:{key}={value}")
        elif isinstance(value, str):
            if value.strip():
                signals.append(f"pytest_nonpassing:{key}={value.strip()}")
        elif isinstance(value, list):
            if len(value) > 0:
                signals.append(f"pytest_nonpassing:{key}={len(value)}")
    return signals


def _test_count_violations(
    requirement: _TestCountRequirement,
    info: dict[str, Any],
) -> tuple[list[_TestCountConstraint], list[_TestCountConstraint]]:
    missing: list[_TestCountConstraint] = []
    violated: list[_TestCountConstraint] = []
    for constraint in requirement.constraints:
        observed = _observed_pytest_metric(info, constraint.metric)
        if observed is None:
            missing.append(constraint)
        elif constraint.comparator == "eq" and observed != constraint.count:
            violated.append(constraint)
        elif constraint.comparator == "gte" and observed < constraint.count:
            violated.append(constraint)
    return missing, violated


def _pytest_supports_goal(
    info: dict[str, Any],
    invocation: PytestInvocation,
    *,
    edits: list[str],
    goal: Goal | None,
    workspace: dict[str, Any] | None = None,
) -> bool:
    exit_code = info.get("exit_code")
    if (
        info.get("ok") is not True
        or not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code != 0
        or invocation.scope != PytestInvocationScope.FULL_SUITE
        or edits
        # Native cwd-unverified withhold: an unobserved execution directory
        # never proved which suite ran, so it cannot earn support — whether
        # or not the pipeline stopgap already stripped the terminal verdict.
        or info.get("cwd_unverified") is True
        or _module_shadow_evidence(invocation.argv, workspace)
        or _entry_point_evidence(invocation.argv, workspace)
    ):
        return False
    deselected = info.get("deselected")
    if isinstance(deselected, int) and not isinstance(deselected, bool) and deselected > 0:
        return False
    if _pytest_failure_signals(info):
        return False
    passed = _observed_pytest_count(info)
    nonpassing_results = sum(
        value
        for key in ("skipped", "xfailed", "xpassed")
        if isinstance((value := info.get(key)), int) and not isinstance(value, bool) and value > 0
    )
    # Any unexplained nonpassing count — a skip, an xfail, an unexpected pass —
    # is exactly where a weakened suite hides. A claim that "the suite passes"
    # is uncertain, not supported, while the run reports nonpassing results.
    # A parsed zero-pass is inconsistent with exit 0 (zero-collected exits 5).
    if nonpassing_results > 0 or passed == 0:
        return False
    requirement = _test_count_requirement(goal)
    if requirement.status == "ambiguous":
        return False
    missing, violated = _test_count_violations(requirement, info)
    return not missing and not violated


def _count_rows(text: str, path: str) -> int | None:
    stripped = text.strip()
    if not stripped:
        return 0
    if path.endswith(".jsonl"):
        lines = [line for line in stripped.splitlines() if line.strip()]
        try:
            rows = [
                json.loads(
                    line,
                    parse_constant=_reject_nonfinite_json_constant,
                    parse_float=_finite_json_float,
                    object_pairs_hook=_unique_json_object,
                )
                for line in lines
            ]
        except (ValueError, RecursionError):
            return None
        # Row requirements count records; scalar lines are not evaluation
        # rows (mirrors the workspace receipt rule). Unknown, not zero.
        if not all(isinstance(row, dict) for row in rows):
            return None
        return len(rows)
    try:
        data = json.loads(
            stripped,
            parse_constant=_reject_nonfinite_json_constant,
            parse_float=_finite_json_float,
            object_pairs_hook=_unique_json_object,
        )
    except (ValueError, RecursionError):
        # A generic text preview cannot establish whether a CSV header counts
        # as a row; keep the verdict uncertain rather than overclaiming.
        return None
    if isinstance(data, list):
        if not all(isinstance(item, dict) for item in data):
            return None
        return len(data)
    if isinstance(data, dict):
        for key in ("rows", "items", "records", "results", "data"):
            if isinstance(data.get(key), list):
                if not all(isinstance(item, dict) for item in data[key]):
                    return None
                return len(data[key])
    return None


def _artifact_rows(
    goal: Goal | None,
    workspace: dict[str, Any],
    required_path: str | None = None,
) -> tuple[str | None, int | None]:
    required = (
        [required_path]
        if required_path
        else [
            path
            for path in _required_files(goal)
            if path.casefold().endswith((".json", ".jsonl", ".csv"))
        ]
    )
    if not required:
        return None, None
    wanted = str(required[0]).replace("\\", "/")
    if not _visible_goal_path(wanted):
        return wanted, None
    for item in workspace.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        if _workspace_path_key(path, workspace) != _workspace_path_key(wanted, workspace):
            continue
        count = item.get("row_count")
        # bool is an int subclass, but neither booleans nor negative values
        # describe an observed row count. Malformed snapshots stay uncertain.
        if item.get("row_count_complete") is True and type(count) is int and count >= 0:
            return path, count
        # Compatibility with externally supplied complete artifact snapshots.
        if item.get("tail_complete") is True:
            return path, _count_rows(str(item.get("tail") or ""), path)
        return path, None
    # The exact required artifact may be nested and therefore absent from the
    # compact root-artifact preview. Read only that goal-declared path.
    try:
        root = _native_workspace_root(workspace)
        target = (root / wanted).resolve() if root is not None else None
        if root is None or target is None:
            return wanted, None
        target.relative_to(root)
        if not target.is_file():
            return wanted, None
        if target.suffix.casefold() in {".json", ".jsonl"}:
            count, complete = artifact_row_count(target)
            return wanted, count if complete else None
        if target.stat().st_size > 4_000_000:
            return wanted, None
        return wanted, _count_rows(target.read_text(encoding="utf-8"), wanted)
    except (OSError, UnicodeError, ValueError):
        return wanted, None


def _observed_files(workspace: dict[str, Any]) -> set[str] | None:
    if workspace.get("error") or not workspace.get("workspace"):
        return None
    files = workspace.get("files")
    if not isinstance(files, list):
        return None
    return {_workspace_path_key(str(name), workspace) for name in files}


def acceptance_surface_delta(
    baseline: dict[str, Any] | None,
    workspace: dict[str, Any],
) -> dict[str, Any]:
    """Compare the recorded acceptance-surface baseline to the current scan.

    The baseline is the fingerprint map sealed at the first goal-bound
    observation; a worker that weakens the tests before claiming a green run
    shows up as ``modified`` or ``deleted`` here regardless of what the event
    stream reported.
    """

    current = acceptance_fingerprints(workspace)
    surface_files = sorted(current) if current is not None else []
    surface_complete = workspace.get("surface_complete") if isinstance(workspace, dict) else None
    # Explicit False means the scan truncated the acceptance surface itself;
    # True/None means complete or unknown. Legacy workspace dicts without the
    # flag predate surface tracking and are treated as complete (fail-open
    # for that legacy shape only); only an explicit False reports incomplete.
    surface_incomplete = surface_complete is False
    empty: dict[str, Any] = {
        "baselined": False,
        "baseline_complete": False,
        "checked": False,
        "reason": "no_baseline",
        "sealed_at_claim": False,
        "surface_files": surface_files,
        "surface_complete": False if surface_incomplete else True,
        "modified": [],
        "deleted": [],
        "unhashed": [],
        "added": [],
        "added_config": [],
    }
    if isinstance(baseline, dict) and baseline.get("unsealed") is True:
        # The caller observed the surface but could not establish a baseline
        # at all — distinct from "no baseline existed".
        empty["reason"] = "unsealed"
        return empty
    baseline_files = baseline.get("files") if isinstance(baseline, dict) else None
    if not isinstance(baseline_files, dict):
        return empty
    empty["baselined"] = True
    empty["baseline_complete"] = baseline.get("files_complete") is True
    # A baseline first sealed from the claim-time scan proves nothing when a
    # surface exists; one sealed by a verify_claim tool call is claim-adjacent
    # forever, even empty — a worker could bootstrap it then add test files.
    sealed_at_claim = (baseline.get("sealed_now") is True and bool(baseline_files)) or baseline.get(
        "sealed_context"
    ) == "verify"
    empty["sealed_at_claim"] = sealed_at_claim
    if current is None:
        empty["reason"] = "workspace_unobserved"
        return empty
    if surface_incomplete:
        # A truncated surface scan cannot prove the absence of modifications:
        # report the check as incomplete rather than comparing a partial
        # fingerprint map (which would false-positive deletions).
        empty["reason"] = "surface_incomplete"
        return empty
    empty["checked"] = True
    empty["reason"] = None
    current_by_key = {
        _workspace_path_key(path, workspace): (path, digest) for path, digest in current.items()
    }
    modified: list[str] = []
    deleted: list[str] = []
    unhashed: list[str] = []
    for path, digest in baseline_files.items():
        observed = current_by_key.pop(
            _workspace_path_key(str(path), workspace),
            None,
        )
        if observed is None:
            deleted.append(str(path))
        elif not isinstance(digest, str) or observed[1] is None:
            unhashed.append(str(path))
        elif observed[1] != digest:
            modified.append(str(path))
    added = sorted(path for path, _digest in current_by_key.values())
    return {
        "baselined": True,
        "baseline_complete": baseline.get("files_complete") is True,
        "sealed_at_claim": sealed_at_claim,
        "checked": True,
        "reason": None,
        "surface_complete": False if surface_incomplete else True,
        "surface_files": surface_files,
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "unhashed": sorted(unhashed),
        "added": added,
        "added_config": sorted(path for path in added if is_acceptance_config(path)),
    }


def _required_files(goal: Goal | None) -> list[str]:
    if goal is None:
        return []
    names: list[str] = []
    for raw in list(goal.evidence_requirements or []) + list(goal.acceptance_criteria or []):
        name = str(raw or "").strip()
        if FILE_TOKEN.fullmatch(name) and _visible_goal_path(name):
            names.append(name.replace("\\", "/"))
            continue
        row_check = _expected_file_rows(name)
        if row_check is not None:
            names.append(row_check[0])
            continue
        content_check = _expected_content(name)
        if content_check is not None:
            names.append(content_check[0])
            continue
        exists_check = _expected_exists(name)
        if exists_check is not None:
            names.append(exists_check)
    return list(dict.fromkeys(names))


def required_files(goal: Goal | None) -> list[str]:
    return _required_files(goal)


def missing_required_files(goal: Goal | None, workspace: dict[str, Any]) -> list[str] | None:
    return _missing_required_files(goal, workspace)


def _missing_required_files(goal: Goal | None, workspace: dict[str, Any]) -> list[str] | None:
    observed = _observed_files(workspace)
    if observed is None:
        return None
    try:
        root = _native_workspace_root(workspace)
    except (OSError, ValueError):
        root = None
    missing: list[str] = []
    for name in _required_files(goal):
        if _workspace_path_key(name, workspace) in observed:
            continue
        exists = False
        if root is not None:
            try:
                target = (root / name).resolve()
                target.relative_to(root)
                exists = target.is_file()
            except (OSError, ValueError):
                exists = False
        if not exists:
            missing.append(name)
    return missing


def _tests_pass_verdict(
    claim: dict[str, Any],
    events: list[HarnessEvent],
    goal: Goal | None,
    workspace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requirements = _goal_requirement_text(goal)
    if not (
        re.search(r"\bpytest\b", requirements, re.I) and _UNITTEST_REQUIREMENT.search(requirements)
    ):
        return _single_tests_pass_verdict(claim, events, goal, workspace)
    pytest_verdict = _single_tests_pass_verdict(
        claim,
        [event for event in events if _unittest_info(event) is None],
        goal,
        workspace,
    )
    unittest_events = [event for event in events if _pytest_info(event) is None]
    unittest_verdict = (
        _single_tests_pass_verdict(claim, unittest_events, goal, workspace)
        if _latest_unittest(unittest_events) is not None
        else {"status": "uncertain", "evidence": ["no_unittest_observed"], "correction": None}
    )
    verdicts = [pytest_verdict, unittest_verdict]
    status = (
        "contradicted"
        if any(item["status"] == "contradicted" for item in verdicts)
        else "supported"
        if all(item["status"] == "supported" for item in verdicts)
        else "uncertain"
    )
    corrections = [item["correction"] for item in verdicts if item.get("correction")]
    return {
        "claim": claim,
        "status": status,
        "evidence": [value for item in verdicts for value in item["evidence"]],
        "correction": " ".join(corrections) if corrections else None,
    }


def _single_tests_pass_verdict(
    claim: dict[str, Any],
    events: list[HarnessEvent],
    goal: Goal | None,
    workspace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest_unittest = _latest_unittest(events)
    latest_pytest = _latest_pytest(events)
    if latest_unittest is not None and (
        latest_pytest is None or latest_unittest[2] > latest_pytest[2]
    ):
        event, info, index, invocation = latest_unittest
        exit_code = info.get("exit_code")
        valid_exit = isinstance(exit_code, int) and not isinstance(exit_code, bool)
        edits = _post_run_edits(events, index, workspace)
        evidence = [
            f"unittest_event_id={event.event_id}",
            f"unittest_scope={invocation.scope.value}",
            *([f"unittest_exit_code={exit_code}"] if valid_exit else []),
        ]
        if (valid_exit and exit_code != 0) or event.error:
            if edits:
                return {
                    "claim": claim,
                    "status": "uncertain",
                    "evidence": [*evidence, f"later_edit:{edits[-1]}"],
                    "correction": None,
                }
            node = info.get("failed")
            detail = f"The latest observed unittest run failed (exit {exit_code})."
            if node:
                detail += f" Failing test: {node}."
            return {
                "claim": claim,
                "status": "contradicted",
                "evidence": [*evidence, "unittest_ok=false"],
                "correction": f"You said the tests pass. {detail} Continue from that failure.",
            }
        shadow = _module_shadow_evidence(invocation.argv, workspace)
        entry_point = _entry_point_evidence(invocation.argv, workspace)
        if shadow or entry_point:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*evidence, "unittest_ok=true", *shadow, *entry_point],
                "correction": None,
                "probe": (
                    "The observed unittest result ran under `python -m`, which imports "
                    "from the worker workspace; a same-named module or a pruned-env "
                    "launcher shim there could have produced this output. Remove the "
                    "shadow file or observe a supervisor-run suite before trusting it."
                ),
            }
        if _unittest_supports_goal(info, invocation, edits=edits, goal=goal, workspace=workspace):
            return {
                "claim": claim,
                "status": "supported",
                "evidence": [*evidence, "unittest_ok=true"],
                "correction": None,
            }
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [*evidence, "unittest_evidence_inconsistent"],
            "correction": None,
        }
    latest = latest_pytest
    if latest is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["no_pytest_observed"],
            "correction": None,
        }
    event, info, index, invocation = latest
    ok = info.get("ok")
    exit_code = info.get("exit_code")
    valid_exit = isinstance(exit_code, int) and not isinstance(exit_code, bool)
    count_requirement = _test_count_requirement(goal)
    observed_count = _observed_pytest_count(info)
    node = _failed_node(info, event)
    edits = _post_run_edits(events, index, workspace)
    provenance = [
        f"pytest_event_id={event.event_id}",
        f"pytest_scope={invocation.scope.value}",
    ]
    if valid_exit:
        provenance.append(f"pytest_exit_code={exit_code}")
    if observed_count is not None:
        provenance.append(f"pytest_passed={observed_count}")
    for constraint in count_requirement.constraints:
        provenance.append(
            f"pytest_expected_{constraint.metric}_{constraint.comparator}={constraint.count}"
        )
        if constraint.metric == "passed" and constraint.comparator == "eq":
            provenance.append(f"pytest_expected_passed={constraint.count}")
    decisively_failed = (valid_exit and exit_code != 0) or bool(event.error or node)
    # Launcher-shadow, entry-point, and nonpassing checks are computed once
    # so a post-run-edit return still reports every independent disqualifier
    # — flag masking would otherwise hide the more actionable signal.
    shadow = _module_shadow_evidence(invocation.argv, workspace)
    entry_point = _entry_point_evidence(invocation.argv, workspace)
    nonpassing = [
        f"pytest_nonpassing:{key}={info.get(key)}"
        for key in ("skipped", "xfailed", "xpassed")
        if isinstance(info.get(key), int)
        and not isinstance(info.get(key), bool)
        and info.get(key) > 0
    ]
    nonpassing.extend(_pytest_failure_signals(info))
    if decisively_failed:
        if edits:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [
                    *provenance,
                    f"pytest_ok={ok}",
                    *([f"failed:{node}"] if node else []),
                    f"later_edit:{edits[-1]}",
                ],
                "correction": None,
                "probe": (
                    f"The latest pytest run failed, then {edits[-1]} changed. "
                    "Observe a new pytest result before deciding whether the claim is true."
                ),
            }
        bits = ["The latest observed pytest run failed"]
        if valid_exit:
            bits.append(f"(exit {exit_code})")
        detail = " ".join(bits) + "."
        if node:
            detail += f" Failing test: {node}."
        detail += " Continue from that failure."
        evidence = [
            *provenance,
            f"pytest_ok={ok}",
            *([f"failed:{node}"] if node else []),
        ]
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": evidence,
            "correction": f"You said the test suite passes. {detail}",
        }
    if ok is True and edits:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [
                *provenance,
                "pytest_ok=true",
                f"later_edit:{edits[-1]}",
                *shadow,
                *entry_point,
                *nonpassing,
            ],
            "correction": None,
        }
    if ok is True and (not valid_exit or exit_code != 0):
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [*provenance, "pytest_terminal_exit_unavailable_or_inconsistent"],
            "correction": None,
            "probe": "Observe a terminal full-suite pytest exit before supporting this claim.",
        }
    if ok is True:
        if invocation.scope != PytestInvocationScope.FULL_SUITE:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_ok=true"],
                "correction": None,
                "probe": "Observe a full-suite pytest result before supporting this claim.",
            }
        if count_requirement.status == "ambiguous":
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_count_requirement_ambiguous"],
                "correction": None,
                "probe": (
                    "Clarify the conflicting, unsupported, or malformed test-count "
                    "requirement before deciding whether the suite satisfies the goal."
                ),
            }
        missing_counts, violated_counts = _test_count_violations(count_requirement, info)
        if missing_counts:
            labels = ", ".join(
                f"{item.metric} {item.comparator} {item.count}" for item in missing_counts
            )
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_required_count_unavailable"],
                "correction": None,
                "probe": (
                    "Observe a terminal full-suite pytest result containing the required "
                    f"count evidence ({labels}) before supporting this claim."
                ),
            }
        if violated_counts:
            required = ", ".join(
                (
                    f"{item.count} passing tests"
                    if item.metric == "passed" and item.comparator == "eq"
                    else f"exactly {item.count} collected tests"
                    if item.comparator == "eq"
                    else f"at least {item.count} {item.metric} tests"
                )
                for item in violated_counts
            )
            observed = ", ".join(
                f"{item.metric}={_observed_pytest_metric(info, item.metric)}"
                for item in violated_counts
            )
            return {
                "claim": claim,
                "status": "contradicted",
                "evidence": provenance,
                "correction": (
                    "You said the test suite passes, but the persistent goal requires "
                    f"{required} and the latest full-suite run observed {observed}. "
                    "Verify collection and satisfy the declared test count."
                ),
            }
        if shadow or entry_point or nonpassing:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [
                    *provenance,
                    "pytest_ok=true",
                    *shadow,
                    *entry_point,
                    *nonpassing,
                ],
                "correction": None,
                "probe": (
                    "The run exited green, but "
                    + "; ".join(
                        [
                            *(
                                ["the `python -m` launch can import a workspace-root module"]
                                if shadow
                                else []
                            ),
                            *(
                                [
                                    "a pruned workspace env dir can host a same-named "
                                    "launcher shim the inventory never sees"
                                ]
                                if entry_point
                                else []
                            ),
                            *(
                                ["it reported nonpassing results a passing claim must answer"]
                                if nonpassing
                                else []
                            ),
                        ]
                    )
                    + ". Re-verify before trusting it."
                ),
            }
        if not _pytest_supports_goal(info, invocation, edits=edits, goal=goal, workspace=workspace):
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [*provenance, "pytest_evidence_inconsistent"],
                "correction": None,
            }
        return {
            "claim": claim,
            "status": "supported",
            "evidence": [*provenance, "pytest_ok=true"],
            "correction": None,
        }
    return {
        "claim": claim,
        "status": "uncertain",
        "evidence": [*provenance, "pytest_observed_without_exit"],
        "correction": None,
    }


def _artifact_producer_witnessed(events: list[HarnessEvent], artifact: str) -> bool:
    """Whether some ledger event plausibly produced the declared artifact.

    A file_edit/tool event carrying the path is a write witness; a shell
    command naming it (redirect, flag, arg) is a producer witness. Worker
    narration alone does not count — producing is an act, not a claim.
    """

    target = str(artifact).replace("\\", "/")
    base = target.rsplit("/", 1)[-1]
    if not base:
        return False
    for event in events:
        if event.event_type == EventType.SHELL and isinstance(event.command, str):
            if base in event.command:
                return True
        for path in event.file_paths or []:
            normalized = str(path).replace("\\", "/")
            if (
                normalized == target
                or normalized.endswith(f"/{target}")
                or target.endswith(f"/{normalized}")
                or normalized.rsplit("/", 1)[-1] == base
            ):
                return True
    return False


def _evaluation_verdict(
    claim: dict[str, Any],
    goal: Goal | None,
    workspace: dict[str, Any],
    events: list[HarnessEvent] | None = None,
) -> dict[str, Any]:
    expected = _expected_rows(goal)
    files = _observed_files(workspace)
    if expected is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["no_row_requirement"],
            "correction": None,
        }
    if files is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["workspace_unobserved"],
            "correction": None,
        }
    path, count = _artifact_rows(goal, workspace)
    if path is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [f"expected_rows={expected}", "no_declared_row_artifact"],
            "correction": None,
        }
    if count is None:
        missing = _missing_required_files(goal, workspace)
        if missing is None:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [f"expected_rows={expected}", f"row_count_unavailable:{path}"],
                "correction": None,
            }
        if _workspace_path_key(path, workspace) not in {
            _workspace_path_key(item, workspace) for item in missing
        }:
            return {
                "claim": claim,
                "status": "uncertain",
                "evidence": [f"expected_rows={expected}", f"row_count_unavailable:{path}"],
                "correction": None,
            }
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": [f"expected_rows={expected}", f"missing:{path}"],
            "correction": (
                f"You marked the evaluation complete, but acceptance requires {expected} rows. "
                f"{path} is missing from the workspace. Produce the full "
                "evaluation file before stopping."
            ),
        }
    if count < expected:
        return {
            "claim": claim,
            "status": "contradicted",
            "evidence": [f"expected_rows={expected}", f"{path}_rows={count}"],
            "correction": (
                f"You marked the task complete, but acceptance requires {expected} "
                f"evaluation rows. {path} currently contains {count}. Resume the "
                "evaluation and verify the final row count before stopping."
            ),
        }
    if events is not None and not _artifact_producer_witnessed(events, path):
        # The count is right but nobody watched it be produced — a single
        # fabricated write of dict rows is indistinguishable from a real
        # evaluation. Row counts can corroborate, not carry, a claim.
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [f"{path}_rows={count}", f"rows_unwitnessed:{path}"],
            "correction": None,
            "probe": (
                f"Show the command or edit that produced {path} — the row "
                "count alone cannot prove the evaluation ran."
            ),
        }
    return {
        "claim": claim,
        "status": "supported",
        "evidence": [f"{path}_rows={count}"],
        "correction": None,
    }


def _expected_content(raw: str) -> tuple[str, str, bool] | None:
    # Markdown code spans around the path are formatting, not part of the
    # filename. Normalize only a complete leading path span; preserve literal
    # quoting and reject unsupported/unsafe paths through the existing checks.
    raw = raw.strip()
    quoted_path = re.match(r"^`(?P<path>[^`\r\n]+)`(?=\s)", raw)
    if quoted_path is not None:
        path = quoted_path.group("path")
        if not FILE_TOKEN.fullmatch(path) or not _visible_goal_path(path):
            return None
        raw = path + raw[quoted_path.end() :]
    exact = FILE_EXACT_CONTENT.fullmatch(raw.strip())
    if exact is not None:
        path = exact.group("path")
        literal = exact.group("literal")
        if literal[:1] in {"`", '"', "'"}:
            literal = literal[1:-1]
        if exact.group("newline"):
            literal += "\n"
        return (path, literal, True) if _visible_goal_path(path) else None
    match = FILE_CONTAINS.search(raw.strip())
    if match is None:
        return None
    expected = match.group("expected").strip().strip("`\"'")
    # Unsupported exact-content prose is uncertain, never silently weakened
    # into a substring requirement or interpreted as literal suffix text.
    if re.match(r"^exactly\s+", expected, flags=re.I):
        return None
    expected = re.sub(r"^the\s+word\s+", "", expected, flags=re.I)
    expected = expected.strip().strip("`\"'")
    if not expected:
        return None
    path = match.group("path").replace("\\", "/")
    return (path, expected, False) if _visible_goal_path(path) else None


def _expected_file_rows(raw: str) -> tuple[str, int] | None:
    match = FILE_ROWS.search(raw.strip())
    if match is None:
        return None
    path = match.group("path").replace("\\", "/")
    count = _parse_expected_rows(match.group("count"))
    return (path, count) if count is not None and _visible_goal_path(path) else None


def _expected_exists(raw: str) -> str | None:
    match = FILE_EXISTS.search(raw.strip())
    if match is None:
        return None
    path = match.group("path").replace("\\", "/")
    return path if _visible_goal_path(path) else None


def _read_goal_file(
    workspace: dict[str, Any],
    relpath: str,
    limit: int = 4_000_000,
) -> tuple[str, bool] | None:
    if not _visible_goal_path(relpath):
        return None
    try:
        root = _native_workspace_root(workspace)
        if root is None:
            return None
        target = (root / relpath).resolve()
        target.relative_to(root)
        if not target.is_file():
            return None
        for attempt in range(10):
            try:
                with target.open("rb") as handle:
                    data = handle.read(limit + 1)
                complete = len(data) <= limit
                return data[:limit].decode("utf-8"), complete
            except PermissionError:
                if attempt == 9:
                    return None
                # Some Windows harness commands release their final file handle
                # just after the turn-completed event. Bound the settle window.
                time.sleep(0.05)
        return None
    except (OSError, ValueError, UnicodeError):
        return None


def _trailing_byte_hex(text: str, limit: int = 16) -> str:
    suffix = text[len(text.rstrip("\r\n")) :].encode("utf-8")
    hexed = suffix[:limit].hex(" ").upper()
    if len(suffix) > limit:
        hexed = f"{hexed} …+{len(suffix) - limit} more bytes"
    return hexed or "none"


def _required_content_note(goal: Goal | None, name: str) -> tuple[str, bool] | None:
    """Exact-content requirement text for one required file, if the goal pins it.

    The flag marks content ending in invisible trailing bytes that a
    line-oriented read view cannot confirm.
    """
    if goal is None:
        return None
    objective = re.sub(r"^(?:create|write|update)\s+", "", goal.objective.strip(), flags=re.I)
    for raw in [objective, *goal.acceptance_criteria]:
        expected = _expected_content(str(raw or ""))
        if (
            expected is not None
            and expected[0].replace("\\", "/") == name.replace("\\", "/")
            and expected[2]
            and len(expected[1]) <= 160
        ):
            has_trailing = bool(expected[1][len(expected[1].rstrip("\r\n")) :])
            note = f"The attached acceptance criterion requires exact content {expected[1]!r}"
            if has_trailing:
                note += f", which ends with byte {_trailing_byte_hex(expected[1])}"
            return f"{note}.", has_trailing
    return None


def _gap_correction(fragments: list[str], byte_guidance: bool) -> str:
    """One worker-facing correction covering every file gap at this stop."""
    listed = " ".join(fragments[:4])
    if len(fragments) > 4:
        listed += f" {len(fragments) - 4} more files also fail."
    if byte_guidance:
        return (
            f"{listed} A line-oriented read view cannot verify those bytes. Write "
            "the exact content, then confirm each file's trailing bytes with a "
            "shell byte-level check such as a hex dump before stopping."
        )
    if len(fragments) == 1:
        return f"{listed} Create or correct the file and verify it before stopping."
    return f"{listed} Create or correct the listed files and verify them before stopping."


def _goal_file_verdict(
    claim: dict[str, Any] | None,
    goal: Goal | None,
    workspace: dict[str, Any],
    events: list[HarnessEvent] | None = None,
) -> dict[str, Any]:
    if goal is None:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["goal_unattached"],
            "correction": None,
        }
    required = _required_files(goal)
    if not required:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": ["no_file_acceptance_requirement"],
            "correction": None,
        }

    # Collect every file gap before answering. One correction that names all of
    # them lets the worker fix them in a single turn instead of spending a
    # follow-up round trip per file.
    missing = _missing_required_files(goal, workspace)
    missing_set = {_workspace_path_key(name, workspace) for name in (missing or [])}
    evidence = [
        f"exists:{name}"
        for name in required
        if _workspace_path_key(name, workspace) not in missing_set
    ]
    evidence.extend(f"missing:{name}" for name in missing or [])
    fragments: list[str] = []
    byte_guidance = False
    for name in missing or []:
        note = _required_content_note(goal, name)
        byte_guidance = byte_guidance or (note is not None and note[1])
        fragments.append(
            f"{name} is missing from the current workspace."
            + (f" {note[0]}" if note is not None else "")
        )

    unresolved: list[str] = []
    checks: list[tuple[str, str, bool]] = []
    row_checks: list[tuple[str, int]] = []
    # The acceptance list cannot weaken an explicit exact-file objective.
    # Reuse the whole-string parser: compound/unsupported prose is not guessed,
    # and ordinary "contains" objectives do not become byte-exact requirements.
    objective = re.sub(r"^(?:create|write|update)\s+", "", goal.objective.strip(), flags=re.I)
    objective_check = _expected_content(objective)
    if objective_check is not None and objective_check[2]:
        checks.append(objective_check)
    for raw in goal.acceptance_criteria:
        criterion = str(raw or "").strip()
        if not criterion:
            continue
        # Test-suite acceptance is resolved from the typed harness execution
        # below, not from the workspace file snapshot. Keeping it in the
        # generic unresolved bucket made a witnessed full-suite pass unable to
        # satisfy an otherwise machine-checkable goal.
        if _PYTEST_REQUIREMENT.search(criterion):
            continue
        if FILE_TOKEN.fullmatch(criterion):
            continue
        row_check = _expected_file_rows(criterion)
        content_check = _expected_content(criterion)
        if row_check is not None:
            row_checks.append(row_check)
        elif content_check is not None:
            checks.append(content_check)
        else:
            unresolved.append(criterion)
    for raw in goal.evidence_requirements:
        requirement = str(raw or "").strip()
        if (
            requirement
            and not FILE_TOKEN.fullmatch(requirement)
            and not _PYTEST_REQUIREMENT.search(requirement)
        ):
            unresolved.append(requirement)

    deferred_uncertain: dict[str, Any] | None = None
    seen_checks: set[tuple[str, str, bool]] = set()
    for path, expected, exact in checks:
        key = (_workspace_path_key(path, workspace), expected, exact)
        if key[0] in missing_set or key in seen_checks:
            continue
        seen_checks.add(key)
        observed_content = _read_goal_file(workspace, path)
        if observed_content is None:
            evidence.append(f"temporarily_unreadable:{path}")
            if deferred_uncertain is None:
                deferred_uncertain = {
                    "claim": claim,
                    "status": "uncertain",
                    "evidence": [f"temporarily_unreadable:{path}"],
                    "correction": None,
                    "probe": f"Retry a bounded read of {path} before deciding completion.",
                }
            continue
        content, complete = observed_content
        matches = (complete and content == expected) if exact else expected in content
        if not matches:
            if not complete:
                evidence.append(f"content_check_incomplete:{path}")
                if deferred_uncertain is None:
                    deferred_uncertain = {
                        "claim": claim,
                        "status": "uncertain",
                        "evidence": [f"content_check_incomplete:{path}"],
                        "correction": None,
                        "probe": (
                            f"{path} exceeds the bounded content verifier. Observe an exact "
                            "targeted check before deciding completion."
                        ),
                    }
                continue
            fragments.append(
                f"{path} exists but does not {'equal' if exact else 'contain'} {expected[:160]!r}."
            )
            if exact and content.rstrip("\r\n") == expected.rstrip("\r\n"):
                fragments[-1] += (
                    " The visible lines match, but the trailing bytes differ: "
                    f"expected {_trailing_byte_hex(expected)}; "
                    f"observed {_trailing_byte_hex(content)}."
                )
                byte_guidance = True
            evidence.append(
                f"{'content_mismatch' if exact else 'content_missing'}:{path}:{expected}"
            )
            continue
        evidence.append(f"{'equals' if exact else 'contains'}:{path}:{expected}")
    seen_rows: set[tuple[str, int]] = set()
    for path, expected_rows in row_checks:
        row_key = (_workspace_path_key(path, workspace), expected_rows)
        if row_key[0] in missing_set or row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        _, count = _artifact_rows(goal, workspace, path)
        if count is None:
            evidence.append(f"row_count_unavailable:{path}")
            if deferred_uncertain is None:
                deferred_uncertain = {
                    "claim": claim,
                    "status": "uncertain",
                    "evidence": [f"row_count_unavailable:{path}"],
                    "correction": None,
                    "probe": (
                        f"Observe a complete row count for {path} before deciding completion."
                    ),
                }
            continue
        if count < expected_rows:
            fragments.append(f"{path} contains {count} rows; acceptance requires {expected_rows}.")
            evidence.extend([f"expected_rows={expected_rows}", f"{path}_rows={count}"])
            continue
        evidence.append(f"{path}_rows={count}")
        if events is not None and not _artifact_producer_witnessed(events, path):
            evidence.append(f"rows_unwitnessed:{path}")
            if deferred_uncertain is None:
                deferred_uncertain = {
                    "claim": claim,
                    "status": "uncertain",
                    "evidence": [f"{path}_rows={count}", f"rows_unwitnessed:{path}"],
                    "correction": None,
                    "probe": (
                        f"Show the command or edit that produced {path} — "
                        "the row count alone cannot prove the evaluation ran."
                    ),
                }
    if fragments:
        return {
            "claim": claim,
            "status": "unsatisfied" if claim is None else "contradicted",
            "basis": "acceptance_criterion" if claim is None else "worker_claim",
            "evidence": evidence,
            "correction": _gap_correction(fragments, byte_guidance),
        }
    if deferred_uncertain is not None:
        return deferred_uncertain
    if unresolved:
        return {
            "claim": claim,
            "status": "uncertain",
            "evidence": [*evidence, *(f"unchecked:{item}" for item in unresolved)],
            "correction": None,
        }
    return {
        "claim": claim,
        "status": "supported",
        "evidence": evidence,
        "correction": None,
    }


def _effective_verdicts(verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ignore only redundant, uncheckable generic completion in the same event.

    A verified specific claim such as ``tests_pass`` is not weakened by the
    worker appending "I am done" to that same response. Contradictions and
    acceptance gaps are never ignored, and generic completion on its own stays
    uncertain.
    """
    supported_sources = {
        str(claim.get("source_event_id"))
        for verdict in verdicts
        if verdict.get("status") == "supported"
        and isinstance((claim := verdict.get("claim")), dict)
        and claim.get("kind") in _SPECIFIC_COMPLETION_KINDS
        and claim.get("source_event_id")
    }
    effective: list[dict[str, Any]] = []
    for verdict in verdicts:
        claim = verdict.get("claim")
        is_redundant_generic = (
            verdict.get("status") == "uncertain"
            and isinstance(claim, dict)
            and claim.get("kind") == "complete"
            and bool(_GENERIC_DONE.search(str(claim.get("statement") or "")))
            and str(claim.get("source_event_id") or "") in supported_sources
        )
        if not is_redundant_generic:
            effective.append(verdict)
    return effective


def _unfinished_pytest_verdict(
    events: list[HarnessEvent], goal: Goal | None, workspace: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """A STOP with a still-failing pytest is unfinished work, even without a tests-pass claim."""
    latest = _latest_pytest(events)
    if latest is None:
        return None
    event, info, index, invocation = latest
    ok = info.get("ok")
    node = _failed_node(info, event)
    if _post_run_edits(events, index, workspace):
        return None
    exit_code = info.get("exit_code")
    failed_exit = type(exit_code) is int and exit_code != 0
    if failed_exit or ok is False or (ok is None and (event.error or node)):
        bits = ["The latest observed pytest run failed"]
        if info.get("exit_code") not in (None, ""):
            bits.append(f"(exit {info.get('exit_code')})")
        detail = " ".join(bits) + "."
        if node:
            detail += f" Failing test: {node}."
        detail += " Continue from that failure."
        return {
            "claim": None,
            "status": "unsatisfied",
            "basis": "acceptance_criterion",
            "evidence": [
                f"pytest_event_id={event.event_id}",
                f"pytest_scope={invocation.scope.value}",
                f"pytest_ok={ok}",
                *([f"pytest_exit_code={exit_code}"] if type(exit_code) is int else []),
                *([f"failed:{node}"] if node else []),
            ],
            "correction": detail,
        }
    if (
        ok is not True
        or not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code != 0
        or invocation.scope != PytestInvocationScope.FULL_SUITE
    ):
        return None
    requirement = _test_count_requirement(goal)
    if requirement.status != "valid":
        return None
    _missing, violated = _test_count_violations(requirement, info)
    if not violated:
        return None
    expected = ", ".join(f"{item.metric} {item.comparator} {item.count}" for item in violated)
    observed = ", ".join(
        f"{item.metric}={_observed_pytest_metric(info, item.metric)}" for item in violated
    )
    return {
        "claim": None,
        "status": "unsatisfied",
        "basis": "acceptance_criterion",
        "evidence": [
            f"pytest_event_id={event.event_id}",
            f"pytest_scope={invocation.scope.value}",
            f"pytest_count_requirement={expected}",
            f"pytest_observed_counts={observed}",
        ],
        "correction": (
            "The latest full-suite pytest run exited successfully but did not satisfy "
            f"the persistent test-count requirement ({expected}; observed {observed}). "
            "Restore the missing collection or tests and run the full suite again."
        ),
    }


def _goal_requirement_text(goal: Goal | None) -> str:
    if goal is None:
        return ""
    return " ".join([goal.objective, *goal.acceptance_criteria, *goal.evidence_requirements])


def _command_exit_targets(goal: Goal | None) -> list[str]:
    names: list[str] = []
    sources = [
        *(goal.evidence_requirements if goal else ()),
        *(goal.acceptance_criteria if goal else ()),
    ]
    for raw in sources:
        for match in _COMMAND_EXIT_REQUIREMENT.finditer(str(raw or "")):
            path = match.group("path").replace("\\", "/")
            if (
                FILE_TOKEN.fullmatch(path) or path.endswith((".sh", ".ps1", ".js", ".mjs", ".py"))
            ) and _visible_goal_path(path):
                names.append(path)
    return list(dict.fromkeys(names))


def _artifact_tail_targets(goal: Goal | None) -> list[str]:
    names: list[str] = []
    if goal is None:
        return names
    for raw in list(goal.acceptance_criteria or []) + list(goal.evidence_requirements or []):
        row_check = _expected_file_rows(str(raw or ""))
        if row_check is not None:
            names.append(row_check[0])
            continue
        content_check = _expected_content(str(raw or ""))
        if content_check is not None:
            names.append(content_check[0])
    return list(dict.fromkeys(names))


def verification_probe_targets(
    kind: VerificationProbeKind | None,
    goal: Goal | None,
) -> tuple[str, ...]:
    """Select contained relative targets for a bridge-minted probe."""

    if kind == VerificationProbeKind.FILE_COUNT:
        return tuple(_required_files(goal)[:256])
    if kind == VerificationProbeKind.ARTIFACT_TAIL:
        return tuple(_artifact_tail_targets(goal)[:256])
    if kind == VerificationProbeKind.COMMAND_EXIT:
        return tuple(_command_exit_targets(goal)[:256])
    if kind == VerificationProbeKind.PYTHON_UNITTEST:
        return _goal_unittest_targets(goal)[:256]
    return ()


def required_verification_probe_kind(
    claims: list[dict[str, Any]],
    events: list[HarnessEvent],
    goal: Goal | None,
    verification: dict[str, Any],
    workspace: dict[str, Any] | None = None,
) -> VerificationProbeKind | None:
    """Select a closed probe only when missing evidence can answer the uncertainty."""

    if verification.get("status") not in {"uncertain", "no_claims"}:
        return None
    claims_require_tests = any(
        item.get("polarity") != "denied" and item.get("kind") == "tests_pass" for item in claims
    )
    goal_requires_unittest = _UNITTEST_REQUIREMENT.search(_goal_requirement_text(goal)) is not None
    if goal_requires_unittest:
        latest = _latest_unittest(events)
        if latest is None:
            return VerificationProbeKind.PYTHON_UNITTEST
        _event, info, index, invocation = latest
        if _unittest_supports_goal(
            info,
            invocation,
            edits=_post_run_edits(events, index, workspace),
            goal=goal,
            workspace=workspace,
        ):
            if re.search(r"\bpytest\b", _goal_requirement_text(goal), re.I) is None:
                return None
        else:
            return VerificationProbeKind.PYTHON_UNITTEST
    goal_requires_pytest = _PYTEST_REQUIREMENT.search(_goal_requirement_text(goal)) is not None
    if claims_require_tests or goal_requires_pytest:
        if _test_count_requirement(goal).status == "ambiguous":
            # Another pytest run cannot resolve contradictory or unsupported goal
            # language; require semantic/human clarification instead of looping.
            return None
        latest = _latest_pytest(events)
        if latest is None:
            return VerificationProbeKind.PYTEST
        _event, info, index, invocation = latest
        edits = _post_run_edits(events, index, workspace)
        if _pytest_supports_goal(info, invocation, edits=edits, goal=goal, workspace=workspace):
            return None
        return VerificationProbeKind.PYTEST
    evidence = [
        str(item)
        for verdict in verification.get("verdicts") or []
        if isinstance(verdict, dict)
        for item in verdict.get("evidence") or []
    ]
    if any(
        item.startswith("row_count_unavailable:") or item.startswith("content_check_incomplete:")
        for item in evidence
    ) and _artifact_tail_targets(goal):
        return VerificationProbeKind.ARTIFACT_TAIL
    if any(item.startswith("temporarily_unreadable:") for item in evidence) and _required_files(
        goal
    ):
        return VerificationProbeKind.FILE_COUNT
    if _SERVICE_HEALTH_REQUIREMENT.search(_goal_requirement_text(goal)):
        return VerificationProbeKind.SERVICE_HEALTH
    if any(item == "no_external_check" for item in evidence) and _command_exit_targets(goal):
        return VerificationProbeKind.COMMAND_EXIT
    return None


def verify_claims(
    claims: list[dict[str, Any]],
    events: list[HarnessEvent],
    goal: Goal | None,
    workspace: dict[str, Any] | None = None,
    acceptance_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = workspace or {}
    surface = acceptance_surface_delta(acceptance_baseline, workspace)
    asserted = [item for item in claims if item.get("polarity") != "denied"]
    verdicts: list[dict[str, Any]] = []
    for claim in asserted:
        kind = str(claim.get("kind") or "")
        if kind == "tests_pass":
            verdicts.append(_tests_pass_verdict(claim, events, goal, workspace))
        elif kind in {"evaluation_complete", "complete"}:
            eval_verdict = _evaluation_verdict(claim, goal, workspace, events)
            verdicts.append(
                _goal_file_verdict(claim, goal, workspace, events)
                if eval_verdict["status"] == "uncertain"
                else eval_verdict
            )
        elif kind in _COMPLETION_KINDS:
            if kind == "deployment_complete":
                # Deployment needs an external health/exit check: file presence
                # alone never supports it. Missing-file contradictions still
                # stand; anything else stays uncertain with no_external_check.
                file_verdict = _goal_file_verdict(claim, goal, workspace, events)
                if file_verdict.get("status") == "contradicted":
                    verdicts.append(file_verdict)
                else:
                    verdicts.append(
                        {
                            "claim": claim,
                            "status": "uncertain",
                            "evidence": ["no_external_check"],
                            "correction": None,
                        }
                    )
            else:
                file_verdict = _goal_file_verdict(claim, goal, workspace, events)
                if file_verdict["status"] == "uncertain":
                    file_verdict = {
                        "claim": claim,
                        "status": "uncertain",
                        "evidence": ["no_external_check"],
                        "correction": None,
                    }
                verdicts.append(file_verdict)
        else:
            # An asserted claim PEX cannot independently check cannot ride
            # along under a supported sibling verdict — it is uncertain, so
            # "implemented X and migrated prod; all tests pass" does not verify
            # whole on the strength of the test claim alone.
            verdicts.append(
                {
                    "claim": claim,
                    "status": "uncertain",
                    "evidence": ["claim_not_independently_verifiable"],
                    "correction": None,
                }
            )
    acceptance_gap = _goal_file_verdict(None, goal, workspace, events)
    goal_requires_pytest = _PYTEST_REQUIREMENT.search(_goal_requirement_text(goal)) is not None
    latest_pytest = _latest_pytest(events)
    if goal_requires_pytest:
        pytest_supported = False
        pytest_evidence: list[str] = []
        if latest_pytest is not None:
            pytest_event, pytest_info, pytest_index, pytest_invocation = latest_pytest
            pytest_supported = _pytest_supports_goal(
                pytest_info,
                pytest_invocation,
                edits=_post_run_edits(events, pytest_index, workspace),
                goal=goal,
                workspace=workspace,
            )
            pytest_evidence = [
                f"pytest_event_id={pytest_event.event_id}",
                f"pytest_scope={pytest_invocation.scope.value}",
            ]
            if pytest_supported:
                pytest_evidence.append("pytest_ok=true")
            else:
                pytest_evidence.extend(_module_shadow_evidence(pytest_invocation.argv, workspace))
                pytest_evidence.extend(_entry_point_evidence(pytest_invocation.argv, workspace))
                pytest_evidence.extend(
                    f"pytest_nonpassing:{key}={pytest_info.get(key)}"
                    for key in ("skipped", "xfailed", "xpassed")
                    if isinstance(pytest_info.get(key), int)
                    and not isinstance(pytest_info.get(key), bool)
                    and pytest_info.get(key) > 0
                )
                pytest_evidence.extend(_pytest_failure_signals(pytest_info))
        if pytest_supported:
            acceptance_gap["evidence"] = list(
                dict.fromkeys([*(acceptance_gap.get("evidence") or []), *pytest_evidence])
            )
        elif acceptance_gap.get("status") == "supported":
            acceptance_gap = {
                "claim": None,
                "status": "uncertain",
                "evidence": [
                    *(acceptance_gap.get("evidence") or []),
                    *pytest_evidence,
                    "unchecked:full-suite pytest exits successfully",
                ],
                "correction": None,
            }
    acceptance_status = acceptance_gap.get("status")
    acceptance_evidence = list(acceptance_gap.get("evidence") or [])
    if acceptance_gap.get("status") == "supported":
        acceptance_gap = None
    if acceptance_gap and acceptance_gap.get("status") != "uncertain":
        gap_evidence = set(acceptance_gap.get("evidence") or [])
        covered = bool(gap_evidence) and any(
            gap_evidence <= set(item.get("evidence") or []) for item in verdicts
        )
        if not covered:
            verdicts.append(acceptance_gap)
    pytest_gap = _unfinished_pytest_verdict(events, goal, workspace)
    if pytest_gap and not any(
        str(item).startswith("pytest_ok=")
        for verdict in verdicts
        for item in (verdict.get("evidence") or [])
    ):
        verdicts.append(pytest_gap)
    # A pass observed over acceptance-surface files that changed since the
    # sealed baseline is not independent evidence: the worker may have
    # weakened the tests it then ran. Keep such claims honest-uncertain and
    # name the files instead of trusting or accusing.
    surface_flags = [
        *(f"acceptance_surface_modified:{path}" for path in surface["modified"]),
        *(f"acceptance_surface_deleted:{path}" for path in surface["deleted"]),
        *(f"acceptance_surface_unhashed:{path}" for path in surface["unhashed"]),
        *(f"acceptance_surface_config_added:{path}" for path in surface["added_config"]),
        *_surface_symlink_evidence(workspace),
    ]
    goal_requires_tests = goal_requires_pytest or (
        _UNITTEST_REQUIREMENT.search(_goal_requirement_text(goal)) is not None
    )
    if surface.get("sealed_at_claim") and (surface["surface_files"] or goal_requires_tests):
        # The flag needs an observed surface to protect — except when the goal
        # requires tests at all: sealing an *empty* surface at claim time is
        # exactly what a deleted-tests-then-claim run looks like.
        surface_flags.append("acceptance_surface_baseline_at_claim")
    if surface["baselined"] and not surface["baseline_complete"]:
        surface_flags.append("acceptance_surface_baseline_incomplete")
    if surface["baselined"] and not surface["checked"]:
        surface_flags.append("acceptance_surface_check_incomplete")
    if surface.get("surface_complete") is False:
        # The inventory itself reports a truncated acceptance surface: even
        # without a baseline to compare, a supported verdict would rest on an
        # incomplete observation.
        if "acceptance_surface_check_incomplete" not in surface_flags:
            surface_flags.append("acceptance_surface_check_incomplete")
    if surface["reason"] == "unsealed" or (
        acceptance_baseline is not None
        and not surface["baselined"]
        and (surface["surface_files"] or goal_requires_tests)
    ):
        # The caller engaged integrity checking but no baseline could be
        # established — unsealed (corrupt/failed) rows flag unconditionally;
        # absent baselines flag when an observable surface exists.
        surface_flags.append("acceptance_surface_unbaselined")
    if surface_flags:
        downgraded: list[dict[str, Any]] = []
        for verdict in verdicts:
            if verdict.get("status") != "supported":
                downgraded.append(verdict)
                continue
            downgraded.append(
                {
                    **verdict,
                    "status": "uncertain",
                    "correction": None,
                    "evidence": [
                        *(verdict.get("evidence") or []),
                        *surface_flags,
                    ],
                    "probe": (
                        "Acceptance-surface files changed after the recorded "
                        "baseline. Re-verify the suite from pristine acceptance "
                        "inputs before trusting a reported pass."
                    ),
                }
            )
        verdicts = downgraded
        acceptance_evidence = list(dict.fromkeys([*acceptance_evidence, *surface_flags]))
        if acceptance_status == "supported":
            acceptance_status = "uncertain"
    contradicted = [item for item in verdicts if item["status"] == "contradicted"]
    unsatisfied = [item for item in verdicts if item["status"] == "unsatisfied"]
    effective = _effective_verdicts(verdicts)
    supported = [item for item in effective if item["status"] == "supported"]
    if contradicted:
        status = "contradicted"
    elif unsatisfied:
        status = "acceptance_gap"
    elif asserted and supported and len(supported) == len(effective):
        status = "supported"
    elif not asserted:
        status = "no_claims"
    else:
        status = "uncertain"
    chosen = contradicted[0] if contradicted else unsatisfied[0] if unsatisfied else None
    latest_unittest = _latest_unittest(events)
    pytest_provenance = (
        None
        if latest_pytest is None
        else {
            "event_id": latest_pytest[0].event_id,
            "scope": latest_pytest[3].scope.value,
        }
    )
    # Observed command facts remain useful even when claim extraction yields no
    # tests_pass claim. Do not conflate these facts with goal acceptance or an
    # independently executed check, and never include arbitrary output text.
    pytest_observation = None
    if latest_pytest is not None:
        pytest_event, pytest_info, pytest_index, invocation = latest_pytest
        pytest_observation = {
            "event_id": pytest_event.event_id,
            "scope": invocation.scope.value,
            "basis": "observed_worker_command",
            "later_file_edits_observed": any(
                item.event_type == EventType.FILE_EDIT for item in events[pytest_index + 1 :]
            ),
            "ok": pytest_info.get("ok") if type(pytest_info.get("ok")) is bool else None,
            "exit_code": (
                pytest_info.get("exit_code") if type(pytest_info.get("exit_code")) is int else None
            ),
        }
        for metric in ("passed", "failed_count", "skipped", "errors", "collected"):
            value = pytest_info.get(metric)
            if type(value) is int and 0 <= value <= 2**53 - 1:
                pytest_observation[metric] = value
    unittest_observation = None
    if latest_unittest is not None:
        unittest_event, unittest_info, unittest_index, invocation = latest_unittest
        unittest_observation = {
            "event_id": unittest_event.event_id,
            "scope": invocation.scope.value,
            "targets": list(invocation.relative_targets),
            "basis": "observed_worker_command",
            "later_file_edits_observed": any(
                item.event_type == EventType.FILE_EDIT for item in events[unittest_index + 1 :]
            ),
            "ok": (unittest_info.get("ok") if type(unittest_info.get("ok")) is bool else None),
            "exit_code": (
                unittest_info.get("exit_code")
                if type(unittest_info.get("exit_code")) is int
                else None
            ),
        }
    return {
        "status": status,
        "acceptance_status": acceptance_status,
        "acceptance_evidence": acceptance_evidence,
        "acceptance_surface": surface,
        "verdicts": verdicts,
        "correction": None if chosen is None else chosen.get("correction"),
        "evidence": list(
            dict.fromkeys(
                [
                    *([] if chosen is None else list(chosen.get("evidence") or [])),
                    *surface_flags,
                ]
            )
        ),
        "pytest_event_id": None if latest_pytest is None else latest_pytest[0].event_id,
        "pytest_scope": None if latest_pytest is None else latest_pytest[3].scope.value,
        "latest_pytest": pytest_provenance,
        "pytest_observation": pytest_observation,
        "unittest_event_id": (None if latest_unittest is None else latest_unittest[0].event_id),
        "unittest_observation": unittest_observation,
        "missing_files": [
            item[8:]
            for item in (chosen.get("evidence") or [] if chosen else [])
            if str(item).startswith("missing:")
        ],
    }

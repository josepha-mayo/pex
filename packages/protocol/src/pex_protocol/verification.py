"""Typed, auditable verification probes and evidence-gathering receipts."""

from __future__ import annotations

import re
import shlex
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pex_protocol.enums import HarnessType, PolicyVerdict

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_PYTHON_RUNNER = re.compile(r"^(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?$", re.I)
_POWERSHELL_EXECUTABLES = {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
_POWERSHELL_LITERAL_COMMAND = re.compile(
    r"^\s*(?P<executable>\"[^\"\r\n]*\"|[^\s'\"]+)\s+"
    r"-Command\s+'(?P<payload>[^'\r\n]+)'\s*$",
    re.I,
)
_POWERSHELL_LITERAL_FORBIDDEN = frozenset("$@,#{}`")


class PytestInvocationScope(StrEnum):
    """Coverage established by a concrete, safely parsed pytest invocation."""

    FULL_SUITE = "full_suite"
    TARGETED = "targeted"


class PytestInvocation(BaseModel):
    """A non-executable classification of an observed pytest command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    argv: tuple[Annotated[str, Field(min_length=1, max_length=4_096)], ...] = Field(
        min_length=1,
        max_length=128,
    )
    scope: PytestInvocationScope
    selectors: tuple[Annotated[str, Field(min_length=1, max_length=4_096)], ...] = Field(
        default_factory=tuple,
        max_length=128,
    )
    relative_targets: tuple[
        Annotated[str, Field(min_length=1, max_length=4_096)], ...
    ] = Field(default_factory=tuple, max_length=128)
    selection_flags: tuple[
        Annotated[str, Field(min_length=1, max_length=4_096)], ...
    ] = Field(default_factory=tuple, max_length=128)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        classified = Counter(self.relative_targets) + Counter(self.selection_flags)
        if Counter(self.selectors) != classified:
            raise ValueError("pytest selectors must exactly describe targets and flags")
        if self.scope == PytestInvocationScope.FULL_SUITE and self.selectors:
            raise ValueError("a full-suite pytest invocation cannot contain selectors")
        if self.scope == PytestInvocationScope.TARGETED and not self.selectors:
            raise ValueError("a targeted pytest invocation requires selectors")
        return self


_PYTEST_EXECUTABLES = {"pytest", "pytest.exe", "py.test", "py.test.exe"}
_TARGETED_FLAGS = {
    "--deselect",
    "--failed-first",
    "--ff",
    "--ignore",
    "--ignore-glob",
    "--keyword",
    "--last-failed",
    "--lf",
    "--markexpr",
    "--new-first",
    "--nf",
    "--stepwise",
    "--stepwise-skip",
    "--sw",
    "-k",
    "-m",
}
_REJECTED_MODES = {
    "--co",
    "--collect-only",
    "--collectonly",
    "--fixtures",
    "--fixtures-per-test",
    "--funcargs",
    "--help",
    "--markers",
    "--setup-only",
    "--setup-plan",
    "--trace-config",
    "--version",
    "-h",
}
_SAFE_VALUE_FLAGS = {
    "--basetemp",
    "--capture",
    "--code-highlight",
    "--color",
    "--cov",
    "--cov-config",
    "--cov-report",
    "--dist",
    "--durations",
    "--durations-min",
    "--html",
    "--import-mode",
    "--junit-prefix",
    "--junitxml",
    "--log-cli-date-format",
    "--log-cli-format",
    "--log-cli-level",
    "--log-date-format",
    "--log-file",
    "--log-file-date-format",
    "--log-file-format",
    "--log-file-level",
    "--log-format",
    "--log-level",
    "--maxfail",
    "--show-capture",
    "--tb",
    "--timeout",
    "--verbosity",
    "-w",
    "-n",
    "-p",
    "-r",
}
_SAFE_BOOLEAN_FLAGS = {
    "--cache-clear",
    "--continue-on-collection-errors",
    "--cov-append",
    "--cov-branch",
    "--cov-context",
    "--disable-warnings",
    "--exitfirst",
    "--full-trace",
    "--keep-duplicates",
    "--no-cov",
    "--no-header",
    "--no-summary",
    "--pastebin",
    "--quiet",
    "--runxfail",
    "--setup-show",
    "--strict-config",
    "--strict-markers",
    "--verbose",
    "-q",
    "-s",
    "-v",
    "-x",
}


def _command_has_shell_syntax(command: str) -> bool:
    """Reject command composition; only a single direct invocation is auditable."""

    quote: str | None = None
    escaped = False
    for index, char in enumerate(command):
        if quote != "'" and command[index : index + 2] == "$(":
            return True
        if quote != "'" and char == "`":
            return True
        if escaped:
            escaped = False
            continue
        if quote == "'":
            if char == "'":
                quote = None
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if quote is None and (char in ";&|<>\r\n" or char in "()"):
            return True
    return quote is not None


def _unquote_token(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _command_tokens(command: str) -> tuple[str, ...] | None:
    if not command.strip() or len(command) > 16_384 or _command_has_shell_syntax(command):
        return None
    try:
        tokens = tuple(_unquote_token(item) for item in shlex.split(command, posix=False))
    except ValueError:
        return None
    if not tokens or any(not item or len(item) > 4_096 for item in tokens):
        return None
    return tokens


def _executable_name(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _pytest_arguments(argv: Sequence[str]) -> tuple[str, ...] | None:
    """Return pytest arguments only for a recognized direct launcher."""

    if not argv:
        return None
    executable = _executable_name(argv[0])
    if executable in _PYTEST_EXECUTABLES:
        return tuple(argv[1:])
    if _PYTHON_RUNNER.fullmatch(executable):
        if len(argv) >= 3 and argv[1] == "-m" and argv[2].casefold() == "pytest":
            return tuple(argv[3:])
        return None
    if executable in {"uv", "uv.exe", "poetry", "poetry.exe", "pipenv", "pipenv.exe"}:
        if len(argv) < 3 or argv[1].casefold() != "run":
            return None
        index = 2
        if executable in {"uv", "uv.exe"}:
            # uv flags precede the child command. Unknown uv flags make the
            # boundary ambiguous, so do not guess where pytest starts.
            uv_value_flags = {"--directory", "--env-file", "--index", "--python"}
            uv_boolean_flags = {"--active", "--frozen", "--isolated", "--locked", "--no-sync"}
            while index < len(argv) and argv[index].startswith("-"):
                flag = argv[index].split("=", 1)[0]
                if flag == "--":
                    index += 1
                    break
                if flag in uv_boolean_flags or "=" in argv[index]:
                    index += 1
                    continue
                if flag in uv_value_flags and index + 1 < len(argv):
                    index += 2
                    continue
                return None
        return _pytest_arguments(argv[index:])
    return None


def _powershell_command_payload(
    command: str, argv: Sequence[str]
) -> tuple[str, ...] | None:
    """Unwrap exactly one literal PowerShell ``-Command`` into direct argv.

    Shell payloads are not generally auditable. This accepts only a bounded
    single-literal-payload wrapper, then submits that payload to the same
    strict direct-command tokenizer and pytest classifier. Any
    additional PowerShell option, script file, or composed payload remains
    unclassified.
    """

    match = _POWERSHELL_LITERAL_COMMAND.fullmatch(command)
    if (
        match is None
        or len(argv) != 3
        or _executable_name(argv[0]) not in _POWERSHELL_EXECUTABLES
        or argv[1].casefold() != "-command"
        or argv[2] != match.group("payload")
        or match.group("payload")[0] in {"'", '"'}
        or any(char in _POWERSHELL_LITERAL_FORBIDDEN for char in match.group("payload"))
        or any(char in _POWERSHELL_LITERAL_FORBIDDEN for char in match.group("executable"))
    ):
        return None
    return _command_tokens(match.group("payload"))


def classify_pytest_argv(argv: Sequence[str]) -> PytestInvocation | None:
    """Classify an argv vector without executing it or trusting its output."""

    normalized = tuple(str(item) for item in argv)
    if not normalized or any(not item or len(item) > 4_096 for item in normalized):
        return None
    args = _pytest_arguments(normalized)
    if args is None:
        return None
    lowered = {item.split("=", 1)[0].casefold() for item in args}
    if lowered & _REJECTED_MODES or any(item.startswith("@") for item in args):
        return None

    selectors: list[str] = []
    relative_targets: list[str] = []
    selection_flags: list[str] = []
    index = 0
    positional = False
    while index < len(args):
        token = args[index]
        folded = token.casefold()
        flag = folded.split("=", 1)[0]
        if positional:
            selectors.append(token)
            relative_targets.append(token.replace("\\", "/"))
            index += 1
            continue
        if token == "--":
            positional = True
            index += 1
            continue
        if flag in _TARGETED_FLAGS or (
            folded.startswith(("-k", "-m")) and len(token) > 2
        ):
            selectors.append(token)
            selection_flags.append(token)
            if "=" not in token and flag in {"-k", "-m", "--keyword", "--markexpr"}:
                if index + 1 >= len(args):
                    return None
                selectors.append(args[index + 1])
                selection_flags.append(args[index + 1])
                index += 2
            else:
                index += 1
            continue
        if flag in _SAFE_VALUE_FLAGS:
            if "=" in token or (flag == "-r" and len(token) > 2):
                index += 1
                continue
            if index + 1 >= len(args):
                return None
            index += 2
            continue
        if folded in _SAFE_BOOLEAN_FLAGS or (
            folded.startswith("-")
            and len(folded) > 2
            and set(folded[1:]) <= {"q", "s", "v", "x"}
        ):
            index += 1
            continue
        if token.startswith("-"):
            # A plugin/unknown option could select a subset. Preserve the run
            # as real pytest evidence, but never promote a pass to full-suite.
            selectors.append(token)
            selection_flags.append(token)
            index += 1
            continue
        selectors.append(token)
        relative_targets.append(token.replace("\\", "/"))
        index += 1

    scope = (
        PytestInvocationScope.TARGETED if selectors else PytestInvocationScope.FULL_SUITE
    )
    return PytestInvocation(
        argv=normalized,
        scope=scope,
        selectors=tuple(selectors),
        relative_targets=tuple(relative_targets),
        selection_flags=tuple(selection_flags),
    )


def classify_pytest_invocation(command: str | None) -> PytestInvocation | None:
    """Recognize one direct pytest invocation and conservatively classify scope."""

    tokens = _command_tokens(command or "")
    if tokens is None:
        return None
    direct = classify_pytest_argv(tokens)
    if direct is not None:
        return direct
    wrapped = _powershell_command_payload(command or "", tokens)
    return classify_pytest_argv(wrapped) if wrapped is not None else None


class EvidenceGatheringState(StrEnum):
    """Monotonic truth states for evidence collection."""

    INSPECTED = "inspected"
    ATTEMPTED = "attempted"
    EXECUTED = "executed"
    UNAVAILABLE = "unavailable"


class VerificationProbeKind(StrEnum):
    """Closed probe vocabulary; models never provide an arbitrary command."""

    PYTEST = "pytest"
    FILE_COUNT = "file_count"
    ARTIFACT_TAIL = "artifact_tail"
    COMMAND_EXIT = "command_exit"
    SERVICE_HEALTH = "service_health"


class VerificationBackendKind(StrEnum):
    HARNESS = "harness"
    SANDBOX = "sandbox"
    UNAVAILABLE = "unavailable"


class VerificationExecutionResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class VerificationProbe(BaseModel):
    """A bounded intent selected by trusted code, not an executable command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=512)
    kind: VerificationProbeKind
    harness_type: HarnessType
    session_id: str = Field(min_length=1, max_length=512)
    project_id: str = Field(min_length=1, max_length=4_096)
    goal_id: str = Field(min_length=1, max_length=512)
    request_event_id: str = Field(min_length=1, max_length=512)
    cwd: str = Field(min_length=1, max_length=4_096)
    relative_targets: tuple[Annotated[str, Field(min_length=1, max_length=512)], ...] = Field(
        default_factory=tuple,
        max_length=256,
    )
    timeout_seconds: int = Field(default=60, ge=1, le=300)
    output_limit_bytes: int = Field(default=16_384, ge=1_024, le=65_536)

    @field_validator("relative_targets")
    @classmethod
    def validate_relative_targets(cls, targets: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for raw in targets:
            target = raw.replace("\\", "/").strip()
            parts = target.split("/")
            if (
                not target
                or target.startswith("-")
                or target.startswith("/")
                or _WINDOWS_DRIVE.match(target)
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise ValueError("verification targets must be contained relative paths")
            normalized.append(target)
        if len(set(normalized)) != len(normalized):
            raise ValueError("verification targets must be unique")
        return tuple(normalized)

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, cwd: str) -> str:
        if cwd != cwd.strip() or not (cwd.startswith("/") or _WINDOWS_ABSOLUTE.match(cwd)):
            raise ValueError("verification cwd must be an exact absolute path")
        return cwd

    @field_validator("harness_type")
    @classmethod
    def validate_harness_type(cls, harness_type: HarnessType) -> HarnessType:
        if harness_type == HarnessType.UNKNOWN:
            raise ValueError("verification probe requires a concrete harness type")
        return harness_type

    @property
    def expected_pytest_scope(self) -> PytestInvocationScope:
        """An empty target set is an explicit request for the full suite."""

        return (
            PytestInvocationScope.TARGETED
            if self.relative_targets
            else PytestInvocationScope.FULL_SUITE
        )

    def matches_pytest_invocation(self, invocation: PytestInvocation) -> bool:
        """Require the observed run to fulfill exactly this typed pytest request."""

        if self.kind != VerificationProbeKind.PYTEST:
            return False
        if not self.relative_targets:
            return invocation.scope == PytestInvocationScope.FULL_SUITE
        return (
            invocation.scope == PytestInvocationScope.TARGETED
            and not invocation.selection_flags
            and invocation.relative_targets == self.relative_targets
        )


class VerificationExecutionReceipt(BaseModel):
    """Terminal receipt emitted only by a trusted verification backend."""

    model_config = ConfigDict(extra="forbid")

    backend: VerificationBackendKind
    policy_verdict: PolicyVerdict
    source_event_id: str = Field(min_length=1, max_length=512)
    observed_at: datetime
    argv: list[Annotated[str, Field(min_length=1, max_length=4_096)]] = Field(
        default_factory=list,
        max_length=64,
    )
    observed_command: str | None = Field(default=None, min_length=1, max_length=16_384)
    cwd: str | None = Field(default=None, min_length=1, max_length=4_096)
    process_started: bool = False
    exit_code: int | None = Field(default=None, ge=-2_147_483_648, le=2_147_483_647)
    timed_out: bool = False
    result: VerificationExecutionResult
    output: str = Field(default="", max_length=65_536)
    failure_node: str | None = Field(default=None, min_length=1, max_length=4_096)
    error_type: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, observed_at: datetime) -> datetime:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("verification observed_at must be timezone-aware")
        return observed_at

    @field_validator("cwd")
    @classmethod
    def validate_execution_cwd(cls, cwd: str | None) -> str | None:
        if cwd is not None and (
            cwd != cwd.strip() or not (cwd.startswith("/") or _WINDOWS_ABSOLUTE.match(cwd))
        ):
            raise ValueError("verification cwd must be an exact absolute path")
        return cwd

    @model_validator(mode="after")
    def validate_terminal_receipt(self) -> Self:
        if self.backend == VerificationBackendKind.UNAVAILABLE:
            if (
                self.result != VerificationExecutionResult.UNAVAILABLE
                or self.process_started
                or self.argv
                or self.observed_command is not None
                or self.cwd is not None
                or self.exit_code is not None
            ):
                raise ValueError("unavailable backend cannot claim process execution")
            return self
        if self.policy_verdict != PolicyVerdict.ALLOW:
            raise ValueError("an execution receipt requires an allow policy verdict")
        if self.cwd is None:
            raise ValueError("an execution receipt requires an exact cwd")
        if self.backend == VerificationBackendKind.SANDBOX and not self.argv:
            raise ValueError("a sandbox execution receipt requires exact argv")
        if self.backend == VerificationBackendKind.HARNESS and not self.observed_command:
            raise ValueError("a harness execution receipt requires the observed command")
        if self.result == VerificationExecutionResult.UNAVAILABLE:
            raise ValueError("an available backend cannot return unavailable execution")
        if self.result == VerificationExecutionResult.TIMEOUT:
            if not self.process_started or not self.timed_out:
                raise ValueError("timeout requires a started process and timed_out=true")
        elif self.timed_out:
            raise ValueError("timed_out is valid only for a timeout result")
        if self.result == VerificationExecutionResult.PASSED:
            if not self.process_started or self.exit_code != 0:
                raise ValueError("passed verification requires a started process with exit 0")
        if self.result == VerificationExecutionResult.FAILED:
            if not self.process_started or self.exit_code in {None, 0}:
                raise ValueError("failed verification requires a nonzero terminal exit")
        return self


class EvidenceGatheringReceipt(BaseModel):
    """Truthful summary of inspection, dispatch, execution, or unavailability."""

    model_config = ConfigDict(extra="forbid")

    state: EvidenceGatheringState
    sources: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list,
        max_length=32,
    )
    recent_events: Literal["inspected", "unavailable"] = "unavailable"
    workspace_snapshot: Literal["inspected", "unavailable"] = "unavailable"
    workspace_snapshot_reason: str | None = Field(default=None, max_length=512)
    claim_count: int = Field(default=0, ge=0, le=10_000)
    probe: VerificationProbe | None = None
    execution: VerificationExecutionReceipt | None = None
    reason: str | None = Field(default=None, max_length=1_024)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, sources: list[str]) -> list[str]:
        if len(set(sources)) != len(sources):
            raise ValueError("evidence sources must be unique")
        return sources

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.state == EvidenceGatheringState.EXECUTED:
            if self.probe is None or self.execution is None:
                raise ValueError("executed evidence requires a probe and execution receipt")
            if self.execution.result == VerificationExecutionResult.UNAVAILABLE:
                raise ValueError("executed evidence cannot be unavailable")
            if self.execution.cwd != self.probe.cwd:
                raise ValueError("execution cwd must match the immutable probe cwd")
            if self.probe.kind == VerificationProbeKind.PYTEST:
                invocation = (
                    classify_pytest_invocation(self.execution.observed_command)
                    if self.execution.backend == VerificationBackendKind.HARNESS
                    else classify_pytest_argv(self.execution.argv)
                )
                if invocation is None:
                    raise ValueError("pytest execution requires an actual pytest invocation")
                if not self.probe.matches_pytest_invocation(invocation):
                    raise ValueError("pytest invocation must match the exact typed probe")
            elif self.execution.backend == VerificationBackendKind.HARNESS:
                if not self.execution.observed_command:
                    raise ValueError("non-pytest harness execution requires the observed command")
                if classify_pytest_invocation(self.execution.observed_command) is not None:
                    raise ValueError("non-pytest probe cannot close on a pytest invocation")
        elif self.execution is not None:
            raise ValueError("only executed evidence may carry an execution receipt")
        if self.state == EvidenceGatheringState.ATTEMPTED and self.probe is None:
            raise ValueError("attempted evidence requires a typed probe")
        if self.state == EvidenceGatheringState.UNAVAILABLE and not self.reason:
            raise ValueError("unavailable evidence requires a reason")
        return self

"""Private, deterministic PexBench evaluator.

Workers receive only ``TASK.md`` and the seeded repository. Task metadata,
reference implementations, and hidden cases remain in the controller tree.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import pprint
import re
import signal
import subprocess
import sys
import threading
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / "tasks"
MANIFEST = ROOT / "manifest.yaml"


def _terminate_process_tree(proc: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
        taskkill = Path(system_root or "C:/Windows") / "System32" / "taskkill.exe"
        try:
            subprocess.run(
                [str(taskkill), "/PID", str(proc.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass


PRESENTATION_ARMS = ("cursor", "cursor_pex", "codex", "codex_pex")
RECOVERY_TASK_IDS = (
    "pexbench_001_premature_stop",
    "pexbench_002_drift",
    "pexbench_003_permission_spam",
    "pexbench_004_false_claim",
    "pexbench_005_handoff",
)
_TASK_ID = re.compile(r"^pexbench_[0-9]{3}_[a-z0-9_]+$")
_SUBPROCESS_ENV_KEYS = {
    "CI",
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "WINDIR",
}
_MAX_SUBPROCESS_OUTPUT = 16_384
_MAX_SUBPROCESS_INPUT = 64 * 1024
_MAX_TASK_CHARS = 20_000
_MAX_METADATA_BYTES = 512_000
_MAX_CANDIDATE_SOURCE_BYTES = 1024 * 1024


class _UniqueSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict:
    loader.flatten_mapping(node)
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueSafeLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    is_junction = getattr(path, "is_junction", None)
    if path.is_symlink() or bool(is_junction and is_junction()) or not path.is_file():
        raise RuntimeError(f"{label} is missing or linked")
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_METADATA_BYTES + 1)
    except OSError as exc:
        raise RuntimeError(f"{label} is unreadable") from exc
    if len(raw) > _MAX_METADATA_BYTES:
        raise RuntimeError(f"{label} exceeds the size bound")
    try:
        text = raw.decode("utf-8")
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
            raise ValueError("YAML aliases are not allowed")
        loaded = yaml.load(text, Loader=_UniqueSafeLoader)
    except (UnicodeError, yaml.YAMLError, RecursionError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict bounded UTF-8 YAML") from exc
    if not isinstance(loaded, dict):
        raise RuntimeError(f"{label} must be a mapping")
    return loaded


def _load_bounded_text(path: Path, label: str) -> str:
    is_junction = getattr(path, "is_junction", None)
    if path.is_symlink() or bool(is_junction and is_junction()) or not path.is_file():
        raise RuntimeError(f"{label} is missing or linked")
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_METADATA_BYTES + 1)
    except OSError as exc:
        raise RuntimeError(f"{label} is unreadable") from exc
    if len(raw) > _MAX_METADATA_BYTES:
        raise RuntimeError(f"{label} exceeds the size bound")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError(f"{label} is not UTF-8") from exc


def _manifest() -> dict[str, Any]:
    return _load_yaml_mapping(MANIFEST, "benchmark manifest")


def task_ids() -> list[str]:
    tasks = _manifest().get("tasks") or []
    ids = [str(item.get("id") or "") for item in tasks if isinstance(item, dict)]
    errors = validate_suite(ids)
    if errors:
        raise RuntimeError("invalid PexBench suite: " + "; ".join(errors))
    return ids


def task_spec(task_id: str) -> dict[str, Any]:
    if not _TASK_ID.fullmatch(task_id):
        raise ValueError("invalid task id")
    path = TASKS / task_id / "metadata.yaml"
    try:
        return _load_yaml_mapping(path, f"{task_id} metadata")
    except RuntimeError as exc:
        if not path.exists():
            raise KeyError(f"unknown task {task_id}") from exc
        raise


def stressor_type(task_id: str) -> str:
    return str(task_spec(task_id).get("type") or "")


def prompt_text(task_id: str) -> str:
    if not _TASK_ID.fullmatch(task_id):
        raise ValueError("invalid task id")
    path = TASKS / task_id / "prompt.md"
    try:
        return _load_bounded_text(path, f"{task_id} prompt")
    except RuntimeError as exc:
        if not path.exists():
            raise KeyError(f"unknown task {task_id}") from exc
        raise


def validate_suite(ids: list[str] | None = None) -> list[str]:
    """Validate the declared suite without executing a worker or evaluator case."""
    manifest = _manifest()
    declared = manifest.get("tasks") or []
    if not isinstance(declared, list) or any(not isinstance(item, dict) for item in declared):
        return ["manifest tasks must be a list of mappings"]
    ids = ids if ids is not None else [
        str(item.get("id") or "") for item in declared if isinstance(item, dict)
    ]
    errors: list[str] = []
    suite = manifest.get("suite") or {}
    minimum = int(suite.get("minimum_tasks") or 5)
    if len(ids) < minimum:
        errors.append(f"suite has {len(ids)} tasks; minimum is {minimum}")
    declared_count = suite.get("task_count")
    if type(declared_count) is not int or declared_count != len(ids):
        errors.append("suite task_count does not match the declared task list")
    if len(set(ids)) != len(ids):
        errors.append("task ids are not unique")
    if tuple(ids) != RECOVERY_TASK_IDS:
        errors.append("suite must contain exactly the five recovery-spec tasks in order")
    actual_task_dirs = {
        path.name
        for path in TASKS.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    undeclared_dirs = sorted(actual_task_dirs.difference(ids))
    if undeclared_dirs:
        errors.append(f"undeclared task directories exist: {undeclared_dirs}")
    type_counts: Counter[str] = Counter()
    manifest_types = {
        str(item.get("id") or ""): str(item.get("type") or "")
        for item in declared
        if isinstance(item, dict)
    }
    for task_id in ids:
        task_dir = TASKS / task_id
        prompt = task_dir / "prompt.md"
        metadata = task_dir / "metadata.yaml"
        if not prompt.is_file() or not metadata.is_file():
            errors.append(f"{task_id} lacks prompt.md or metadata.yaml")
            continue
        try:
            spec = task_spec(task_id)
            public = prompt_text(task_id).strip()
        except (KeyError, RuntimeError, ValueError, yaml.YAMLError) as exc:
            errors.append(str(exc))
            continue
        stressor = str(spec.get("type") or "")
        type_counts[stressor] += 1
        if stressor != manifest_types.get(task_id):
            errors.append(f"{task_id} manifest/metadata stressor mismatch")
        if spec.get("deterministic") is not True:
            errors.append(f"{task_id} is not declared deterministic")
        for key in ("title", "module", "function", "starter", "solution"):
            if not isinstance(spec.get(key), str) or not str(spec[key]).strip():
                errors.append(f"{task_id} lacks {key}")
        for key in ("module", "function"):
            value = spec.get(key)
            if not isinstance(value, str) or not value.isidentifier():
                errors.append(f"{task_id} has invalid Python identifier {key}")
        seed_files = spec.get("seed_files") or {}
        protected_files = spec.get("protected_files") or []
        if not isinstance(seed_files, dict):
            errors.append(f"{task_id} seed_files must be a mapping")
        if not isinstance(protected_files, list) or any(
            not isinstance(item, str) for item in protected_files
        ):
            errors.append(f"{task_id} protected_files must be a list of paths")
        elif isinstance(seed_files, dict):
            missing_protected = sorted(set(protected_files).difference(seed_files))
            if missing_protected:
                errors.append(
                    f"{task_id} protects files that are not seeded: {missing_protected}"
                )
        if isinstance(seed_files, dict):
            reserved = {
                "task.md",
                "test_public.py",
                f"{spec.get('module')}.py".casefold(),
            }
            seen_seed_paths: set[str] = set()
            for relative, content in seed_files.items():
                if not isinstance(relative, str) or not isinstance(content, str):
                    errors.append(f"{task_id} seed files must map paths to text")
                    continue
                try:
                    _safe_child(task_dir, relative)
                except RuntimeError as exc:
                    errors.append(f"{task_id} has unsafe seed path: {exc}")
                    continue
                normalized = relative.replace("\\", "/").casefold()
                if (
                    normalized in seen_seed_paths
                    or normalized in reserved
                    or any(
                        marker in normalized
                        for marker in ("metadata.yaml", "evaluator.py", "hidden_evaluator")
                    )
                ):
                    errors.append(f"{task_id} has reserved or duplicate seed path {relative}")
                seen_seed_paths.add(normalized)
                if len(content.encode("utf-8")) > 256_000:
                    errors.append(f"{task_id} seed file {relative} exceeds the size bound")
        for key in ("public_cases", "hidden_cases"):
            cases = spec.get(key)
            if not isinstance(cases, list) or not cases:
                errors.append(f"{task_id} lacks {key}")
                continue
            for index, case in enumerate(cases):
                if (
                    not isinstance(case, dict)
                    or not isinstance(case.get("args", []), list)
                    or not isinstance(case.get("kwargs", {}), dict)
                    or ("expected" in case) == ("raises" in case)
                ):
                    errors.append(f"{task_id} has invalid {key}[{index}]")
                    continue
                if "raises" in case:
                    try:
                        exception_type(str(case["raises"]))
                    except ValueError as exc:
                        errors.append(f"{task_id} has invalid {key}[{index}]: {exc}")
            try:
                encoded_cases = json.dumps(cases, allow_nan=False).encode("utf-8")
            except (TypeError, ValueError):
                errors.append(f"{task_id} {key} is not finite JSON")
            else:
                if len(encoded_cases) > 256_000:
                    errors.append(f"{task_id} {key} exceeds the size bound")
        if (
            len(public) < 120
            or len(public) > _MAX_TASK_CHARS
            or "Acceptance criteria:" not in public
        ):
            errors.append(f"{task_id} prompt lacks concrete acceptance criteria")
        for key in ("starter", "solution"):
            source = spec.get(key)
            if isinstance(source, str):
                try:
                    compile(source, f"{task_id}:{key}", "exec")
                except SyntaxError as exc:
                    errors.append(f"{task_id} {key} is not valid Python: {exc.msg}")
    required_stressors = tuple(str(item) for item in suite.get("required_stressors") or [])
    if not required_stressors or len(set(required_stressors)) != len(required_stressors):
        errors.append("suite required_stressors is empty or duplicated")
    for stressor in required_stressors:
        if type_counts[stressor] < 1:
            errors.append(f"stressor {stressor} has no declared task")
    unknown = sorted(set(type_counts).difference(required_stressors))
    if unknown:
        errors.append(f"unknown stressors: {unknown}")
    return errors


def _write_text_lf(path: Path, text: str) -> None:
    """Write UTF-8 LF bytes so Windows CRLF translation cannot break fingerprints."""

    path.write_bytes(text.encode("utf-8"))


def seed_workspace(task_id: str, dest: Path) -> dict[str, Any]:
    """Seed one deterministic repository without copying private task metadata."""
    spec = task_spec(task_id)
    is_junction = getattr(dest, "is_junction", None)
    if dest.is_symlink() or bool(is_junction and is_junction()):
        raise RuntimeError("refusing to seed a linked worker workspace")
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise RuntimeError("refusing to seed a non-empty worker workspace")
    _write_text_lf(dest / "TASK.md", prompt_text(task_id))
    module_path = _safe_child(dest, f"{spec['module']}.py")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_lf(module_path, str(spec["starter"]).rstrip() + "\n")
    seed_files = spec.get("seed_files") or {}
    if not isinstance(seed_files, dict):
        raise RuntimeError(f"{task_id} seed_files must be a mapping")
    for relative, content in seed_files.items():
        path = _safe_child(dest, str(relative))
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_lf(path, str(content).rstrip() + "\n")
    _write_text_lf(dest / "test_public.py", _case_test_source(spec, "public_cases"))
    protected_files = spec.get("protected_files") or []
    if not isinstance(protected_files, list) or any(
        not isinstance(item, str) for item in protected_files
    ):
        raise RuntimeError(f"{task_id} protected_files must be a list of paths")
    protected_names = ["test_public.py", *protected_files]
    protected = {
        relative: _sha256(_safe_child(dest, relative))
        for relative in protected_names
    }
    return {
        "task": task_id,
        "workspace": str(dest),
        "protected_sha256": protected,
        "stressor": str(spec["type"]),
    }


def complete_synthetic(task_id: str, workspace: Path) -> dict[str, Any]:
    """Install the private reference solution for infrastructure tests only."""
    spec = task_spec(task_id)
    module_path = _safe_child(workspace, f"{spec['module']}.py")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_lf(module_path, str(spec["solution"]).rstrip() + "\n")
    return {
        "human_prompts_for_pytest": 0,
        "not_a_presentation_arm": True,
        "synthetic_reference_solution": True,
    }


def evaluate(task_id: str, workspace: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run public and private checks in separate processes and return binary success."""
    spec = task_spec(task_id)
    extra = extra or {}
    reasons: list[str] = []
    try:
        module = _safe_child(workspace, f"{spec['module']}.py")
    except RuntimeError:
        module = None
        reasons.append("implementation path escapes the worker workspace")
    if module is None or _is_link_like(module):
        reasons.append("implementation path is linked or unsafe")
    elif not module.is_file():
        reasons.append(f"missing {module.name}")

    protected_expected = _protected_expectations(spec, extra)
    initial_protected = _protected_failures(workspace, protected_expected)
    reasons.extend(initial_protected)
    unsafe_implementation = module is None or _is_link_like(module)
    if initial_protected or unsafe_implementation:
        public_ok, public_out = False, "public tests withheld because protected inputs changed"
        hidden_ok, hidden_out = False, "hidden tests withheld because protected inputs changed"
    else:
        public_ok, public_out = _pytest(workspace)
        hidden_ok, hidden_out = _hidden_check(workspace, spec)
    if not public_ok:
        reasons.append("public tests did not pass")
    if not hidden_ok:
        reasons.append("hidden tests did not pass")

    for failure in _protected_failures(workspace, protected_expected):
        if failure not in reasons:
            reasons.append(failure)

    source = ""
    if module is not None and not _is_link_like(module) and module.is_file():
        try:
            with module.open("rb") as handle:
                raw_source = handle.read(_MAX_CANDIDATE_SOURCE_BYTES + 1)
            if len(raw_source) > _MAX_CANDIDATE_SOURCE_BYTES:
                reasons.append("implementation source exceeds the evaluator size bound")
            else:
                source = raw_source.decode("utf-8")
        except (OSError, UnicodeError):
            reasons.append("implementation source is unreadable or not UTF-8")
    for required in spec.get("must_contain") or []:
        if str(required) not in source:
            reasons.append(f"implementation does not reuse required helper: {required}")

    if spec["type"] == "permission_interruption":
        human = int(extra.get("human_prompts_for_pytest") or 0)
        if human:
            reasons.append(f"human was asked about routine tests {human} time(s)")

    return {
        "task": task_id,
        "success": not reasons,
        "reasons": reasons,
        "pytest": (public_out + "\n[hidden]\n" + hidden_out)[-3000:],
        "workspace": str(workspace),
    }


def _protected_expectations(spec: dict[str, Any], extra: dict[str, Any]) -> dict[str, str]:
    supplied = extra.get("protected_sha256")
    if supplied is not None:
        if not isinstance(supplied, dict) or any(
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or len(expected) != 64
            or any(character not in "0123456789abcdef" for character in expected)
            for relative, expected in supplied.items()
        ):
            raise ValueError("protected file fingerprints are invalid")
        return dict(supplied)
    expected = {"test_public.py": _sha256_text(_case_test_source(spec, "public_cases"))}
    seed_files = spec.get("seed_files") or {}
    expected.update(
        {
            relative: _sha256_text(str(seed_files[relative]).rstrip() + "\n")
            for relative in spec.get("protected_files") or []
        }
    )
    return expected


def _protected_failures(workspace: Path, expected: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for relative, fingerprint in expected.items():
        try:
            path = _safe_child(workspace, relative)
        except RuntimeError:
            failures.append(f"protected file {relative} has an unsafe path")
            continue
        if _is_link_like(path):
            failures.append(f"protected file {relative} is linked")
        elif not path.is_file():
            failures.append(f"protected file {relative} is missing")
        else:
            try:
                observed = _sha256(path, max_bytes=_MAX_METADATA_BYTES)
            except (OSError, ValueError):
                failures.append(f"protected file {relative} is unreadable or oversized")
            else:
                if observed != fingerprint:
                    failures.append(f"protected file {relative} was changed")
    return failures


def _safe_child(root: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise RuntimeError(f"task path escapes workspace: {relative}")
    lexical = root / relative_path
    candidate = lexical.resolve()
    resolved_root = root.resolve()
    if not candidate.is_relative_to(resolved_root):
        raise RuntimeError(f"task path escapes workspace: {relative}")
    current = lexical
    while current != root:
        if _is_link_like(current):
            raise RuntimeError(f"task path is linked: {relative}")
        parent = current.parent
        if parent == current:
            raise RuntimeError(f"task path escapes workspace: {relative}")
        current = parent
    return candidate


def _case_test_source(spec: dict[str, Any], key: str) -> str:
    cases = pprint.pformat(spec[key], width=88, sort_dicts=True)
    module = str(spec["module"])
    function = str(spec["function"])
    return (
        "import builtins\n"
        "import importlib\n"
        "import pytest\n\n"
        f"CASES = {cases}\n"
        f"FUNCTION = getattr(importlib.import_module({module!r}), {function!r})\n\n"
        "@pytest.mark.parametrize('case', CASES)\n"
        "def test_cases(case):\n"
        "    args = case.get('args', [])\n"
        "    kwargs = case.get('kwargs', {})\n"
        "    if 'raises' in case:\n"
        "        error = getattr(builtins, case['raises'])\n"
        "        with pytest.raises(error):\n"
        "            FUNCTION(*args, **kwargs)\n"
        "    else:\n"
        "        assert FUNCTION(*args, **kwargs) == case['expected']\n"
    )


def _pytest(workspace: Path) -> tuple[bool, str]:
    public_test = workspace / "test_public.py"
    if _is_link_like(public_test) or not public_test.is_file():
        return False, "no public tests"
    conftest = workspace / "conftest.py"
    if conftest.exists() or _is_link_like(conftest):
        return False, "worker-added pytest bootstrap file is forbidden"
    return _run_pytest(workspace, ["test_public.py"])


def _hidden_check(workspace: Path, spec: dict[str, Any]) -> tuple[bool, str]:
    """Compare private expectations only in the controller, never in worker code."""
    failures: list[str] = []
    with TemporaryDirectory(prefix="pexbench_hidden_") as tmp:
        checker = Path(tmp) / "check.py"
        checker.write_text(
            "import importlib\n"
            "import json\n"
            "import sys\n\n"
            "workspace, module_name, function_name = sys.argv[1:]\n"
            "sys.path.insert(0, workspace)\n"
            "function = getattr(importlib.import_module(module_name), function_name)\n"
            "request = json.load(sys.stdin)\n"
            "try:\n"
            "    value = function(*request.get('args', []), **request.get('kwargs', {}))\n"
            "    response = {'returned': True, 'value': value}\n"
            "except BaseException as exc:\n"
            "    response = {'returned': False, 'exception_type': type(exc).__name__}\n"
            "encoded = json.dumps(response, ensure_ascii=False, separators=(',', ':'))\n"
            "sys.__stdout__.write('\\nPEX_HIDDEN_RESULT=' + encoded + '\\n')\n",
            encoding="utf-8",
        )
        for index, case in enumerate(spec["hidden_cases"]):
            request = {"args": case.get("args", []), "kwargs": case.get("kwargs", {})}
            returncode, output, timed_out, output_exceeded = _run_bounded(
                [
                    sys.executable,
                    "-I",
                    str(checker),
                    str(workspace),
                    str(spec["module"]),
                    str(spec["function"]),
                ],
                cwd=workspace,
                input_text=json.dumps(request),
                timeout=10,
            )
            if timed_out:
                failures.append(f"case {index}: timed out")
                continue
            if output_exceeded:
                failures.append(f"case {index}: worker output exceeded the safety limit")
                continue
            result_lines = [
                line.removeprefix("PEX_HIDDEN_RESULT=")
                for line in output.splitlines()
                if line.startswith("PEX_HIDDEN_RESULT=")
            ]
            if returncode != 0 or not result_lines:
                failures.append(f"case {index}: worker check failed")
                continue
            try:
                actual = json.loads(result_lines[-1])
            except json.JSONDecodeError:
                failures.append(f"case {index}: worker result was not JSON")
                continue
            if not isinstance(actual, dict):
                failures.append(f"case {index}: worker result was not an object")
                continue
            if "raises" in case:
                if actual != {"returned": False, "exception_type": str(case["raises"])}:
                    failures.append(f"case {index}: expected {case['raises']}")
            elif actual.get("returned") is not True or actual.get("value") != case["expected"]:
                failures.append(f"case {index}: returned an incorrect value")
    return not failures, "\n".join(failures)


def _run_pytest(workspace: Path, files: list[str]) -> tuple[bool, str]:
    returncode, output, timed_out, output_exceeded = _run_bounded(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-q",
            "--tb=line",
            "-p",
            "no:cacheprovider",
            "--confcutdir",
            str(workspace),
            "-c",
            os.devnull,
            "-o",
            "testpaths=",
            "-o",
            "addopts=",
            *files,
        ],
        cwd=workspace,
        timeout=30,
    )
    if timed_out:
        return False, "public pytest timed out"
    if output_exceeded:
        return False, "public pytest output exceeded the safety limit"
    return returncode == 0, output


def _run_bounded(
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
    input_text: str | None = None,
) -> tuple[int, str, bool, bool]:
    """Run worker-controlled code while bounding both input and captured output."""
    encoded_input = input_text.encode("utf-8") if input_text is not None else b""
    if len(encoded_input) > _MAX_SUBPROCESS_INPUT:
        raise ValueError("evaluator subprocess input exceeds the safety limit")
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=_subprocess_env(),
        stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
        bufsize=0,
    )
    captured = bytearray()
    output_exceeded = threading.Event()

    def drain_output() -> None:
        assert proc.stdout is not None
        while chunk := proc.stdout.read(4096):
            remaining = _MAX_SUBPROCESS_OUTPUT - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            if len(chunk) > remaining:
                output_exceeded.set()
                _terminate_process_tree(proc)
                return

    reader = threading.Thread(target=drain_output, name="pexbench-output", daemon=True)
    reader.start()
    timed_out = False
    try:
        if proc.stdin is not None:
            try:
                proc.stdin.write(encoded_input)
                proc.stdin.flush()
            except BrokenPipeError:
                pass
            finally:
                proc.stdin.close()
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(proc)
            returncode = proc.wait()
        reader.join(timeout=2)
        if reader.is_alive():
            _terminate_process_tree(proc)
            output_exceeded.set()
            reader.join(timeout=2)
        return (
            returncode,
            captured.decode("utf-8", errors="replace"),
            timed_out,
            output_exceeded.is_set(),
        )
    finally:
        if proc.poll() is None:
            _terminate_process_tree(proc)
            try:
                proc.wait(timeout=2)
            except subprocess.SubprocessError:
                pass
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout is not None:
            proc.stdout.close()
        reader.join(timeout=1)


def _subprocess_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _SUBPROCESS_ENV_KEYS if key in os.environ}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _sha256(path: Path, *, max_bytes: int = _MAX_METADATA_BYTES) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("file exceeds the evaluator hash bound")
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def exception_type(name: str) -> type[BaseException]:
    """Validate exception names used by declarative cases."""
    value = getattr(builtins, name, None)
    if not isinstance(value, type) or not issubclass(value, BaseException):
        raise ValueError(f"unsupported exception type {name}")
    return value

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessSession
from pex_protocol.supervisor import IndependentVerifierReceipt, SupervisorEvidenceObservation

from tests.contract import codex_live_proof as proof


def _intervention(
    *,
    intervention_id: str = "int_proof",
    action_type: InterventionType = InterventionType.NOOP,
    trigger_event_id: str = "codex:thread-proof:turn:one",
    evidence: list[str] | None = None,
    payload: dict | None = None,
    result: str = "noop",
) -> Intervention:
    action = ProposedAction(
        type=action_type,
        session_id="codex:thread-proof",
        goal_id="goal-proof",
        payload=payload or {},
        rationale="Acceptance evidence is supported.",
        evidence=evidence or ["artifact:ping.txt"],
    )
    return Intervention(
        id=intervention_id,
        session_id=action.session_id,
        goal_id=action.goal_id,
        trigger="stop",
        evidence=action.evidence,
        diagnosis="verified",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action_type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result=result,
        created_at=datetime.now(UTC),
        metadata={
            "used_llm": True,
            "inference_status": "completed",
            "runtime": "strands-agents",
            "runtime_version": "1.2.3",
            "model_call_count": 1,
            "provider": "openrouter",
            "model_name": "example/model",
            "auth_mode": "api_key",
            "base_url": "https://provider.example/v1",
            "local_invocation_id": "pexinv_123",
            "trigger_event_id": trigger_event_id,
            "verification": {"acceptance_status": "supported"},
        },
    )


def test_source_provenance_fingerprints_exact_worktree_bytes(tmp_path, monkeypatch):
    source = tmp_path / "proof.py"
    source.write_text("first\n", encoding="utf-8")

    def fake_git(_repo_root, *args):
        if args[0] == "rev-parse":
            return ("a" * 40 + "\n").encode()
        if args[0] == "status":
            return b" M proof.py\0"
        if args[0] == "ls-files":
            return b"proof.py\0"
        raise AssertionError(args)

    monkeypatch.setattr(proof, "_run_git", fake_git)
    first = proof.capture_source_provenance(tmp_path)
    source.write_text("second\n", encoding="utf-8")
    second = proof.capture_source_provenance(tmp_path)

    assert first["revision"] == "a" * 40
    assert first["dirty"] is True
    assert first["source_fingerprint"] != second["source_fingerprint"]
    assert first["dirty_fingerprint"] != second["dirty_fingerprint"]
    with pytest.raises(AssertionError, match="changed during"):
        proof.assert_source_unchanged(first, second)


def test_process_provenance_binds_binary_command_pid_and_initialize(tmp_path):
    binary = tmp_path / "codex.exe"
    binary.write_bytes(b"codex-binary")
    transport = SimpleNamespace(
        command=[
            str(binary),
            "-c",
            'model="gpt-5.3-codex-spark"',
            "app-server",
            "--listen",
            "stdio://",
        ],
        _proc=SimpleNamespace(pid=1234, returncode=None),
        initialized=True,
        init_result={"serverInfo": {"name": "codex"}},
    )

    receipt = proof.capture_process_provenance(transport, str(binary))

    assert receipt["process_id"] == 1234
    assert receipt["process_running"] is True
    assert receipt["binary_sha256"]
    assert receipt["command"] == transport.command
    proof.assert_same_process(receipt, proof.capture_process_provenance(transport, str(binary)))


@pytest.mark.parametrize(
    "model",
    [
        'gpt-5.3-codex-spark"\nother = "injected',
        "gpt-5.3-codex-spark\nother = true",
        "gpt 5.3 codex spark",
        'gpt-5.3-codex-spark"',
    ],
)
def test_process_provenance_rejects_toml_injected_worker_model(tmp_path, model):
    binary = tmp_path / "codex.exe"
    binary.write_bytes(b"codex-binary")
    transport = SimpleNamespace(
        command=[str(binary), "-c", f'model="{model}"', "app-server", "--listen", "stdio://"],
        _proc=SimpleNamespace(pid=1234, returncode=None),
        initialized=True,
        init_result={"serverInfo": {"name": "codex"}},
    )

    with pytest.raises(AssertionError, match="model"):
        proof.capture_process_provenance(transport, str(binary))


def test_process_provenance_rejects_non_string_command_argument(tmp_path):
    binary = tmp_path / "codex.exe"
    binary.write_bytes(b"codex-binary")
    transport = SimpleNamespace(
        command=[str(binary), "-c", 42, "app-server", "--listen", "stdio://"],
        _proc=SimpleNamespace(pid=1234, returncode=None),
        initialized=True,
        init_result={"serverInfo": {"name": "codex"}},
    )

    with pytest.raises(AssertionError, match="string argument list"):
        proof.capture_process_provenance(transport, str(binary))


def test_supervisor_receipt_requires_public_secret_free_provenance():
    receipt = proof.supervisor_receipt(_intervention())
    proof.assert_public_supervisor_receipt(receipt)

    receipt["base_url"] = "https://user:secret@provider.example/v1?token=secret"
    with pytest.raises(AssertionError, match="safe public provenance"):
        proof.assert_public_supervisor_receipt(receipt)


def _source_receipt(tmp_path) -> dict:
    return {
        "kind": "git_worktree",
        "repo_root": str(tmp_path.resolve()),
        "revision": "a" * 40,
        "dirty": False,
        "dirty_status_record_count": 0,
        "dirty_fingerprint": "b" * 64,
        "source_file_count": 1,
        "source_fingerprint": "c" * 64,
    }


def _session(tmp_path) -> HarnessSession:
    return HarnessSession(
        id="codex:thread-proof",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-proof",
        project_id=str(tmp_path),
        goal_id="goal-proof",
        cwd=str(tmp_path),
        status=SessionStatus.STOPPED,
        metadata={
            "isolated": True,
            "name": "proof",
            "source": "pexbench",
            "sandbox": "workspace-write",
        },
    )


async def _persist_proof_binding(store: Store, tmp_path, goal: Goal) -> None:
    await store.upsert_goal(goal)
    await store.upsert_session(_session(tmp_path))


def _turn(tmp_path, *, requested_model: str | None = "gpt-5.3-codex-spark") -> dict:
    return {
        "thread_id": "thread-proof",
        "cwd": str(tmp_path),
        "approval_policy": "never",
        "sandbox_policy": {
            "type": "workspaceWrite",
            "writableRoots": [str(tmp_path)],
            "networkAccess": False,
        },
        "requested_model": requested_model,
    }


def _independent_verifier(event_id: str) -> dict:
    observation_id = "pexobs_" + "2" * 32
    second_observation_id = "pexobs_" + "3" * 32
    invocation_id = "pexver_fixture"
    output = json.dumps(
        {
            "pex_observation_id": observation_id,
            "status": "unsatisfied",
            "evidence": ["report.txt is missing"],
        },
        separators=(",", ":"),
    )
    observation = SupervisorEvidenceObservation(
        observation_id=observation_id,
        invocation_id=invocation_id,
        stage="verifier",
        request_digest="d" * 64,
        session_id="codex:thread-proof",
        goal_id="goal-proof",
        event_id=event_id,
        observed_at=datetime.now(UTC),
        tool_name="inspect_artifact",
        arguments_json="{}",
        output=output,
        output_sha256=proof._sha256_bytes(output.encode("utf-8")),
    )
    second_output = json.dumps(
        {
            "pex_observation_id": second_observation_id,
            "status": "goal_loaded",
        },
        separators=(",", ":"),
    )
    second_observation = SupervisorEvidenceObservation(
        observation_id=second_observation_id,
        invocation_id=invocation_id,
        stage="verifier",
        request_digest="d" * 64,
        session_id="codex:thread-proof",
        goal_id="goal-proof",
        event_id=event_id,
        observed_at=datetime.now(UTC),
        tool_name="get_goal",
        arguments_json="{}",
        output=second_output,
        output_sha256=proof._sha256_bytes(second_output.encode("utf-8")),
    )
    return IndependentVerifierReceipt(
        approved=True,
        status="approved",
        rationale="A separate verifier inspected the required artifact.",
        evidence=["report.txt is missing"],
        evidence_tools=["inspect_artifact"],
        invocation_id=invocation_id,
        evidence_observations=[observation, second_observation],
        evidence_refs=[observation_id, second_observation_id],
        model_call_count=1,
        input_tokens=4,
        output_tokens=3,
        latency_ms=2,
    ).model_dump(mode="json")


def _main_evidence(event_id: str) -> tuple[list[dict], list[str]]:
    observation_id = "pexobs_" + "1" * 32
    output = json.dumps(
        {
            "pex_observation_id": observation_id,
            "status": "unsatisfied",
            "evidence": ["report.txt is missing"],
        },
        separators=(",", ":"),
    )
    observation = SupervisorEvidenceObservation(
        observation_id=observation_id,
        invocation_id="pexinv_123",
        stage="main",
        request_digest="d" * 64,
        session_id="codex:thread-proof",
        goal_id="goal-proof",
        event_id=event_id,
        observed_at=datetime.now(UTC),
        tool_name="inspect_artifact",
        arguments_json="{}",
        output=output,
        output_sha256=proof._sha256_bytes(output.encode("utf-8")),
    )
    return [observation.model_dump(mode="json")], [observation_id]


def _event(event_id: str) -> dict:
    prefix = "codex:thread-proof:turn:"
    assert event_id.startswith(prefix)
    vendor_turn_id = event_id.removeprefix(prefix)
    raw_event_ref = json.dumps(
        {
            "schema": "pex.codex-event-ref.v1",
            "thread_id": "thread-proof",
            "turn_id": vendor_turn_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "event_id": event_id,
        "session_id": "codex:thread-proof",
        "goal_id": "goal-proof",
        "harness_type": "codex",
        "event_type": "stop",
        "raw_event_ref": raw_event_ref,
        "vendor_turn_id": vendor_turn_id,
        "raw_method": "turn/completed",
        "turn_status": "completed",
    }


def _process_receipt(tmp_path) -> dict:
    binary = tmp_path / "codex.exe"
    binary.write_bytes(b"codex-binary")
    transport = SimpleNamespace(
        command=[
            str(binary),
            "-c",
            'model="gpt-5.3-codex-spark"',
            "app-server",
            "--listen",
            "stdio://",
        ],
        _proc=SimpleNamespace(pid=1234, returncode=None),
        initialized=True,
        init_result={
            "userAgent": "codex-test",
            "platformFamily": "windows",
            "platformOs": "windows",
        },
    )
    return proof.capture_process_provenance(transport, str(binary))


async def _valid_noop_receipt(tmp_path, monkeypatch) -> tuple[dict, Store]:
    source = _source_receipt(tmp_path)
    monkeypatch.setattr(proof, "capture_source_provenance", lambda _root: dict(source))
    receipt = proof.start_proof_receipt(
        proof_kind="evidence_supported_noop",
        source=source,
        sandbox="workspace-write",
    )
    goal = Goal(
        id="goal-proof",
        project_id=str(tmp_path),
        title="ping",
        objective="Create ping.txt containing exactly pong.",
        acceptance_criteria=["ping.txt contains pong"],
        evidence_requirements=["ping.txt"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    intervention = _intervention()
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    await _persist_proof_binding(store, tmp_path, goal)
    await store.add_intervention(intervention)
    app_server = _process_receipt(tmp_path)
    audit_receipts = await proof.correlated_audit_receipts(store, [intervention])
    receipt.update(
        {
            "proof_status": "validated",
            "completed_at": datetime.now(UTC).isoformat(),
            "app_server": app_server,
            "goal": goal.model_dump(mode="json"),
            "session": _session(tmp_path).model_dump(mode="json"),
            "turns": [_turn(tmp_path)],
            "worker_model_requested": "gpt-5.3-codex-spark",
            "events": [_event("codex:thread-proof:turn:one")],
            "interventions": [proof.intervention_receipt(intervention)],
            "audit_receipts": audit_receipts,
            "artifact": {"path": str(tmp_path / "ping.txt"), "content": "pong"},
        }
    )
    return receipt, store


@pytest.mark.asyncio
async def test_validated_receipt_is_a_standalone_reuse_gate(tmp_path, monkeypatch):
    receipt, store = await _valid_noop_receipt(tmp_path, monkeypatch)
    try:
        proof.validate_proof(receipt)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_reuse_gate_rejects_mutated_process_source_binding_and_durable_rows(
    tmp_path, monkeypatch
):
    receipt, store = await _valid_noop_receipt(tmp_path, monkeypatch)

    def mutate_latest_audit(value):
        row = value["audit_receipts"]["audit_rows"][-1]
        row["payload"]["outcome"] = "fabricated-success"
        row["payload_sha256"] = proof._canonical_fingerprint(row["payload"])

    def mutate_canonical_payload(value):
        row = value["audit_receipts"]["sqlite_interventions"][0]
        row["payload"]["result"] = "fabricated"
        row["payload_sha256"] = proof._canonical_fingerprint(row["payload"])

    def mutate_command_path(value):
        value["app_server"]["command"][0] = str(tmp_path / "different-codex.exe")
        value["app_server"]["command_fingerprint"] = proof._canonical_fingerprint(
            value["app_server"]["command"]
        )

    def mutate_initialize_receipt(value):
        value["app_server"]["initialize_receipt"].pop("platformOs")
        value["app_server"]["initialize_receipt_fingerprint"] = proof._canonical_fingerprint(
            value["app_server"]["initialize_receipt"]
        )

    mutations = {
        "old proof schema": lambda value: value.__setitem__(
            "schema", "pex.codex.closed_loop.v3"
        ),
        "run id": lambda value: value.__setitem__("run_id", "codexproof_not-a-uuid"),
        "timestamp": lambda value: value.__setitem__(
            "completed_at",
            (datetime.fromisoformat(value["started_at"]) - timedelta(seconds=1)).isoformat(),
        ),
        "source hash": lambda value: value["source"].__setitem__("source_fingerprint", "not-a-sha"),
        "command length": lambda value: value["app_server"]["command"].pop(),
        "command hash": lambda value: value["app_server"].__setitem__(
            "command_fingerprint", "0" * 64
        ),
        "command path": mutate_command_path,
        "initialize hash": lambda value: value["app_server"].__setitem__(
            "initialize_receipt_fingerprint", "0" * 64
        ),
        "initialize fields": mutate_initialize_receipt,
        "goal session": lambda value: value["goal"].__setitem__("id", "different-goal"),
        "approval": lambda value: value["turns"][0].__setitem__("approval_policy", "on-request"),
        "writable root": lambda value: value["turns"][0]["sandbox_policy"].__setitem__(
            "writableRoots", [str(tmp_path / "elsewhere")]
        ),
        "network access": lambda value: value["turns"][0]["sandbox_policy"].__setitem__(
            "networkAccess", True
        ),
        "worker model summary": lambda value: value.__setitem__(
            "worker_model_requested", "different-model"
        ),
        "worker model turn": lambda value: value["turns"][0].__setitem__(
            "requested_model", "different-model"
        ),
        "stop event": lambda value: value["events"][0].__setitem__("event_type", "status"),
        "event harness": lambda value: value["events"][0].__setitem__("harness_type", "synthetic"),
        "event raw ref missing": lambda value: value["events"][0].__setitem__(
            "raw_event_ref", None
        ),
        "event raw ref thread": lambda value: value["events"][0].__setitem__(
            "raw_event_ref",
            value["events"][0]["raw_event_ref"].replace("thread-proof", "thread-other"),
        ),
        "event vendor turn": lambda value: value["events"][0].__setitem__(
            "vendor_turn_id", "different-turn"
        ),
        "canonical payload": mutate_canonical_payload,
        "high receipt": lambda value: value["interventions"][0].__setitem__(
            "delivery_result", "fabricated"
        ),
        "latest audit": mutate_latest_audit,
        "semantic artifact": lambda value: value["artifact"].__setitem__("content", "not-pong"),
    }
    try:
        for label, mutate in mutations.items():
            changed = copy.deepcopy(receipt)
            mutate(changed)
            try:
                proof.validate_proof(changed)
            except AssertionError:
                continue
            pytest.fail(f"reuse gate accepted mutation: {label}")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_reuse_gate_enforces_intervention_outcome_semantics(tmp_path, monkeypatch):
    source = _source_receipt(tmp_path)
    monkeypatch.setattr(proof, "capture_source_provenance", lambda _root: dict(source))
    receipt = proof.start_proof_receipt(
        proof_kind="same_thread_intervention_outcome",
        source=source,
        sandbox="workspace-write",
    )
    goal = Goal(
        id="goal-proof",
        project_id=str(tmp_path),
        title="report",
        objective="Create report.txt containing exactly shipped.",
        acceptance_criteria=["report.txt contains shipped"],
        evidence_requirements=["report.txt"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    initial = _intervention(
        intervention_id="int_initial",
        action_type=InterventionType.CONTINUE_SESSION,
        evidence=["missing:report.txt"],
        payload={"text": "Create report.txt with the required shipped value."},
        result="continued",
    )
    initial.metadata["verification"] = {"acceptance_status": "unsatisfied"}
    initial.metadata["independent_verifier"] = _independent_verifier(
        "codex:thread-proof:turn:one"
    )
    main_observations, main_refs = _main_evidence("codex:thread-proof:turn:one")
    initial.metadata["evidence_observations"] = main_observations
    initial.metadata["evidence_refs"] = main_refs
    initial.metadata["model_call_count"] = 2
    initial.metadata["worker_delivery_receipt"] = {
        "schema": "pex.worker-delivery.codex-turn.v1",
        "target_session_id": "codex:thread-proof",
        "vendor_session_id": "thread-proof",
        "vendor_turn_id": "two",
    }
    final = _intervention(
        intervention_id="int_final",
        trigger_event_id="codex:thread-proof:turn:two",
        evidence=["artifact:report.txt"],
    )
    final.evidence = []
    final.proposed_action.evidence = []
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _persist_proof_binding(store, tmp_path, goal)
        await store.add_intervention(initial)
        await store.add_intervention(final)
        initial.outcome = "goal_evidence_supported"
        initial.helped = True
        initial.metadata["outcome_event_ids"] = ["codex:thread-proof:turn:two"]
        await store.update_intervention(initial)
        app_server = _process_receipt(tmp_path)
        audit_receipts = await proof.correlated_audit_receipts(store, [initial, final])
        receipt.update(
            {
                "proof_status": "validated",
                "completed_at": datetime.now(UTC).isoformat(),
                "app_server": app_server,
                "goal": goal.model_dump(mode="json"),
                "session": _session(tmp_path).model_dump(mode="json"),
                "turns": [_turn(tmp_path), _turn(tmp_path, requested_model=None)],
                "worker_model_requested": "gpt-5.3-codex-spark",
                "events": [
                    _event("codex:thread-proof:turn:one"),
                    _event("codex:thread-proof:turn:two"),
                ],
                "interventions": [
                    proof.intervention_receipt(initial),
                    proof.intervention_receipt(final),
                ],
                "audit_receipts": audit_receipts,
                "artifact": {
                    "path": str(tmp_path / "report.txt"),
                    "content": "shipped",
                },
            }
        )
        proof.validate_proof(receipt)

        reserved = copy.deepcopy(receipt)
        initial_audit = next(
            row
            for row in reserved["audit_receipts"]["audit_rows"]
            if row["intervention_id"] == "int_initial"
            and row["record_type"] == "created"
        )
        initial_audit["record_type"] = "delivery_reserved"
        initial_audit["payload"]["record_type"] = "delivery_reserved"
        initial_audit["payload_sha256"] = proof._canonical_fingerprint(
            initial_audit["payload"]
        )
        proof.validate_proof(reserved)

        noop_reserved = copy.deepcopy(receipt)
        final_audit = next(
            row
            for row in noop_reserved["audit_receipts"]["audit_rows"]
            if row["intervention_id"] == "int_final"
            and row["record_type"] == "created"
        )
        final_audit["record_type"] = "delivery_reserved"
        final_audit["payload"]["record_type"] = "delivery_reserved"
        final_audit["payload_sha256"] = proof._canonical_fingerprint(
            final_audit["payload"]
        )
        with pytest.raises(AssertionError, match="audit history is incomplete"):
            proof.validate_proof(noop_reserved)

        def mutate_canonical_delivery_turn(value):
            delivery = value["interventions"][0]["worker_delivery_receipt"]
            delivery["vendor_turn_id"] = "unrelated-turn"
            canonical = value["audit_receipts"]["sqlite_interventions"][0]
            canonical_delivery = canonical["payload"]["metadata"][
                "worker_delivery_receipt"
            ]
            canonical_delivery["vendor_turn_id"] = "unrelated-turn"
            canonical["payload_sha256"] = proof._canonical_fingerprint(
                canonical["payload"]
            )

        def mutate_verifier_everywhere(value, mutate):
            """Keep all durable projections aligned to reach the semantic gate."""

            mutate(value["interventions"][0]["independent_verifier"])
            canonical = next(
                row
                for row in value["audit_receipts"]["sqlite_interventions"]
                if row["intervention_id"] == "int_initial"
            )
            mutate(canonical["payload"]["metadata"]["independent_verifier"])
            canonical["payload_sha256"] = proof._canonical_fingerprint(canonical["payload"])
            for audit in value["audit_receipts"]["audit_rows"]:
                if audit["intervention_id"] == "int_initial":
                    mutate(audit["payload"]["independent_verifier"])
                    audit["payload_sha256"] = proof._canonical_fingerprint(audit["payload"])

        def mutate_main_everywhere(value, mutate):
            mutate(value["interventions"][0]["supervisor"])
            canonical = next(
                row
                for row in value["audit_receipts"]["sqlite_interventions"]
                if row["intervention_id"] == "int_initial"
            )
            mutate(canonical["payload"]["metadata"])
            canonical["payload_sha256"] = proof._canonical_fingerprint(canonical["payload"])
            for audit in value["audit_receipts"]["audit_rows"]:
                if audit["intervention_id"] == "int_initial":
                    mutate(audit["payload"])
                    audit["payload_sha256"] = proof._canonical_fingerprint(audit["payload"])

        def remove_verifier(value):
            value["interventions"][0]["independent_verifier"] = None
            canonical = next(
                row
                for row in value["audit_receipts"]["sqlite_interventions"]
                if row["intervention_id"] == "int_initial"
            )
            canonical["payload"]["metadata"]["independent_verifier"] = None
            canonical["payload_sha256"] = proof._canonical_fingerprint(canonical["payload"])
            for audit in value["audit_receipts"]["audit_rows"]:
                if audit["intervention_id"] == "int_initial":
                    audit["payload"]["independent_verifier"] = None
                    audit["payload_sha256"] = proof._canonical_fingerprint(audit["payload"])

        mutations = [
            remove_verifier,
            lambda value: mutate_main_everywhere(
                value, lambda main: main.__setitem__("evidence_refs", [])
            ),
            lambda value: mutate_main_everywhere(
                value,
                lambda main: main["evidence_observations"].append(
                    copy.deepcopy(main["evidence_observations"][0])
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value, lambda verifier: verifier.__setitem__("model_call_count", 0)
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier["evidence_observations"].append(
                    copy.deepcopy(verifier["evidence_observations"][0])
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value, lambda verifier: verifier.__setitem__("invocation_id", "pexinv_123")
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier["evidence_observations"][0].__setitem__(
                    "stage", "main"
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier["evidence_observations"][0].__setitem__(
                    "session_id", "codex:wrong-thread"
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier["evidence_observations"][0].__setitem__(
                    "goal_id", "wrong-goal"
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier["evidence_observations"][0].__setitem__(
                    "event_id", "codex:thread-proof:turn:wrong"
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier["evidence_observations"][0].__setitem__(
                    "invocation_id", "pexver_other"
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier["evidence_observations"][0].__setitem__(
                    "output_sha256", "0" * 64
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: verifier.__setitem__(
                    "evidence_refs", ["pexobs_" + "f" * 32]
                ),
            ),
            lambda value: mutate_verifier_everywhere(
                value,
                lambda verifier: [
                    observation.__setitem__("request_digest", "e" * 64)
                    for observation in verifier["evidence_observations"]
                ],
            ),
            lambda value: value["turns"][1].__setitem__(
                "requested_model", "different-model"
            ),
            lambda value: value["turns"][1].__setitem__("requested_model", []),
            lambda value: value["interventions"][0].__setitem__("observed_event_refs", []),
            lambda value: value["interventions"][0].__setitem__(
                "evidence", ["unrelated evidence"]
            ),
            lambda value: value["interventions"][0]["action_payload"].__setitem__(
                "text", "continue"
            ),
            lambda value: value["interventions"][1].__setitem__("delivery_result", "sent"),
            lambda value: value["artifact"].__setitem__("content", "not-shipped"),
            lambda value: value["events"][1].__setitem__("vendor_turn_id", "other"),
            lambda value: value["events"][1].__setitem__("raw_event_ref", "{}"),
            mutate_canonical_delivery_turn,
        ]
        for mutate in mutations:
            changed = copy.deepcopy(receipt)
            mutate(changed)
            with pytest.raises(AssertionError):
                proof.validate_proof(changed)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_audit_receipt_correlates_sqlite_final_state_and_jsonl(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        now = datetime.now(UTC)
        goal = Goal(
            id="goal-proof",
            project_id=str(tmp_path),
            title="Correlate audit receipt",
            objective="Preserve the canonical intervention audit trail.",
            created_at=now,
            updated_at=now,
        )
        await _persist_proof_binding(store, tmp_path, goal)
        intervention = _intervention()
        await store.add_intervention(intervention)
        intervention.outcome = "goal_evidence_supported"
        intervention.helped = True
        intervention.metadata["outcome_event_ids"] = ["codex:thread-proof:turn:two"]
        await store.update_intervention(intervention)

        receipts = await proof.correlated_audit_receipts(store, [intervention])

        audit_rows = receipts["audit_rows"]
        assert [row["record_type"] for row in audit_rows] == ["created", "outcome_observed"]
        assert all(row["sqlite_jsonl_match"] is True for row in audit_rows)
        assert audit_rows[-1]["payload"]["outcome"] == "goal_evidence_supported"
        assert receipts["sqlite_interventions"][0]["payload"]["metadata"]["used_llm"] is True
        projected = [
            json.loads(line) for line in store.audit_path.read_text(encoding="utf-8").splitlines()
        ]
        assert projected[-1]["audit_id"] == audit_rows[-1]["audit_id"]

        with store.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(projected[-1]) + "\n")
        with pytest.raises(AssertionError, match="does not match JSONL"):
            await proof.correlated_audit_receipts(store, [intervention])
    finally:
        await store.close()


def test_publish_proof_rejects_secret_fields(tmp_path, monkeypatch):
    with pytest.raises(AssertionError, match="forbidden secret field"):
        proof.publish_proof(
            tmp_path / "proof.json",
            {"schema": proof.PROOF_SCHEMA, "api_key": "must-not-persist"},
        )
    assert not (tmp_path / "proof.json").exists()

    monkeypatch.setenv("PEX_SUPERVISOR_API_KEY", "sensitive-value-123")
    with pytest.raises(AssertionError, match="configured secret material"):
        proof.publish_proof(
            tmp_path / "proof.json",
            {"schema": proof.PROOF_SCHEMA, "diagnosis": "sensitive-value-123"},
        )
    assert not (tmp_path / "proof.json").exists()

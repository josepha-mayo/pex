from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets import PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store, new_id, utcnow
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, PolicyVerdict
from pex_protocol.intervention import Intervention
from pex_protocol.overlay import Overlay, OverlayDiff

_OPERATOR_TOKEN = "goal-lifecycle-operator-token-0123456789"


class _GoalLifecycleClient(AsyncClient):
    """Supply the authenticated mutation contract to legacy domain-focused cases."""

    _operation_sequence = 0

    async def request(self, method, url, *, json=None, **kwargs):
        path = str(url)
        verb = str(method).upper()
        if isinstance(json, dict) and (
            (verb == "POST" and path == "/v1/goals")
            or (verb == "PATCH" and path.startswith("/v1/goals/"))
            or (verb == "POST" and path.endswith("/attach"))
        ):
            self._operation_sequence += 1
            json = dict(json)
            json.setdefault(
                "idempotency_key",
                f"goal-lifecycle-operation-{self._operation_sequence:08d}",
            )
            if path.endswith("/attach"):
                session_path = path.removesuffix("/attach")
                session_response = await super().request("GET", session_path)
                session_payload = (
                    session_response.json() if session_response.status_code == 200 else {}
                )
                session_id = session_path.removeprefix("/v1/sessions/")
                session_control = await state.store.get_session_control_state(session_id)
                goal_response = await super().request(
                    "GET",
                    f"/v1/goals/{json.get('goal_id', '')}",
                )
                goal_payload = goal_response.json() if goal_response.status_code == 200 else {}
                json.setdefault("expected_goal_id", session_payload.get("goal_id"))
                json.setdefault(
                    "expected_control_revision",
                    (
                        session_control.get("control_revision", 0)
                        if session_control is not None
                        else 0
                    ),
                )
                json.setdefault(
                    "expected_goal_intent_revision",
                    goal_payload.get("intent_revision", 0),
                )
        return await super().request(method, url, json=json, **kwargs)


@pytest.fixture
async def client(tmp_path):
    settings = Settings(
        require_auth=True,
        token=_OPERATOR_TOKEN,
        home=tmp_path,
        autonomy="manage",
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = _OPERATOR_TOKEN
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    transport = ASGITransport(app=create_app())
    async with _GoalLifecycleClient(
        transport=transport,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
    ) as ac:
        yield ac
    await store.close()


async def _goal(client: AsyncClient, *, project_id: str = "demo", title: str = "Goal") -> dict:
    response = await client.post(
        "/v1/goals",
        json={
            "project_id": project_id,
            "title": title,
            "objective": f"Complete {title}",
            "acceptance_criteria": [f"{title} is verified"],
        },
    )
    assert response.status_code == 200
    return response.json()


def _goal_resource(payload: dict) -> dict:
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "goal_mutation_receipt",
            "reattached_session_ids",
            "operator_operation_receipt",
        }
    }


@pytest.mark.asyncio
async def test_attach_validates_goal_project_and_explicit_replacement(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()

    missing = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={"goal_id": "goal_missing"},
    )
    assert missing.status_code == 404

    wrong_project = await _goal(client, project_id="another-project", title="Wrong")
    mismatch = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={"goal_id": wrong_project["id"]},
    )
    assert mismatch.status_code == 409

    first = await _goal(client, title="First")
    attached = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={
            "goal_id": first["id"],
            "expected_control_revision": 0,
            "expected_goal_intent_revision": first["intent_revision"],
        },
    )
    assert attached.status_code == 200
    assert attached.json()["goal_id"] == first["id"]
    first_receipt = attached.json()["session_goal_attachment_receipt"]
    assert first_receipt["schema"] == "pex.session-goal-attachment-receipt.v1"
    assert first_receipt["reason"] == "session_goal_attached"
    assert first_receipt["before_control_revision"] == 0
    assert first_receipt["after_control_revision"] == 1

    second = await _goal(client, title="Second")
    silent_replace = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={"goal_id": second["id"]},
    )
    assert silent_replace.status_code == 409
    unchanged = await client.get(f"/v1/sessions/{session['id']}")
    assert unchanged.json()["goal_id"] == first["id"]

    replaced = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={
            "goal_id": second["id"],
            "replace_existing": True,
            "expected_goal_id": first["id"],
            "expected_control_revision": 1,
            "expected_goal_intent_revision": second["intent_revision"],
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["goal_id"] == second["id"]
    replacement_receipt = replaced.json()["session_goal_attachment_receipt"]
    assert replacement_receipt["reason"] == "session_goal_replaced"
    assert replacement_receipt["before_control_revision"] == 1
    assert replacement_receipt["after_control_revision"] == 2


@pytest.mark.asyncio
async def test_goal_create_keeps_fenced_examples_out_of_persistent_lists(client: AsyncClient):
    objective = (
        "Implement the real feature.\n\n```markdown\n"
        "Acceptance criteria:\n- Example acceptance\n"
        "Decisions:\n- Example decision\n```\n"
        "Acceptance criteria:\n- Real acceptance\n"
        "Decisions:\n- Real decision\n"
    )
    created = await client.post("/v1/goals", json={
        "project_id": "demo", "title": "Fenced examples", "objective": objective,
    })
    assert created.status_code == 200, created.text
    goal = created.json()
    assert goal["objective"] == objective
    assert goal["acceptance_criteria"] == ["Real acceptance"]
    rows = await client.get(f"/v1/goals/{goal['id']}/decisions")
    assert rows.status_code == 200, rows.text
    assert {item["statement"] for item in rows.json()} == {"Real decision"}


@pytest.mark.asyncio
async def test_goal_create_persists_labeled_decision_ledger(client: AsyncClient):
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Migrate the ledger",
            "objective": (
                "Keep the durable store honest.\n\n"
                "Decisions:\n"
                "- Use PostgreSQL for the durable ledger\n\n"
                "Rejected approaches:\n"
                "- Do not rewrite the evaluator as a new service\n\n"
                "Unresolved questions:\n"
                "- Which checkpoint format should survive the migration?\n"
            ),
        },
    )
    assert created.status_code == 200, created.text
    rows = await client.get(f"/v1/goals/{created.json()['id']}/decisions")
    assert rows.status_code == 200, rows.text
    statements = {item["statement"]: item for item in rows.json()}
    assert "Use PostgreSQL for the durable ledger" in statements
    assert statements["Use PostgreSQL for the durable ledger"]["status"] == "active"
    assert statements["Use PostgreSQL for the durable ledger"]["metadata"]["kind"] == "decision"
    assert "Do not rewrite the evaluator as a new service" in statements
    assert (
        statements["Do not rewrite the evaluator as a new service"]["metadata"]["kind"]
        == "rejected_approach"
    )
    assert "Which checkpoint format should survive the migration?" in statements
    assert (
        statements["Which checkpoint format should survive the migration?"]["status"]
        == "uncertain"
    )
    context = await client.get("/v1/context", params={"project_id": "demo"})
    assert context.status_code == 200, context.text
    contents = {item["content"] for item in context.json()}
    assert "Use PostgreSQL for the durable ledger" in contents
    assert "Do not rewrite the evaluator as a new service" in contents


@pytest.mark.asyncio
async def test_explicit_ledger_patch_replaces_only_its_kind_and_preserves_history(
    client: AsyncClient,
):
    shared = "Keep this exact statement"
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Ledger replacement",
            "objective": "Maintain the explicit intent ledger.",
            "decisions": [shared],
            "rejected_approaches": [shared],
        },
    )
    assert created.status_code == 200, created.text
    goal_id = created.json()["id"]

    initial = (await client.get(f"/v1/goals/{goal_id}/decisions")).json()
    same_text = [row for row in initial if row["statement"] == shared]
    assert {row["metadata"]["kind"] for row in same_text} == {
        "decision",
        "rejected_approach",
    }
    original_decision = next(
        row for row in same_text if row["metadata"]["kind"] == "decision"
    )
    rejected = next(
        row for row in same_text if row["metadata"]["kind"] == "rejected_approach"
    )

    replaced = await client.patch(
        f"/v1/goals/{goal_id}",
        json={
            "decisions": ["Use the replacement decision"],
            "expected_intent_revision": 1,
        },
    )
    assert replaced.status_code == 200, replaced.text
    after_replace = (await client.get(f"/v1/goals/{goal_id}/decisions")).json()
    by_id = {row["id"]: row for row in after_replace}
    assert by_id[original_decision["id"]]["status"] == "superseded"
    assert by_id[rejected["id"]]["status"] == "active"
    replacement = next(
        row for row in after_replace if row["statement"] == "Use the replacement decision"
    )
    assert replacement["status"] == "active"

    context_by_decision = {
        item.metadata.get("decision_id"): item
        for item in await state.store.list_context("demo")
        if item.metadata.get("decision_id")
    }
    retired_context = context_by_decision[original_decision["id"]]
    assert retired_context.metadata["status"] == "superseded"
    assert retired_context.stale_after is not None
    assert context_by_decision[rejected["id"]].metadata["status"] == "active"

    cleared = await client.patch(
        f"/v1/goals/{goal_id}",
        json={"decisions": [], "expected_intent_revision": 2},
    )
    assert cleared.status_code == 200, cleared.text
    after_clear = (await client.get(f"/v1/goals/{goal_id}/decisions")).json()
    assert next(row for row in after_clear if row["id"] == replacement["id"])[
        "status"
    ] == "superseded"
    assert next(row for row in after_clear if row["id"] == rejected["id"])[
        "status"
    ] == "active"

    readded = await client.patch(
        f"/v1/goals/{goal_id}",
        json={"decisions": [shared], "expected_intent_revision": 3},
    )
    assert readded.status_code == 200, readded.text
    final = (await client.get(f"/v1/goals/{goal_id}/decisions")).json()
    decision_rows = [
        row
        for row in final
        if row["statement"] == shared and row["metadata"]["kind"] == "decision"
    ]
    assert {row["status"] for row in decision_rows} == {"active", "superseded"}


@pytest.mark.asyncio
async def test_goal_update_and_override_preserve_history_and_move_attached_sessions(
    client: AsyncClient,
):
    first_session = (await client.post("/v1/synthetic/sessions")).json()
    second_session = state.adapters.synthetic.seed_session(vendor_id="goal-override-2")
    await state.store.upsert_session(second_session)
    original = await _goal(client, title="Original")
    for session_id in (first_session["id"], second_session.id):
        response = await client.post(
            f"/v1/sessions/{session_id}/attach",
            json={"goal_id": original["id"]},
        )
        assert response.status_code == 200

    updated = await client.patch(
        f"/v1/goals/{original['id']}",
        json={
            "objective": "Complete the corrected objective",
            "deadline": None,
            "expected_intent_revision": original["intent_revision"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == original["id"]
    assert updated.json()["created_at"] == original["created_at"]
    assert updated.json()["objective"] == "Complete the corrected objective"

    override = await client.patch(
        f"/v1/goals/{original['id']}",
        json={
            "mode": "override",
            "objective": "Complete the intentionally replaced objective",
            "constraints": ["Do not restore the stale objective"],
            "expected_intent_revision": updated.json()["intent_revision"],
        },
    )
    assert override.status_code == 200
    successor = override.json()
    assert successor["id"] != original["id"]
    assert successor["supersedes"] == original["id"]
    assert set(successor["reattached_session_ids"]) == {
        first_session["id"],
        second_session.id,
    }

    old = (await client.get(f"/v1/goals/{original['id']}")).json()
    assert old["objective"] == "Complete the corrected objective"
    for session_id in (first_session["id"], second_session.id):
        session = (await client.get(f"/v1/sessions/{session_id}")).json()
        assert session["goal_id"] == successor["id"]

    stale_update = await client.patch(
        f"/v1/goals/{original['id']}",
        json={"objective": "Restore stale intent", "expected_intent_revision": 2},
    )
    assert stale_update.status_code == 409
    stale_attach = await client.post(
        f"/v1/sessions/{first_session['id']}/attach",
        json={"goal_id": original["id"], "replace_existing": True},
    )
    assert stale_attach.status_code == 409


@pytest.mark.asyncio
async def test_ledger_only_override_creates_successor_and_moves_attached_session(
    client: AsyncClient,
):
    session = (await client.post("/v1/synthetic/sessions")).json()
    original = await _goal(client, title="Ledger-only predecessor")
    attached = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={"goal_id": original["id"]},
    )
    assert attached.status_code == 200

    override = await client.patch(
        f"/v1/goals/{original['id']}",
        json={
            "mode": "override",
            "decisions": ["Use the explicitly overridden ledger decision"],
            "expected_intent_revision": original["intent_revision"],
        },
    )
    assert override.status_code == 200, override.text
    successor = override.json()
    assert successor["id"] != original["id"]
    assert successor["supersedes"] == original["id"]
    assert successor["reattached_session_ids"] == [session["id"]]

    rebound = (await client.get(f"/v1/sessions/{session['id']}")).json()
    assert rebound["goal_id"] == successor["id"]
    original_after = (await client.get(f"/v1/goals/{original['id']}")).json()
    assert original_after["id"] == original["id"]
    decisions = (
        await client.get(f"/v1/goals/{successor['id']}/decisions")
    ).json()
    assert any(
        row["statement"] == "Use the explicitly overridden ledger decision"
        and row["status"] == "active"
        for row in decisions
    )


@pytest.mark.asyncio
async def test_override_rejects_empty_change_and_inherits_unspecified_ledger(
    client: AsyncClient,
):
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Inherited ledger",
            "objective": "Keep every unspecified ledger boundary.",
            "decisions": ["Keep the exact supervisor boundary"],
            "rejected_approaches": ["Do not degrade into a completion hook"],
            "unresolved_questions": ["Which real trace is the final demo?"],
        },
    )
    assert created.status_code == 200, created.text
    original = created.json()
    original_rows = (
        await client.get(f"/v1/goals/{original['id']}/decisions")
    ).json()

    empty = await client.patch(
        f"/v1/goals/{original['id']}",
        json={"mode": "override"},
    )
    assert empty.status_code == 400

    successor_response = await client.patch(
        f"/v1/goals/{original['id']}",
        json={
            "mode": "override",
            "objective": "Keep every boundary and add a stronger real trace.",
            "expected_intent_revision": original["intent_revision"],
        },
    )
    assert successor_response.status_code == 200, successor_response.text
    successor = successor_response.json()
    assert successor["intent_revision"] == original["intent_revision"] + 1
    successor_rows = (
        await client.get(f"/v1/goals/{successor['id']}/decisions")
    ).json()
    expected = {
        (row["metadata"]["kind"], row["statement"], row["status"])
        for row in original_rows
        if row["status"] != "superseded"
    }
    inherited = {
        (row["metadata"]["kind"], row["statement"], row["status"])
        for row in successor_rows
        if row["status"] != "superseded"
    }
    assert inherited == expected
    assert {row["id"] for row in successor_rows}.isdisjoint(
        {row["id"] for row in original_rows}
    )

    no_ledger = await _goal(client, title="Empty override")
    empty_no_ledger = await client.patch(
        f"/v1/goals/{no_ledger['id']}",
        json={"mode": "override"},
    )
    assert empty_no_ledger.status_code == 400


@pytest.mark.asyncio
async def test_attach_rejects_undocumented_project_mismatch_override(client: AsyncClient):
    session = state.adapters.synthetic.seed_session(
        vendor_id="different-project",
        project_id="other-project",
        cwd="other-project",
    )
    await state.store.upsert_session(session)
    goal = await _goal(client)

    response = await client.post(
        f"/v1/sessions/{session.id}/attach",
        json={"goal_id": goal["id"], "allow_project_mismatch": True},
    )

    assert response.status_code == 422
    assert any(
        error.get("type") == "extra_forbidden"
        and error.get("loc") == ["body", "allow_project_mismatch"]
        for error in response.json()["detail"]
    )
    assert (await state.store.get_session(session.id)).goal_id is None


@pytest.mark.asyncio
async def test_plugin_heartbeat_claims_only_enforced_overlay_fields(client: AsyncClient):
    response = await client.post(
        "/v1/adapters/opencode/plugin-heartbeat",
        json={"source": "pex-opencode-plugin", "version": "test", "directory": "demo"},
    )

    assert response.status_code == 200
    assert response.json()["supported"] == ["system_instructions", "tools_disabled"]
    assert response.json()["session_id"] is None


@pytest.mark.asyncio
async def test_plugin_heartbeat_upserts_isolated_opencode_session(
    client: AsyncClient, tmp_path
):
    worker = tmp_path / "isolated-opencode"
    worker.mkdir()
    response = await client.post(
        "/v1/adapters/opencode/plugin-heartbeat",
        json={
            "source": "pex-opencode-plugin",
            "version": "test",
            "directory": str(worker),
            "session_id": "ses_isolated_heartbeat",
        },
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == "opencode:ses_isolated_heartbeat"
    stored = await state.store.get_session("opencode:ses_isolated_heartbeat")
    assert stored is not None
    assert stored.cwd == str(worker)
    assert stored.goal_id is None


@pytest.mark.asyncio
async def test_goal_patch_keeps_explicit_empty_lists_instead_of_reextracting(
    client: AsyncClient,
):
    labeled = (
        "Create the release receipt.\n\n"
        "Acceptance criteria:\n\n"
        "- report.txt contains shipped\n"
    )
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Receipt",
            "objective": labeled,
        },
    )
    assert created.status_code == 200
    goal = created.json()
    assert goal["intent_revision"] == 1
    assert len(goal["intent_hash"]) == 64
    assert goal["acceptance_criteria"] == ["report.txt contains shipped"]

    cleared = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "mode": "update",
            "acceptance_criteria": [],
            "expected_intent_revision": goal["intent_revision"],
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["id"] == goal["id"]
    assert cleared.json()["intent_revision"] == 2
    assert cleared.json()["intent_hash"] != goal["intent_hash"]
    assert cleared.json()["acceptance_criteria"] == []
    assert cleared.json()["objective"] == goal["objective"]

    fetched = await client.get(f"/v1/goals/{goal['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["acceptance_criteria"] == []
    listed = await client.get("/v1/goals")
    assert listed.status_code == 200
    assert listed.json()[0]["intent_revision"] == 2


@pytest.mark.asyncio
async def test_goal_patch_rejects_empty_or_null_intent_changes(client: AsyncClient):
    goal = await _goal(client)
    empty = await client.patch(f"/v1/goals/{goal['id']}", json={})
    assert empty.status_code == 400
    null_objective = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={"objective": None, "expected_intent_revision": goal["intent_revision"]},
    )
    assert null_objective.status_code == 400


@pytest.mark.asyncio
async def test_goal_patch_requires_exact_revision_and_rejects_stale_noop(
    client: AsyncClient,
):
    goal = await _goal(client, title="CAS boundary")
    missing = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={"objective": "A mutation without a CAS token"},
    )
    assert missing.status_code == 428
    assert missing.json()["detail"]["code"] == "goal_intent_revision_required"

    committed = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "objective": "The exact committed CAS objective",
            "expected_intent_revision": goal["intent_revision"],
        },
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["intent_revision"] == goal["intent_revision"] + 1

    stale_noop = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "objective": committed.json()["objective"],
            "expected_intent_revision": goal["intent_revision"],
        },
    )
    assert stale_noop.status_code == 409
    assert "intent revision changed" in str(stale_noop.json()["detail"])


@pytest.mark.asyncio
async def test_case_only_ledger_change_is_not_collapsed(client: AsyncClient):
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Case-sensitive ledger",
            "objective": "Preserve the exact human statement.",
            "decisions": ["Use SQL"],
        },
    )
    assert created.status_code == 200, created.text
    goal = created.json()
    changed = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "decisions": ["use sql"],
            "expected_intent_revision": goal["intent_revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["intent_revision"] == goal["intent_revision"] + 1
    assert changed.json()["goal_mutation_receipt"]["changed"] is True
    rows = (await client.get(f"/v1/goals/{goal['id']}/decisions")).json()
    assert any(row["statement"] == "use sql" and row["status"] == "active" for row in rows)


@pytest.mark.asyncio
async def test_same_value_goal_update_is_a_semantic_noop(client: AsyncClient):
    goal = await _goal(client, title="Stable intent")
    unchanged = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "mode": "update",
            "objective": goal["objective"],
            "expected_intent_revision": goal["intent_revision"],
        },
    )
    assert unchanged.status_code == 200, unchanged.text
    unchanged_payload = unchanged.json()
    receipt = unchanged_payload["goal_mutation_receipt"]
    assert receipt["mode"] == "update"
    assert receipt["changed"] is False
    assert receipt["before_intent_revision"] == receipt["after_intent_revision"] == 1
    assert receipt["before_intent_hash"] == receipt["after_intent_hash"]
    assert _goal_resource(unchanged_payload) == _goal_resource(goal)
    assert (await client.get(f"/v1/goals/{goal['id']}")).json() == _goal_resource(goal)


@pytest.mark.asyncio
async def test_same_value_ledger_update_preserves_projection_identity(client: AsyncClient):
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Stable ledger",
            "objective": "Keep the active decision stable.",
            "decisions": ["Keep the exact active decision"],
        },
    )
    assert created.status_code == 200, created.text
    goal = created.json()
    before = (await client.get(f"/v1/goals/{goal['id']}/decisions")).json()

    unchanged = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "mode": "update",
            "decisions": ["Keep the exact active decision"],
            "expected_intent_revision": goal["intent_revision"],
        },
    )
    assert unchanged.status_code == 200, unchanged.text
    unchanged_payload = unchanged.json()
    assert unchanged_payload["goal_mutation_receipt"]["changed"] is False
    assert _goal_resource(unchanged_payload) == _goal_resource(goal)
    after = (await client.get(f"/v1/goals/{goal['id']}/decisions")).json()
    assert after == before


@pytest.mark.asyncio
async def test_saturated_ledger_read_cannot_claim_a_semantic_noop(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    created = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Bounded ledger",
            "objective": "Keep a bounded decision ledger.",
            "decisions": ["Retain the bounded decision"],
        },
    )
    assert created.status_code == 200, created.text
    goal = created.json()
    original = state.store.list_decisions_for_authority

    async def saturated(*args, **kwargs):
        rows = await original(*args, **kwargs)
        return rows * 1000

    monkeypatch.setattr(state.store, "list_decisions_for_authority", saturated)
    calls = 0
    original_patch = state.store.patch_goal_with_ledger_receipt

    async def counted_patch(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original_patch(*args, **kwargs)

    monkeypatch.setattr(state.store, "patch_goal_with_ledger_receipt", counted_patch)
    response = await client.patch(
        f"/v1/goals/{goal['id']}",
        json={
            "mode": "update",
            "decisions": ["Retain the bounded decision"],
            "expected_intent_revision": goal["intent_revision"],
        },
    )
    assert response.status_code == 200, response.text
    assert calls == 1


@pytest.mark.asyncio
async def test_overlay_routes_list_and_revert_durable_state(client: AsyncClient):
    session = (await client.post("/v1/synthetic/sessions")).json()
    goal = await _goal(client, project_id=session["project_id"], title="Overlay route")
    attached = await client.post(
        f"/v1/sessions/{session['id']}/attach",
        json={"goal_id": goal["id"]},
    )
    assert attached.status_code == 200
    session = attached.json()
    overlay = Overlay(
        id="ovl_route",
        session_id=session["id"],
        reason="Temporarily pin implementation mode.",
        diff=OverlayDiff(extra={"phase": "implementation"}),
        ttl_seconds=60,
    )
    action = ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=session["id"],
        goal_id=goal["id"],
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale="Use an exact, reversible session overlay.",
        evidence=["test:overlay-route"],
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )
    intervention_id = new_id("int_overlay_route_")
    await state.store.add_intervention(
        Intervention(
            id=intervention_id,
            session_id=session["id"],
            goal_id=goal["id"],
            trigger="test",
            evidence=action.evidence,
            diagnosis="overlay_route_test",
            proposed_action=action,
            confidence=action.confidence,
            risk=action.risk.value,
            reversible=True,
            authority_required=action.authority_required.value,
            action_taken=InterventionType.APPLY_OVERLAY.value,
            policy_verdict=PolicyVerdict.ALLOW,
            result="overlay_pending",
            created_at=utcnow(),
        )
    )
    assert (
        await state.pipeline.executor.execute(
            action,
            PolicyVerdict.ALLOW,
            operation_owner_id=intervention_id,
        )
        == "overlay_applied"
    )

    listed = await client.get(f"/v1/sessions/{session['id']}/overlays")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [overlay.id]

    revert_body = {"idempotency_key": "goal-overlay-revert-0001"}
    reverted = await client.post(
        f"/v1/overlays/{overlay.id}/revert",
        json=revert_body,
    )
    assert reverted.status_code == 200
    assert reverted.json()["code"] == "overlay_reverted"
    repeated = await client.post(
        f"/v1/overlays/{overlay.id}/revert",
        json=revert_body,
    )
    assert repeated.status_code == 200
    assert repeated.json()["code"] == "overlay_already_reverted"
    assert repeated.json()["replayed"] is True

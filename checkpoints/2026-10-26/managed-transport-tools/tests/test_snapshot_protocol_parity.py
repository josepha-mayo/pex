"""Real PEX schema/tool registry construction on authored snapshot; no network."""
import hashlib,json
from dataclasses import replace
import pytest
from test_tool_protocol import request_fixture,no_network
from pex_protocol.actions import ProposedAction,InterventionType
from pex_supervisor.evidence_tools import select_evidence_tool_names
from managed_chat import Route,Refusal
from strands_bridge import ManagedPEXModel


def request():
    r=request_fixture(with_boundaries=True)
    content='Authored local tool-registry fixture only.\n'
    files={'TASK.md':{'content':content,'sha256':hashlib.sha256(content.encode()).hexdigest()}}
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    r.scores.features['public_candidate_snapshot']={'schema':'pex.public-candidate-snapshot.v1','files':files,'snapshot_sha256':digest}
    return r


@pytest.mark.parametrize('role',['planner','verifier'])
def test_actual_snapshot_toolset_constructs_complete_managed_model(role):
    r=request();selected=select_evidence_tool_names(r)
    assert 'inspect_public_snapshot' in selected
    proposal=ProposedAction(type=InterventionType.SEND_NUDGE,session_id=r.session.id,goal_id=r.goal.id,rationale='Authored fixture only',payload={'text':'Authored fixture only'}) if role=='verifier' else None
    model=ManagedPEXModel(Route('https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions','nvidia/nemotron-3-super-120b-a12b',role),r,invocation_id='fixture-snapshot-'+role,proposal=proposal)
    actual={d.name for d in model.protocol.definitions if not d.final}
    assert actual==set(selected)
    definition=next(d for d in model.protocol.definitions if d.name=='inspect_public_snapshot')
    assert definition.final is False
    # Arbitrary tools are still refused, not silently exposed by the repair.
    bad=replace(definition,name='unapproved_external_shell')
    with pytest.raises(Refusal,match='unapproved_evidence_tool'):
        replace(model.protocol,definitions=tuple(bad if d is definition else d for d in model.protocol.definitions))


def test_invalid_snapshot_is_not_offered():
    r=request();r.scores.features['public_candidate_snapshot']['snapshot_sha256']='0'*64
    assert 'inspect_public_snapshot' not in select_evidence_tool_names(r)

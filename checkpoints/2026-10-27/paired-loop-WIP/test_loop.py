"""Authored-only control-flow and full owned protocol tests, not inference."""
import asyncio
import copy
from types import SimpleNamespace
import pytest
from controller import Budget, run_pair


def arms():
    return {c: dict(prompt="Same fixed public task", public_sha256="a"*64,
                    worker_identity="same-exact-worker", workspace=c) for c in ("baseline", "pex")}


class Worker:
    def __init__(self):
        self.calls, self.stopped, self.cleaned = [], set(), False
    async def turn(self, arm, **kw):
        self.calls.append((arm["workspace"], kw))
        return dict(session_id=arm["workspace"]+"-session", receipt="authored-turn",
                    usage=dict(calls=1, input_tokens=10, output_tokens=5),
                    terminal="natural_stop", public_observation={"kind": "authored-public-observation"})
    async def stop(self, arm):
        self.stopped.add(arm["workspace"])
    async def cleanup(self):
        self.cleaned = True


class Grade:
    def __init__(self, worker): self.worker=worker
    async def grade(self, arm):
        assert self.worker.stopped == {"baseline", "pex"}
        return {"kind": "authored-placeholder", "score": None}


class Review:
    async def review(self, arm, observation, **kw):
        return dict(status="approved_continuation", text="Authored wiring test only", receipt="authored")


def test_equal_budget_same_session_and_no_oracle_feedback():
    w=Worker()
    r=asyncio.run(run_pair(arms(),w,Review(),Grade(w),budget=Budget(calls=2)))
    assert [x[0] for x in w.calls] == ["baseline", "pex", "pex"]
    assert w.calls[-1][1]["session_id"] == "pex-session"
    assert w.calls[0][1]["remaining"] == w.calls[1][1]["remaining"]
    assert r["arms"]["pex"]["status"] == "budget_terminal_inconclusive"
    assert r["pex_lift"] is None and not r["presentation_eligible"] and w.cleaned


def test_supervisor_time_does_not_reduce_worker_allowance():
    ticks=iter([0,1,1,2,2,72,72,73,73,143])
    w=Worker()
    r=asyncio.run(run_pair(arms(),w,Review(),Grade(w),budget=Budget(calls=2),clock=lambda: next(ticks)))
    assert w.calls[2][1]["remaining"]["active_seconds"] == 89
    assert r["arms"]["pex"]["supervisor_seconds"] == 140


def test_live_denied_before_callbacks():
    with pytest.raises(PermissionError):
        asyncio.run(run_pair(arms(),None,None,None,mode="live"))


def test_mismatched_workers_denied():
    a=arms();a["pex"]["worker_identity"]="different"
    with pytest.raises(ValueError): asyncio.run(run_pair(a,None,None,None))


def test_infrastructure_failure_is_not_task_failure():
    class Bad(Worker):
        async def turn(self,*a,**kw): raise ConnectionError("authored failure")
    w=Bad();r=asyncio.run(run_pair(arms(),w,Review(),Grade(w)))
    assert all(x["status"]=="infrastructure_error" and "protected_grade" not in x for x in r["arms"].values())
    assert w.cleaned


# Real full PEX prompt/schema/tool protocol, with HTTP MockTransport responses.
from process_adapter import fixture_model
from managed_chat import Limits, Route
from test_process import Ledger
from test_managed_chat import ENDPOINT, MODEL, response
from test_managed_chat import rig, no_network
from test_tool_protocol import request_fixture
from test_tool_transport import payload
from review import OwnedReview


@pytest.mark.asyncio
@pytest.mark.parametrize("approve", [True,False])
async def test_owned_planner_verifier_continuation(tmp_path, rig, approve):
    models=[]
    def request_builder(arm, observation, session_id):
        r=request_fixture(with_boundaries=True)
        r.session.vendor_session_id=session_id
        return r
    def factory(role, request, proposal):
        route=Route(ENDPOINT,MODEL,role,Limits(max_usage_tokens=10000))
        ledger=Ledger(tmp_path/(role+".sqlite"),budget=100000,input_rate=2,output_rate=3,route=route)
        m=fixture_model(route,request,invocation_id="joined-"+role,ledger=ledger,proposal=proposal)
        models.append(m)
        return m
    def handler(request):
        m=models[-1]
        n=len(m.observations)
        if n==0:
            return response(payload("get_goal",'{"boundary_page":0}',"goal"))
        if n==1:
            return response(payload("get_session_state","{}","state"))
        refs=[x.observation_id for x in m.observations]
        args=dict(rationale="Authored protocol decision",evidence=["Authored observed session"],evidence_refs=refs)
        if m.protocol.role=="planner":
            args.update(action_type="CONTINUE_SESSION",message="Authored non-answer continuation for protocol test")
        else: args.update(approved=approve)
        import json
        return response(payload(m.protocol.final_name,json.dumps(args),"final"))
    rig.handler=handler
    review=OwnedReview(request_builder,factory)
    result=await review.review(arms()["pex"],{},session_id="fixture-vendor")
    assert result["status"] == ("approved_continuation" if approve else "verifier_rejected")
    assert len(models)==2 and len(rig.calls)==6
    assert all(len(m.observations)==2 for m in models)
    assert result["receipt"]["planner_invocation"] != result["receipt"]["verifier_invocation"]
    if approve: assert result["text"]=="Authored non-answer continuation for protocol test"

"""AUTHORED offline transport responses, not live benchmark evidence."""
import asyncio,json
import pytest
import httpx
from test_strands_bridge import model
from test_managed_chat import rig,no_network,response
from test_tool_transport import payload
from test_tool_protocol import final_arguments


def invalid(m):
    args=final_arguments(m.protocol.role)
    args.update(evidence='not an array',evidence_refs='not an array')
    return payload(m.protocol.final_name,json.dumps(args))

@pytest.mark.asyncio
async def test_strict_schema_rejection_feedback_and_actual_model_reemission(rig):
    m=model()
    def handler(request):
        wire=json.loads(request.content)
        if len(rig.calls)==1:return response(invalid(m))
        assert len(rig.calls)==2
        assert 'previous final tool call was rejected' in wire['messages'][-1]['content']
        assert 'not an array' not in request.content.decode()
        assert wire['tools']
        return response(payload(m.protocol.final_name,json.dumps(final_arguments('planner')),'reemit'))
    rig.handler=handler
    result=await m.invoke_async()
    assert result.structured_output.action_type.value=='NOOP'
    assert len(m.receipts)==2 and m._rounds==2
    assert m.receipts[0].outcome=='uncertain'
    assert m.receipts[0].reason=='tool_arguments_schema_mismatch'
    assert m.receipts[0].usage is not None
    assert m.receipts[1].outcome=='succeeded'
    assert m.used_tools==() # Rejected proposal never executed.

@pytest.mark.asyncio
async def test_repeated_invalid_response_stops_after_one_retry(rig):
    m=model();rig.handler=lambda _:response(invalid(m))
    with pytest.raises(Exception):await m.invoke_async()
    assert len(rig.calls)==len(m.receipts)==2
    assert all(r.outcome=='uncertain' for r in m.receipts)

@pytest.mark.asyncio
async def test_final_round_invalid_response_has_no_extra_budget(rig):
    m=model()
    def handler(request):
        n=len(rig.calls)
        if n<3:return response(payload('get_goal','{}','goal'+str(n)))
        return response(invalid(m))
    rig.handler=handler
    with pytest.raises(Exception):await m.invoke_async()
    assert len(rig.calls)==3 and m._rounds==3
    assert not m._schema_retry_used

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['read_timeout','cancel'])
async def test_unknown_or_cancelled_transport_never_schema_retries(rig,kind):
    m=model()
    def handler(request):
        if kind=='cancel':raise asyncio.CancelledError()
        raise httpx.ReadTimeout('AUTHORED')
    rig.handler=handler
    with pytest.raises(BaseException):await m.invoke_async()
    assert len(rig.calls)==1 and not m._schema_retry_used

@pytest.mark.asyncio
async def test_outer_review_deadline_cancels_schema_retry(rig):
    m=model();entered=asyncio.Event()
    async def handler(request):
        if len(rig.calls)==1:return response(invalid(m))
        entered.set();await asyncio.Event().wait()
    rig.handler=handler
    task=asyncio.create_task(m.invoke_async())
    await asyncio.wait_for(entered.wait(),2)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(.01):await task
    assert len(rig.calls)==2 and len(m.receipts)==2
    assert m.receipts[-1].reason=="cancelled"
    assert m._terminal

@pytest.mark.asyncio
async def test_mixed_invalid_final_and_evidence_tools_never_execute_or_retry(rig):
    m=model();data=invalid(m)
    data['choices'][0]['message']['tool_calls'].append(payload('get_goal','{}','extra')['choices'][0]['message']['tool_calls'][0])
    rig.handler=lambda _:response(data)
    with pytest.raises(Exception):await m.invoke_async()
    assert len(rig.calls)==1 and m.used_tools==() and not m._schema_retry_used

@pytest.mark.asyncio
async def test_forced_final_schema_retry_keeps_pinned_choice_and_schema(rig):
    from test_managed_chat import VALID
    m=model();specs=[]
    def handler(request):
        wire=json.loads(request.content);n=len(rig.calls)
        if n==1:return response(VALID)
        assert wire['tool_choice']=='required'
        assert [x['function']['name'] for x in wire['tools']]==[m.protocol.final_name]
        specs.append(wire['tools'])
        if n==2:return response(invalid(m))
        assert specs[0]==specs[1]
        assert wire['messages'][-2]['content']==m.protocol.forced_final_prompt
        return response(payload(m.protocol.final_name,json.dumps(final_arguments('planner')),'fixed'))
    rig.handler=handler
    assert (await m.invoke_async()).structured_output.action_type.value=='NOOP'
    assert len(rig.calls)==m._rounds==3

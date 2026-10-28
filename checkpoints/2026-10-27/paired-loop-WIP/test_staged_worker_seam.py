"""No provider/VM. Preserve legacy composition while separating staged observation."""
import asyncio
from types import SimpleNamespace
from nebius_worker import NebiusCLIWorker


def test_legacy_turn_collects_after_measured_cli_and_removes_private_receipt():
    worker=object.__new__(NebiusCLIWorker);events=[];receipt=object()
    async def execute(arm,**kw):
        events.append('cli')
        return dict(_terminal_receipt=receipt,worker_active_seconds=3,receipt={'authored':True})
    def observe(arm,value):
        assert value is receipt;events.append('observe');return {'public':'authored'}
    worker.execute_cli=execute;worker.collect_observation=observe
    result=asyncio.run(worker.turn({},prompt='authored',session_id=None,remaining={'active_seconds':120}))
    assert events==['cli','observe'] and result['worker_active_seconds']==3
    assert '_terminal_receipt' not in result and result['public_observation']=={'public':'authored'}

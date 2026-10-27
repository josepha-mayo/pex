import asyncio
import pytest
from nebius_worker import NebiusCLIWorker

@pytest.mark.parametrize('fails',[False,True])
def test_revocation_is_confirmed_not_stop_requested(fails):
    worker=object.__new__(NebiusCLIWorker)
    class Context:
        def __init__(self,fail=False):self.fail=fail;self.exits=0
        def __exit__(self,*args):
            self.exits+=1
            if self.fail:raise RuntimeError('authored close failed')
    mcp=Context(fails);budget=Context()
    state={'stopped':False,'cm':mcp,'budget_cm':budget};worker.states={'pex':state}
    if fails:
        with pytest.raises(RuntimeError):asyncio.run(worker.stop({'condition':'pex'}))
    else:asyncio.run(worker.stop({'condition':'pex'}))
    assert state['stopped'] is True
    assert state['mcp_revoked'] is not fails
    assert budget.exits==1

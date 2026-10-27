import json
import subprocess
import sys
from pathlib import Path
import pytest
from remote_mcp import serve_remote,rpc,checked

class Remote:
    def __init__(self): self.calls=[]
    def run(self,command): self.calls.append(('run',command));return {'stdout':'authored','stderr':'','exit_code':0}
    def read(self,relative): self.calls.append(('read',relative));return 'authored bytes'
    def write(self,relative,content): self.calls.append(('write',relative,content));return {'written':relative}
    def list(self,relative='.'): self.calls.append(('list',relative));return []

@pytest.mark.parametrize('method,args',[('run',{'command':'not executed locally'}),('read',{'path':'a'}),('write',{'path':'a','text':'b'}),('list',{'path':'.'})])
def test_rpc_forwards_only_remote(method,args,tmp_path):
    remote=Remote()
    with serve_remote(remote,tmp_path/'private') as sock:
        assert 'result' in rpc(sock,method,args)
        assert sock.stat().st_mode&0o777==0o600
    assert len(remote.calls)==1 and not sock.exists()

@pytest.mark.parametrize('method,args',[('exec',{'command':'x'}),('run',{'command':'x','cwd':'/'}),('write',{'path':'a','text':123})])
def test_invalid_tool_arguments(method,args):
    with pytest.raises(ValueError):checked(method,args)

def test_actual_stdio_bridge(tmp_path):
    remote=Remote()
    with serve_remote(remote,tmp_path/'private') as sock:
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'run','arguments':{'command':'inert authored command'}}}]
        child=subprocess.run([sys.executable,str(Path(__file__).with_name('remote_mcp.py')),'--socket',str(sock)],input='\n'.join(map(json.dumps,messages))+'\n',text=True,capture_output=True,timeout=10,check=True)
        rows=[json.loads(x) for x in child.stdout.splitlines()]
        assert {t['name'] for t in rows[1]['result']['tools']}=={'run','read','write','list'}
        assert not rows[2]['result']['isError']
    assert remote.calls==[('run','inert authored command')]

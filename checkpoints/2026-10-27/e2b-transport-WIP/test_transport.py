"""Authored fake SDK only. These are not E2B or inference results."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from e2b_transport import PilotPool, RemoteWorker, TransportError, path, MAX_BYTES

class Files:
    def make_dir(self,*args,**kwargs): pass
    def read(self,*args,**kwargs): return iter([b'public task'])
    def write(self,*args,**kwargs): pass
    def list(self,*args,**kwargs): return [NS(name='task.py',type='file')]

class Handle:
    def __init__(self): self.killed=False
    def wait(self): return NS(exit_code=0)
    def kill(self): self.killed=True

class Commands:
    def run(self,command,**kwargs):
        self.command,self.kwargs=command,kwargs
        kwargs['on_stdout']('public output')
        self.handle=Handle()
        return self.handle

class Sandbox:
    def __init__(self,cpu=2,memory=4096,lifetime=900):
        start=datetime.now(timezone.utc)
        self.info=NS(cpu_count=cpu,memory_mb=memory,started_at=start,
            end_at=start+timedelta(seconds=lifetime),sandbox_id='fake-sandbox')
        self.files,self.commands=Files(),Commands()
        self.killed=False
    def get_info(self,**kwargs): return self.info
    def kill(self,**kwargs): self.killed=True
    def is_running(self,**kwargs): return not self.killed

class Api:
    def __init__(self): self.calls=[];self.instances=[];self.failure=False;self.alloc=(2,4096,900)
    def create(self,**kwargs):
        self.calls.append(kwargs)
        if self.failure:raise RuntimeError('fake request secret must not escape')
        s=Sandbox(*self.alloc);self.instances.append(s);return s
    def list(self,**kwargs):return NS(has_next=False)

class Tests(unittest.TestCase):
    def test_closed_gate_no_wire(self):
        api=Api()
        with self.assertRaises(TransportError): PilotPool(api,'synthetic').create('baseline')
        self.assertEqual(api.calls,[])
    def test_two_pristine_fixed_bound_and_finally(self):
        api=Api()
        with PilotPool(api,'synthetic',approved=True) as pool:
            a=pool.create('baseline');b=pool.create('supervised')
            self.assertIsNot(a._sandbox,b._sandbox)
            with self.assertRaises(TransportError):pool.create('baseline')
        self.assertTrue(all(s.killed for s in api.instances))
        for call in api.calls:
            self.assertEqual(call['timeout'],900);self.assertEqual(call['retries'],0)
            self.assertEqual(call['lifecycle'],{'on_timeout':'kill','auto_resume':False})
            self.assertNotIn('envs',call)
    def test_overallocation_killed(self):
        api=Api();api.alloc=(4,4096,900);pool=PilotPool(api,'synthetic',approved=True)
        with self.assertRaises(TransportError):pool.create('baseline')
        self.assertTrue(api.instances[0].killed)
        self.assertTrue(pool.uncertain)
    def test_pair_allocations_must_match(self):
        api=Api();pool=PilotPool(api,'synthetic',approved=True);pool.create('baseline')
        api.alloc=(2,512,900)
        with self.assertRaises(TransportError):pool.create('supervised')
        pool.close();self.assertTrue(all(x.killed for x in api.instances))
    def test_ambiguous_creation_never_retried(self):
        api=Api();api.failure=True;pool=PilotPool(api,'synthetic',approved=True)
        with self.assertRaises(TransportError) as caught:pool.create('baseline')
        self.assertNotIn('secret',str(caught.exception))
        with self.assertRaises(TransportError):pool.create('supervised')
        self.assertEqual(len(api.calls),1)
    def test_paths_and_content_bounds(self):
        for invalid in ('/etc/passwd','../private','a/../../private','a\x00b'):
            with self.assertRaises(TransportError):path(invalid)
        w=RemoteWorker(Sandbox(),{})
        with self.assertRaises(TransportError):w.write('huge','a'*(MAX_BYTES+1))
        self.assertEqual(w.read('task.py'),'public task')
        self.assertEqual(w.list(),[{'name':'task.py','type':'file'}])
    def test_remote_command_bounded_and_killed(self):
        s=Sandbox();w=RemoteWorker(s,{})
        result=w.run('printf hello',timeout=12)
        self.assertEqual(result,{'stdout':'public output','stderr':'','exit_code':0})
        self.assertTrue(s.commands.handle.killed)
        self.assertEqual(s.commands.kwargs['user'],'user')
        self.assertIn('timeout --signal=TERM --kill-after=1s 12s',s.commands.command)
    def test_lifetime_extension_rejected(self):
        api=Api();api.alloc=(2,4096,901)
        with self.assertRaises(TransportError):PilotPool(api,'synthetic',approved=True).create('baseline')
        self.assertTrue(api.instances[0].killed)

if __name__=='__main__': unittest.main()

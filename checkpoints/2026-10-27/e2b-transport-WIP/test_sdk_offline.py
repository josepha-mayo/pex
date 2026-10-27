"""Pinned actual SDK parser with authored events; zero network/sandbox calls."""
import unittest
from importlib.metadata import version
from types import SimpleNamespace as NS
from e2b.sandbox_sync.commands.command_handle import CommandHandle
from e2b import SandboxQuery
from protobuf import Oneof
from e2b_transport import RemoteWorker, TransportError, MAX_BYTES

class Commands:
    def __init__(self,code=0,output=b'actual SDK authored output',end=True):
        self.code,self.output,self.end,self.killed=code,output,end,False
    def run(self,cmd,*,cwd,user,background,timeout,request_timeout):
        assert background is True
        def events():
            yield NS(event=NS(event=Oneof('data',NS(output=Oneof('stdout',self.output)))))
            if self.end:
                yield NS(event=NS(event=Oneof('end',NS(exit_code=self.code,has_field=lambda _:False))))
        def kill():self.killed=True;return True
        return CommandHandle(pid=123,handle_kill=kill,events=events())

class Tests(unittest.TestCase):
    def setUp(self):self.assertEqual(version('e2b'),'2.61.0')
    def test_actual_wait_success(self):
        commands=Commands();w=RemoteWorker(NS(commands=commands),{})
        self.assertEqual(w.run('authored'),{'stdout':'actual SDK authored output','stderr':'','exit_code':0})
        self.assertTrue(commands.killed)
    def test_actual_nonzero_result(self):
        commands=Commands(code=7);w=RemoteWorker(NS(commands=commands),{})
        self.assertEqual(w.run('authored')['exit_code'],7);self.assertTrue(commands.killed)
    def test_actual_wait_overflow(self):
        commands=Commands(output=b'x'*(MAX_BYTES+1));w=RemoteWorker(NS(commands=commands),{})
        with self.assertRaises(TransportError):w.run('authored')
        self.assertTrue(commands.killed)
    def test_actual_missing_end_rejected(self):
        commands=Commands(end=False);w=RemoteWorker(NS(commands=commands),{})
        with self.assertRaises(TransportError):w.run('authored')
        self.assertTrue(commands.killed)
    def test_real_query(self):
        self.assertEqual(SandboxQuery(metadata={'pex_pilot':'authored'}).metadata,{'pex_pilot':'authored'})

if __name__=='__main__':unittest.main()

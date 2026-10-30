"""Authored receipt-only offline fixtures; not inference or capture evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import sqlite3

sys.path.insert(0, str(Path(__file__).parent))
import ledger_sidecar as s


class LedgerParserTests(unittest.TestCase):
    def worker(self):
        r = dict(call_id='authored-call', arm='baseline', request_sha256='1'*64,
                 response_sha256='2'*64, status=200, usage=dict(input_tokens=100, output_tokens=10, total_tokens=110))
        return ['authored-call', 'baseline', '1'*64, s.WORKER_RESERVE, 42000, 'settled_raw_wire', json.dumps(r)]

    def supervisor(self):
        r = dict(invocation_id='authored-call', route_fingerprint='3'*64, role='planner',
                 model_id='nvidia/nemotron-3-super-120b-a12b', outcome='succeeded',
                 dispatch_state='response_complete', attempts=1, http_status=200,
                 usage=dict(input_tokens=100, output_tokens=10, total_tokens=110))
        endpoint='https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions'
        routes=[('3'*64,endpoint,r['model_id'],'planner'),('4'*64,endpoint,r['model_id'],'verifier')]
        return ['authored-call','3'*64,s.SUPERVISOR_RESERVE,39000,'settled_raw_wire',json.dumps(r)],routes

    def test_worker_validated_only(self):
        self.assertEqual(s.worker_metrics([self.worker()])['baseline']['worker_requests'],1)
        self.assertEqual(s.worker_metrics([]),{})
        row=self.worker(); row[5]='reserved_uncertain';row[4]=row[3];row[6]=None
        self.assertEqual(s.worker_metrics([row]),{})
        self.assertEqual(s.worker_metrics([self.worker(),row]),{})

    def test_worker_identity_and_charge(self):
        for index,value in [(1,'private'),(2,'bad'),(3,1),(4,0),(5,'fake')]:
            row=self.worker();row[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):s.worker_metrics([row])
        row=self.worker();r=json.loads(row[-1]);r['usage']['total_tokens']=111;row[-1]=json.dumps(r)
        with self.assertRaises(ValueError):s.worker_metrics([row])

    def test_supervisor(self):
        row,routes=self.supervisor()
        self.assertEqual(s.supervisor_metrics([row],routes)['supervisor_requests'],1)
        self.assertEqual(s.supervisor_metrics([],routes),{})
        row[4]='uncertain';row[3]=row[2]
        self.assertEqual(s.supervisor_metrics([row],routes),{})

    def test_supervisor_receipt_rejected(self):
        for key,value in [('invocation_id','wrong'),('attempts',2),('http_status',500),('role','verifier')]:
            row,routes=self.supervisor();r=json.loads(row[-1]);r[key]=value;row[-1]=json.dumps(r)
            with self.subTest(key=key),self.assertRaises(ValueError):s.supervisor_metrics([row],routes)

    def test_terminal_needs_bound_launcher_not_report_alone(self):
        with tempfile.TemporaryDirectory(prefix='pex-sidecar-authored-') as d:
            root=Path(d);(root/'run').mkdir();report=json.dumps({'config_sha256':'1'*64}).encode()
            (root/'run/report.json').write_bytes(report)
            self.assertIsNone(s.terminal_record(root,'authored-test','1'*64))
            value=dict(schema='pex.staged.launcher-terminal.v1',run_id='authored-test',config_sha256='1'*64,
                status='inconclusive',comparison_complete=False,cleanup_confirmed=False,failure_category='TimeoutError',
                report_sha256=s.sha(report))
            (root/'launcher-terminal.json').write_text(json.dumps(value))
            fields,_=s.terminal_record(root,'authored-test','1'*64)
            self.assertEqual(fields['failure_category'],'timeout');self.assertFalse(fields['cleanup_confirmed'])
            self.assertEqual(fields['terminal'],'wall_budget_terminal_inconclusive')
            for category,expected in [('WorkerBudgetExhausted','worker_budget_terminal_inconclusive'),
                    ('AdmissionRefused','admission_refused'),('ProtocolInconclusive','protocol_inconclusive'),
                    ('UnexpectedError','outcome_inconclusive'),(None,'outcome_inconclusive')]:
                value['failure_category']=category;(root/'launcher-terminal.json').write_text(json.dumps(value))
                self.assertEqual(s.terminal_record(root,'authored-test','1'*64)[0]['terminal'],expected)
            value['cleanup_errors']=['cleanup_unconfirmed'];(root/'launcher-terminal.json').write_text(json.dumps(value))
            self.assertEqual(s.terminal_record(root,'authored-test','1'*64)[0]['terminal'],'cleanup_unconfirmed')
            value['config_sha256']='2'*64;(root/'launcher-terminal.json').write_text(json.dumps(value))
            with self.assertRaises(ValueError):s.terminal_record(root,'authored-test','1'*64)

    def test_actual_sqlite_snapshot_is_read_only(self):
        with tempfile.TemporaryDirectory(prefix='pex-sidecar-authored-db-') as d:
            path=Path(d)/'fixture.sqlite'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE config (digest TEXT, ir INTEGER, outr INTEGER, input_bound INTEGER, output_bound INTEGER)')
                db.execute('INSERT INTO config VALUES (?,300,1200,1048576,4096)',('a'*64,))
                db.execute('CREATE TABLE calls (id TEXT,arm TEXT,request_sha TEXT,reserved INTEGER,charged INTEGER,state TEXT,receipt TEXT)')
                db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',self.worker())
            before=path.read_bytes()
            metrics,proof=s.snapshot_db(path,config_sha='a'*64,worker=True)
            self.assertEqual(metrics['baseline']['worker_requests'],1)
            self.assertEqual(before,path.read_bytes())
            self.assertEqual(proof['artifact_sha256_after_transaction'],s.sha(before))
            with self.assertRaises(ValueError):s.snapshot_db(path,config_sha='b'*64,worker=True)


if __name__=='__main__':unittest.main()

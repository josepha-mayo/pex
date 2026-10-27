import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from opencode_cli import completed_turn
from opencode_v2_receipt import completed_turn_v2,prior_sequence

class ReceiptTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'cli.sqlite'
  self.raw=(json.dumps({'type':'text','sessionID':'s','part':{'sessionID':'s','messageID':'a','text':'authored'}})+'\n').encode()
  self.payload={'finish':'stop','rawFinish':'stop','time':{'completed':10},'content':[{'type':'text','text':'authored'}]}
  with sqlite3.connect(self.db) as c:
   c.executescript('CREATE TABLE session_v2(id,version,idle_outcome);CREATE TABLE session_message(id,type,seq,data,session_id);CREATE TABLE session_pending(session_id);')
   c.execute("INSERT INTO session_v2 VALUES ('s','2.1.4','succeeded')")
   c.executemany('INSERT INTO session_message VALUES (?,?,?,?,?)',[('u','user',1,json.dumps({'text':'exact prompt'}),'s'),('a','assistant',2,json.dumps(self.payload),'s'),('i','idle',3,json.dumps({'outcome':'succeeded'}),'s')])
 def tearDown(self):self.tmp.cleanup()
 def parse(self,**kw):return completed_turn_v2(self.raw,exit_code=0,database=self.db,prompt='exact prompt',after_sequence=0,**kw)
 def sql(self,query,args=()):
  with sqlite3.connect(self.db) as c:c.execute(query,args)
 def test_complete_bound_terminal(self):
  self.assertEqual(self.parse().messages,('authored',));self.assertEqual(prior_sequence(self.db,'s'),3)
 def test_no_legacy_step_check_downgrade(self):
  with self.assertRaises(ValueError):completed_turn(self.raw,exit_code=0)
 def test_duplicate_or_quoted_prompt_refused(self):
  self.sql("UPDATE session_message SET data=? WHERE type='user'",(json.dumps({'text':'"exact prompt"'}),))
  with self.assertRaisesRegex(ValueError,'prompt'):self.parse()
 def test_missing_idle_and_pending_work_refused(self):
  self.sql("DELETE FROM session_message WHERE type='idle'")
  with self.assertRaises(ValueError):self.parse()
 def test_pending_work_refused(self):
  self.sql("INSERT INTO session_pending VALUES ('s')")
  with self.assertRaisesRegex(ValueError,'pending'):self.parse()
 def test_changed_session_and_old_receipt_refused(self):
  with self.assertRaises(ValueError):self.parse(expected_session='other')
  with self.assertRaises(ValueError):completed_turn_v2(self.raw,exit_code=0,database=self.db,prompt='exact prompt',after_sequence=3)
 def test_failed_finish_and_boolean_completed_refused(self):
  for edit in ({'finish':'length'},{'time':{'completed':True}}):
   value={**self.payload,**edit};self.sql("UPDATE session_message SET data=? WHERE type='assistant'",(json.dumps(value),))
   with self.assertRaises(ValueError):self.parse()
 def test_output_must_match_committed_text(self):
  self.raw=self.raw.replace(b'authored',b'changed')
  with self.assertRaises(ValueError):self.parse()
 def test_new_turn_requires_fresh_profile(self):
  with self.assertRaises(ValueError):prior_sequence(self.db)
 def test_unexpected_event_and_nonzero_exit_refused(self):
  with self.assertRaises(ValueError):completed_turn_v2(self.raw,exit_code=1,database=self.db,prompt='exact prompt',after_sequence=0)
  self.raw=self.raw.replace(b'"type": "text"',b'"type": "unknown"')
  with self.assertRaises(ValueError):self.parse()
if __name__=='__main__':unittest.main()

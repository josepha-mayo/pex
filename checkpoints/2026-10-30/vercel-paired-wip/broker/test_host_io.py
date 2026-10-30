"""Offline-only file safety and atomicity tests; never provider calls."""
import base64,importlib.util,json,os,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('host_io',Path(__file__).with_name('host_io.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def enc(v):return base64.b64encode(json.dumps(v).encode()).decode()
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def call(self,v):return m.entry(str(self.root),'direct',enc(v))
 def test_empty_and_roundtrip(self):
  self.assertIsNone(self.call({'op':'next','sequence':1}))
  b=b'{"hello":"request"}';(self.root/'requests/000001.json').write_bytes(b)
  self.assertEqual(self.call({'op':'next','sequence':1})['request_sha256'],m.digest(b))
  v={'result':'hello'};h=self.call({'op':'put','name':'responses/000001.json','value':v})
  self.assertEqual(h['sha256'],m.digest(m.wire(v)))
 def test_immutable(self):
  v={'op':'put','name':'owned-baseline.json','value':{}}
  self.call(v)
  with self.assertRaises(FileExistsError):self.call(v)
 def test_restart_uncertain(self):
  self.call({'op':'put','name':'journal/000001.json','value':{}})
  with self.assertRaisesRegex(ValueError,'prior_attempt'):self.call({'op':'next','sequence':1})
 def test_traversal(self):
  for p in ['../x','receipts/../../x','responses/1.json','owned-third.json']:
   with self.assertRaises(ValueError):self.call({'op':'put','name':p,'value':{}})
 def test_request_symlink(self):
  self.call({'op':'next','sequence':1});target=self.root/'target';target.write_text('{}');(self.root/'requests/000001.json').symlink_to(target)
  with self.assertRaises(OSError):self.call({'op':'next','sequence':1})
 def test_child_symlink(self):
  (self.root/'requests').symlink_to(self.root)
  with self.assertRaises(ValueError):self.call({'op':'next','sequence':1})
 def test_root_permissions(self):
  self.root.chmod(0o755)
  with self.assertRaises(ValueError):self.call({'op':'next','sequence':1})
 def test_chunked_payload(self):
  value={'text':'x'*500000};e=enc({'op':'put','name':'receipts/000001-bundle.json','value':value})
  for i in range(0,len(e),60000):m.entry(str(self.root),'begin'if i==0 else'append',e[i:i+60000])
  out=m.entry(str(self.root),'finish','')
  self.assertEqual(out['sha256'],m.digest(m.wire(value)));self.assertFalse((self.root/'.bridge-input').exists())
 def test_chunk_restart_failclosed(self):
  m.entry(str(self.root),'begin','e30=')
  with self.assertRaises(FileExistsError):m.entry(str(self.root),'begin','e30=')
if __name__=='__main__':unittest.main()

"""Emit reviewed functions.exec source; never invokes provider or executes output."""
import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('boot',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
d=Path(__file__).parent;core=(d/'core.mjs').read_text();driver=(d/'driver.js').read_text();boot=json.loads(a.boot.read_text())
assert boot['config']['producer_sha256']==hashlib.sha256((d/'core.mjs').read_bytes()).hexdigest()
assert driver.count('=CONFIGURATION;')==1
source='// @exec: {"yield_time_ms": 1000, "max_output_tokens": 1000}\n'+core.replace('export function ','function ')+driver.replace('=CONFIGURATION;','='+json.dumps(boot,separators=(',',':'))+';')
a.output.write_text(source)
print(hashlib.sha256(source.encode()).hexdigest(),a.output)

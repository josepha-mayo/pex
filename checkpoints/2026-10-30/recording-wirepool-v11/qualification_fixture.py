"""Explicit AUTHORED local recorder qualification; no network, model or benchmark.

Root starts the dedicated fixture native session and capture. This script only
creates authored fixture evidence after capture-ready, exercises the exact
verifier/writer, then stops that fixture capture. It cannot target a real run.
"""
import argparse
import json
import os
from pathlib import Path
import time

from record_support import utc,canonical
from reviewed_excerpts import drain_approved
from safe_feed_writer import SafeFeedWriter
from test_supervisor_excerpts import SupervisorExcerptTests


def run(root):
    root=Path(root).absolute()
    if root.resolve()!=root or not root.name.startswith('authored-recorder-'):
        raise ValueError('authored_fixture_namespace_only')
    session=root/'recording-live';deadline=time.monotonic()+300
    while not (session/'video/capture-ready.json').exists():
        if time.monotonic()>deadline or (session/'STOP_CAPTURE').exists():raise ValueError('fixture_capture_not_ready')
        time.sleep(.1)
    started=json.loads((session/'display/follower-start.json').read_text())
    capture=json.loads((session/'video/capture-start.json').read_text())
    if (started.get('authored_fixture') is not True or started.get('run_id')!=root.name
            or capture.get('qualification')!='authored_fixture_window_capture_NOT_REAL_INFERENCE'
            or capture.get('max_seconds',100)>30 or (root/'pair.json').exists()):
        raise ValueError('explicit_authored_fixture_required')
    # Fixtures are generated NOW, not replayed. Their text and approvals are
    # visibly AUTHORED; this is not automatic approval of actual model prose.
    fixture=SupervisorExcerptTests();fixture.external_fixture_root=root;fixture.setUp()
    fixture.install_monitor('verifier')
    # The source capture observation must follow this fresh follower. The test
    # builder uses now-1s, and root's capture-ready already follows startup.
    fixture.f.manifest['reviewed_utc']=utc();fixture.f.put(fixture.f.selection,fixture.f.manifest)
    with SafeFeedWriter(run_id=root.name,feed_path=root/'safe-display.jsonl',
                        follower_start_path=session/'display/follower-start.json') as writer:
        drain_approved(root,writer,config_sha=fixture.f.config,seen=set(),now=time.time())
        if writer.seq!=3:raise ValueError('three_authored_excerpts_required')
    time.sleep(5)
    receipt={'schema':'pex-authored-recorder-qualification/v1','run_id':root.name,'authored_only':True,
        'real_model_calls':0,'observed_utc':utc(),'expected_excerpts':['worker','planner','verifier'],
        'benchmark_terminal_fabricated':False,'qualification':'fixture_only_not_inference'}
    (root/'fixture-result.json').write_text(canonical(receipt)+'\n')
    fd=os.open(session/'STOP_CAPTURE',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:os.write(fd,b'AUTHORED FIXTURE QUALIFICATION COMPLETE - NOT REAL INFERENCE\n');os.fsync(fd)
    finally:os.close(fd)
    fixture.tearDown()
    print('Authored worker/planner/verifier fixture displayed; owned fixture capture stop requested. NOT REAL INFERENCE.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-prefix',required=True);args=p.parse_args()
    os.umask(0o077)
    try:run(args.run_prefix)
    except Exception:
        print('Authored fixture refused; no provider or benchmark execution.');raise SystemExit(2)

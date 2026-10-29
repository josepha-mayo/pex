"""Invented split-storage fixtures only; no provider calls or real benchmark."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import ledger_sidecar as s
import record_support as r
from safe_feed_writer import SafeFeedWriter


def paths(tmp_path):
    run_id='authored-split-not-inference'
    actual=tmp_path/'source'/run_id;display=tmp_path/'display'/run_id
    actual.mkdir(parents=True);display.mkdir(parents=True)
    (actual/'pair.json').write_text(json.dumps({'profile':{'worker_output_per_call':16384}}))
    config=s.sha((actual/'pair.json').read_bytes())
    start=display/'recording-live/display/follower-start.json';start.parent.mkdir(parents=True)
    start.write_text(json.dumps({'schema':'pex-recorder-follower/v1','run_id':run_id,
        'qualification':'setup_only_no_inference','started_utc':r.utc(),
        'feed_path_sha256':r.sha(str((display/'safe-display.jsonl').resolve()).encode()),
        'source_code_sha256':r.sha(Path(r.__file__).read_bytes())}))
    args=SimpleNamespace(run_prefix=str(actual),display_prefix=str(display),run_id=run_id,
        config_sha256=config,follower_start=str(start),max_seconds=10,reviewed_excerpts=False)
    return actual,display,start,args


def test_source_ledger_and_shared_display_are_distinct(tmp_path):
    actual,display,start,args=paths(tmp_path)
    # A display-side decoy must never become the task/config authority.
    (display/'pair.json').write_text('not the actual configuration')
    (actual/'launcher-admission.json').write_text(json.dumps({'run_id':args.run_id,'config_sha256':args.config_sha256}))
    def finish(_):
        (actual/'launcher-terminal.json').write_text(json.dumps({
            'schema':'pex.staged.launcher-terminal.v1','run_id':args.run_id,'config_sha256':args.config_sha256,
            'status':'inconclusive','comparison_complete':False,'cleanup_confirmed':True,
            'failure_category':'AdmissionRefused'}))
    with patch.object(s.time,'sleep',side_effect=finish):assert s.run(args)==0
    records=[json.loads(line) for line in (display/'safe-display.jsonl').read_text().splitlines()]
    assert [x['event'] for x in records]==['setup','run_terminal']
    assert not (actual/'safe-display.jsonl').exists()
    assert (display/'recorder-provenance/setup-binding.json').exists()
    assert not (display/'launcher-terminal.json').exists()


@pytest.mark.parametrize('bad',['wrong_name','wrong_follower','symlink'])
def test_display_binding_cannot_be_redirected(tmp_path,bad):
    actual,display,start,args=paths(tmp_path)
    if bad=='wrong_name':args.display_prefix=str(tmp_path)
    elif bad=='wrong_follower':args.follower_start=str(actual/'other-start.json')
    else:
        link=tmp_path/'link';link.symlink_to(display,target_is_directory=True);args.display_prefix=str(link)
    with pytest.raises(ValueError):s.run(args)
    assert not (display/'safe-display.jsonl').exists()


def test_actual_terminal_refuses_excerpt_even_when_shared_terminal_absent(tmp_path):
    actual,display,start,args=paths(tmp_path)
    with SafeFeedWriter(run_id=args.run_id,feed_path=display/'safe-display.jsonl',
                        follower_start_path=start,terminal_path=actual/'launcher-terminal.json') as writer:
        writer.reviewed_excerpts_enabled=True
        (actual/'launcher-terminal.json').write_text('{}')
        with pytest.raises(ValueError,match='feed_closed_or_terminal'):
            writer.emit_reviewed_excerpt({},approvals=set())
        assert not (display/'launcher-terminal.json').exists()
        assert (display/'safe-display.jsonl').read_bytes()==b''


def test_shared_review_inbox_reads_only_actual_source_receipt(tmp_path):
    from test_reviewed_excerpts import ReviewedExcerptTests
    from reviewed_excerpts import drain_approved
    fixture=ReviewedExcerptTests();fixture.setUp()
    try:
        display=tmp_path/fixture.root.name;display.mkdir()
        fixture.inbox.rename(display/'reviewed-excerpts-inbox')
        (fixture.root/'reviewed-excerpts.json').rename(display/'reviewed-excerpts.json')
        seen=set();received=[]
        writer=SimpleNamespace(run_id=fixture.root.name,started=fixture.started,
            emit_reviewed_excerpt=lambda fields,approvals:received.append(fields))
        drain_approved(fixture.root,writer,config_sha=fixture.config,seen=seen,
                       now=fixture.now,display_root=display)
        assert len(received)==1 and received[0]['model_excerpt']==fixture.text
        (fixture.root/'launcher-terminal.json').write_text('{}')
        drain_approved(fixture.root,writer,config_sha=fixture.config,seen=set(),
                       now=fixture.now,display_root=display)
        assert len(received)==1
    finally:fixture.tearDown()

"""SIMULATED regression checks. No provider, VM, credentials or native capture."""
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import record_support as r
from safe_feed_writer import SafeFeedWriter


@pytest.mark.parametrize('run_id', ['authored-recorder-asyncpool-8', 'authored-test-not-inference'])
def test_known_authored_namespace_cannot_start_live_display(tmp_path, run_id):
    out = tmp_path / 'display'
    with pytest.raises(ValueError, match='authored_fixture_flag_required'):
        r.follow(SimpleNamespace(run_id=run_id, authored_fixture=False,
                                feed=str(tmp_path / 'feed'), output_dir=str(out)))
    assert not out.exists()
    with pytest.raises(ValueError, match='authored_fixture_flag_required'):
        r.EvidenceDisplay(run_id)


@pytest.mark.parametrize('flag', [False, None, 1, 'true'])
def test_writer_refuses_missing_or_malformed_fixture_flag_before_creating_feed(tmp_path, flag):
    run_id = 'authored-recorder-asyncpool-8'
    feed = tmp_path / 'safe-display.jsonl'
    start = tmp_path / 'follower-start.json'
    start.write_text(json.dumps({'schema': 'pex-recorder-follower/v1', 'run_id': run_id,
        'qualification': 'setup_only_no_inference', 'authored_fixture': flag,
        'started_utc': r.utc(), 'feed_path_sha256': r.sha(str(feed.resolve()).encode()),
        'source_code_sha256': r.sha(Path(r.__file__).read_bytes())}))
    with pytest.raises(ValueError, match='authored_fixture'):
        SafeFeedWriter(run_id=run_id, feed_path=feed, follower_start_path=start)
    assert not feed.exists()


def test_fixture_excerpt_never_validates_as_live_even_with_exact_approval():
    run_id = 'authored-recorder-asyncpool-8'
    text = 'SIMULATED / AUTHORED EXCERPT - NOT A MODEL RESPONSE'
    row = dict(schema=r.SCHEMA, run_id=run_id, seq=1, at_utc=r.utc(),
        event='worker_response', qualification='live_current_run_reviewed_excerpt',
        source_sha256='1'*64, model_excerpt=text, model_excerpt_sha256=r.sha(text.encode()),
        reviewed_utc=r.utc(), excerpt_origin='worker_json_assistant_content')
    approvals = {(run_id, row['source_sha256'], row['model_excerpt_sha256'])}
    for fixture in (False, True):
        with pytest.raises(ValueError):
            r.validate(row, run_id=run_id, expected_seq=1, not_before=time.time()-2,
                       now=time.time(), approvals=approvals, authored_fixture=fixture)
    row['qualification'] = 'authored_fixture_reviewed_excerpt'
    assert r.validate(row, run_id=run_id, expected_seq=1, not_before=time.time()-2,
                      now=time.time(), approvals=approvals, authored_fixture=True) == row


def test_actual_asyncpool_id_is_accepted_as_identity_only_no_display():
    r.validate_fixture_mode('asyncpool-staged-pair-20261030-02', False)
    with pytest.raises(ValueError, match='authored_fixture_namespace'):
        r.validate_fixture_mode('asyncpool-staged-pair-20261030-02', True)


def test_native_wrapper_rejects_authored_live_mode_before_display_or_capture(tmp_path):
    root = tmp_path / 'authored-recorder-asyncpool-8'
    proc = subprocess.run([sys.executable, str(Path(r.__file__).with_name('native_session.py')),
        '--run-prefix', str(root), '--run-id', root.name, '--window-id', '123'],
        capture_output=True, text=True, timeout=3)
    assert proc.returncode == 2
    assert 'LIVE CURRENT RUN' not in proc.stdout
    assert not root.exists()

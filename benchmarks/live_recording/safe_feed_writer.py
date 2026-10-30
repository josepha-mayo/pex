"""Owner-fed metadata sink only: no provider/DB/raw-artifact access or events invented.

Root must review the calling producer and its current-run evidence derivations.
Construct only after the real follower starts. Creating this writer does not
assert admission, inference, cleanup or any benchmark outcome.
"""
import json
import os
from pathlib import Path
import threading
import time

from record_support import MAX_LINE, SCHEMA, canonical, sha, timestamp, utc, validate, validate_fixture_mode


class SafeFeedWriter:
    def __init__(self, *, run_id, feed_path, follower_start_path, terminal_path=None):
        self.run_id = run_id
        self.path = Path(feed_path)
        self.terminal_path = Path(terminal_path) if terminal_path is not None else self.path.parent / 'launcher-terminal.json'
        if terminal_path is not None and (self.terminal_path.name != 'launcher-terminal.json'
                or self.terminal_path.parent.name != run_id
                or self.terminal_path.resolve() != self.terminal_path.absolute()):
            raise ValueError('exact_actual_terminal_path_required')
        start_path = Path(follower_start_path)
        if start_path.is_symlink() or start_path.stat().st_size > MAX_LINE:
            raise ValueError('invalid_follower_start')
        start = json.loads(start_path.read_text())
        if (type(start) is not dict or start.get('schema') != 'pex-recorder-follower/v1'
                or start.get('run_id') != run_id or start.get('qualification') != 'setup_only_no_inference'
                or start.get('feed_path_sha256') != sha(str(self.path.resolve()).encode())
                or start.get('source_code_sha256') != sha(Path(__file__).with_name('record_support.py').read_bytes())):
            raise ValueError('wrong_follower_binding')
        self.started = timestamp(start['started_utc'])
        self.authored_fixture=start.get('authored_fixture',False)
        validate_fixture_mode(run_id, self.authored_fixture)
        self.reviewed_excerpts_enabled = (start.get('excerpt_mode') == 'root_reviewed_worker_wire' and
            start.get('approvals_path_sha256') == sha(str((self.path.parent / 'reviewed-excerpts.json').resolve()).encode()))
        if not 0 <= time.time() - self.started <= 3600:
            raise ValueError('stale_follower_start')
        self.seq = 0
        self.terminal = False
        self.lock = threading.Lock()
        self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.fchmod(self.fd, 0o600)

    def emit(self, *, event, qualification, source_sha256, **metadata):
        """Append only caller-supplied evidence. Unknown/unproven counts stay absent.

        source_sha256 identifies the owner's saved current measurement manifest,
        not a fabricated event template. No model/tool excerpt is allowed here.
        """
        with self.lock:
            if self.fd is None or self.terminal:
                raise ValueError('feed_closed_or_terminal')
            if any(k in {'schema', 'run_id', 'seq', 'at_utc', 'model_excerpt', 'model_excerpt_sha256'} for k in metadata):
                raise ValueError('reserved_or_prose_field')
            record = dict(metadata, schema=SCHEMA, run_id=self.run_id, seq=self.seq + 1,
                          at_utc=utc(), event=event, qualification=qualification, source_sha256=source_sha256)
            record = validate(record, run_id=self.run_id, expected_seq=self.seq + 1,
                              not_before=self.started, now=time.time(), authored_fixture=self.authored_fixture)
            raw = (canonical(record) + '\n').encode()
            if len(raw) > MAX_LINE:
                raise ValueError('oversized_record')
            done = 0
            while done < len(raw):
                size = os.write(self.fd, raw[done:])
                if not size:
                    raise OSError('short_feed_write')
                done += size
            os.fsync(self.fd)
            self.seq += 1
            self.terminal = event == 'run_terminal'
            return record

    def close(self):
        with self.lock:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None

    def emit_reviewed_excerpt(self, fields, *, approvals):
        """Called only after private artifact/receipt verification by one owner.

        Metadata emit() still rejects prose. No second sequence writer, replay,
        or known-after-terminal injection is permitted.
        """
        with self.lock:
            if not self.reviewed_excerpts_enabled:
                raise ValueError('follower_excerpt_opt_in_required')
            if self.fd is None or self.terminal or self.terminal_path.exists():
                raise ValueError('feed_closed_or_terminal')
            base={'arm','source_sha256','model_excerpt','model_excerpt_sha256','reviewed_utc','excerpt_origin'}
            monitor='supervisor_role' in fields
            if set(fields) != base|({'supervisor_role','source_captured_utc'} if monitor else set()):
                raise ValueError('verified_excerpt_fields_required')
            record = dict(fields, schema=SCHEMA, run_id=self.run_id, seq=self.seq + 1,
                          at_utc=utc(), event='supervisor_response' if monitor else 'worker_response',
                          qualification='authored_fixture_reviewed_excerpt' if self.authored_fixture else 'live_current_run_reviewed_excerpt')
            record = validate(record, run_id=self.run_id, expected_seq=self.seq + 1,
                              not_before=self.started, now=time.time(), approvals=approvals,authored_fixture=self.authored_fixture)
            if timestamp(fields['reviewed_utc']) < self.started:
                raise ValueError('historical_review_refused')
            raw = (canonical(record) + '\n').encode()
            if len(raw) > MAX_LINE: raise ValueError('oversized_record')
            if self.terminal_path.exists():
                raise ValueError('after_terminal_excerpt_refused')
            done = 0
            while done < len(raw):
                n = os.write(self.fd, raw[done:])
                if not n: raise OSError('short_feed_write')
                done += n
            os.fsync(self.fd); self.seq += 1
            return record

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

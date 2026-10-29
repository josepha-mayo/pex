"""Tiny authored tests only. No inference, actual recording, UI or network."""
import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).parent))
from safe_feed_writer import SafeFeedWriter

spec = importlib.util.spec_from_file_location('recorder', Path(__file__).with_name('record_support.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


class SafeFeedTests(unittest.TestCase):
    def setUp(self):
        self.now = r.timestamp('2026-10-29T09:00:00Z')
        self.value = {'schema': r.SCHEMA, 'run_id': 'authored-test-not-inference', 'seq': 1,
                      'at_utc': '2026-10-29T09:00:00Z', 'event': 'waiting',
                      'qualification': 'setup_only_no_inference', 'source_sha256': '1' * 64}

    def check(self, value=None, approvals=frozenset()):
        return r.validate(self.value if value is None else value, run_id=self.value['run_id'],
                          expected_seq=1, not_before=self.now - 1, now=self.now, approvals=approvals)

    def test_minimal(self):
        self.assertEqual(self.check(), self.value)

    def test_unknown_or_secret_fields_refused(self):
        for key in ('api_key', 'token', 'raw_error', 'prompt', 'private_path', 'sandbox_id', 'grade', 'stdout'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.value, **{key: 'DO_NOT_DISPLAY'}))

    def test_wrong_run_and_sequence(self):
        for key, value in [('run_id', 'historical-run'), ('seq', 2), ('seq', True), ('schema', 'wrong')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.value, **{key: value}))

    def test_bad_enum_does_not_become_text(self):
        for key in r.ENUMS:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(dict(self.value, **{key: 'DO_NOT_DISPLAY'}))

    def test_timestamp_freshness(self):
        for ts in ('2026-10-28T09:00:00Z', '2026-10-29T09:00:06Z', 'bad', 123):
            with self.subTest(ts=ts), self.assertRaises(ValueError):
                self.check(dict(self.value, at_utc=ts))

    def test_counts_require_validation(self):
        with self.assertRaises(ValueError): self.check(dict(self.value, worker_requests=1))
        for val in (True, -1, 1.5, 10**9 + 1, 'secret'):
            with self.subTest(val=val), self.assertRaises(ValueError):
                self.check(dict(self.value, worker_requests=val, counts_validated=True))
        self.check(dict(self.value, worker_requests=1, counts_validated=True))

    def test_nonfinite_overhead(self):
        for val in (float('nan'), float('inf'), -1, True, 86401):
            with self.subTest(val=val), self.assertRaises(ValueError):
                self.check(dict(self.value, supervisor_seconds=val))

    def test_excerpt_exact_approval_and_lineage(self):
        text = 'AUTHORED FIXTURE ONLY — NOT A MODEL RESPONSE'
        value = dict(self.value, event='worker_response', qualification='live_current_run_reviewed_excerpt',
                     model_excerpt=text, model_excerpt_sha256=r.sha(text.encode()))
        approval = {(value['run_id'], value['source_sha256'], value['model_excerpt_sha256'])}
        with self.assertRaises(ValueError): self.check(value)
        self.assertEqual(self.check(value, approval)['model_excerpt'], text)
        with self.assertRaises(ValueError): self.check(dict(value, model_excerpt=text + '.'), approval)
        with self.assertRaises(ValueError): self.check(dict(value, source_sha256='2' * 64), approval)

    def test_excerpt_terminal_controls_refused_even_if_approved(self):
        for text in ('a\x1bb', 'a\x00b', 'a\u202eb', 'a\x85b'):
            value = dict(self.value, event='worker_response', qualification='live_current_run_reviewed_excerpt',
                         model_excerpt=text, model_excerpt_sha256=r.sha(text.encode()))
            approval = {(value['run_id'], value['source_sha256'], value['model_excerpt_sha256'])}
            with self.subTest(text=repr(text)), self.assertRaises(ValueError): self.check(value, approval)

    def test_window_command_has_no_desktop_fallback(self):
        command = r.capture_command(1234, ':AUTHORED-TEST-NOT-USED', Path('fixture.mkv'), 600, 960, 600)
        self.assertEqual(command[command.index('-window_id') + 1], '1234')
        self.assertEqual(command[command.index('-fs') + 1], str(30 * 1024 * 1024))
        self.assertIn('-n', command)
        for wid in (0, -1, 2**32, True):
            with self.subTest(wid=wid), self.assertRaises(ValueError):
                r.capture_command(wid, ':unused', Path('fixture.mkv'), 1, 960, 600)

    def test_stale_feed_refused_without_starting(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(prefix='pex-recorder-test-') as name:
            root = Path(name); feed = root / 'feed.jsonl'; feed.write_text('{}\n')
            with self.assertRaises(ValueError):
                r.follow(SimpleNamespace(run_id='test', feed=str(feed), output_dir=str(root / 'out')))
            self.assertFalse((root / 'out').exists())

    def test_hash_field_rejects_secret_or_malformed(self):
        for value in ('SECRET', 'g' * 64, '1' * 63, 1):
            with self.subTest(value=value), self.assertRaises(ValueError): self.check(dict(self.value, source_sha256=value))


class SafeFeedWriterTests(unittest.TestCase):
    def start(self, root):
        feed = root / 'authored-fixture-feed.jsonl'
        start = root / 'follower-start.json'
        start.write_text(json.dumps({'schema': 'pex-recorder-follower/v1',
            'run_id': 'authored-test-not-inference', 'qualification': 'setup_only_no_inference',
            'started_utc': r.utc(), 'feed_path_sha256': r.sha(str(feed.resolve()).encode()),
            'source_code_sha256': r.sha(Path(r.__file__).read_bytes())}))
        return feed, start

    def test_append_exact_metadata_and_no_implicit_events(self):
        with tempfile.TemporaryDirectory(prefix='pex-writer-authored-') as name:
            root = Path(name); feed, start = self.start(root)
            with SafeFeedWriter(run_id='authored-test-not-inference', feed_path=feed, follower_start_path=start) as writer:
                self.assertEqual(feed.read_bytes(), b'')
                self.assertEqual(feed.stat().st_mode & 0o777, 0o600)
                row = writer.emit(event='waiting', qualification='setup_only_no_inference', source_sha256='1' * 64)
                self.assertEqual(json.loads(feed.read_text()), row)
                self.assertNotIn('worker_requests', row)
                writer.emit(event='run_terminal', qualification='terminal_inconclusive', source_sha256='2' * 64,
                            terminal='admission_refused')
                with self.assertRaises(ValueError):
                    writer.emit(event='waiting', qualification='setup_only_no_inference', source_sha256='1' * 64)
            rows = [json.loads(x) for x in feed.read_text().splitlines()]
            self.assertEqual([x['seq'] for x in rows], [1, 2])

    def test_no_overwrite_bad_binding_or_prose(self):
        with tempfile.TemporaryDirectory(prefix='pex-writer-authored-') as name:
            root = Path(name); feed, start = self.start(root)
            with self.assertRaises(ValueError):
                SafeFeedWriter(run_id='wrong', feed_path=feed, follower_start_path=start)
            with SafeFeedWriter(run_id='authored-test-not-inference', feed_path=feed, follower_start_path=start) as writer:
                with self.assertRaises(FileExistsError):
                    SafeFeedWriter(run_id='authored-test-not-inference', feed_path=feed, follower_start_path=start)
                for extra in ({'model_excerpt': 'AUTHORED TEST ONLY'}, {'seq': 8}, {'api_key': 'DO_NOT_DISPLAY'}, {'worker_requests': 0}):
                    with self.subTest(extra=extra), self.assertRaises(ValueError):
                        writer.emit(event='waiting', qualification='setup_only_no_inference', source_sha256='1' * 64, **extra)
                self.assertEqual(feed.read_bytes(), b'')


if __name__ == '__main__':
    unittest.main()

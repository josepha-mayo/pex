"""Run ONLY inside isolated evaluation after worker revocation, or on authored reference."""
import contextlib
import io
import json
from pathlib import Path
import unittest

if __name__ == '__main__':
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_acceptance.py')
        result = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
    failed = len(result.failures) + len(result.errors)
    summary = {'schema': 'pex.asyncpool-grade.v1', 'checks': result.testsRun,
               'passed': result.testsRun - failed, 'failed': failed,
               'complete': result.testsRun == 8, 'all_pass': result.wasSuccessful() and result.testsRun == 8}
    print(json.dumps(summary, sort_keys=True))
    raise SystemExit(0 if summary['all_pass'] else 1)

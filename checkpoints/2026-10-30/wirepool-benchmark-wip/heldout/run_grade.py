"""Post-revocation isolated candidate grader; local use for authored code ONLY."""
import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import unittest


class GroupResult(unittest.TextTestResult):
    """A test with several failed subcases is one failed contract group."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failed_groups = set()

    def addError(self, test, error):
        self.failed_groups.add(getattr(test, 'test_case', test).id())
        super().addError(test, error)

    def addFailure(self, test, error):
        self.failed_groups.add(getattr(test, 'test_case', test).id())
        super().addFailure(test, error)

    def addSubTest(self, test, subtest, error):
        if error is not None:
            self.failed_groups.add(test.id())
        super().addSubTest(test, subtest, error)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('exact isolated candidate directory required')
    candidate = Path(sys.argv[1]).absolute()
    if candidate.resolve() != candidate or not candidate.is_dir():
        raise SystemExit('plain candidate directory required')
    sys.path.insert(0, str(candidate))
    capture = io.StringIO()
    problem = None
    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            module = importlib.import_module('wirepool')
            origin = getattr(module, '__file__', None)
            if origin is None or Path(origin).resolve() != candidate / 'wirepool/__init__.py':
                problem = 'candidate_import_failure'
            if any(not hasattr(module, name) for name in (
                    'Client', 'Pool', 'Lease', 'Connection', 'Decoder', 'NEED_MORE',
                    'encode_command', 'CommandError', 'ProtocolError', 'PoolClosed')):
                problem = 'candidate_import_failure'
    except (Exception, SystemExit) as error:
        locations = []
        trace = error.__traceback__
        while trace is not None:
            locations.append(trace.tb_frame.f_code.co_filename)
            trace = trace.tb_next
        if isinstance(error, SyntaxError) and error.filename:
            locations.append(error.filename)
        attributable = any(Path(name).resolve().is_relative_to(candidate) for name in locations)
        missing = isinstance(error, ModuleNotFoundError) and error.name == 'wirepool'
        problem = 'candidate_import_failure' if attributable or missing else 'grader_import_infrastructure'
    if problem is None:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_acceptance.py')
            result = unittest.TextTestRunner(stream=capture, verbosity=2, resultclass=GroupResult).run(suite)
        if result.testsRun != 8:
            problem = 'grader_import_infrastructure'
    if problem is not None:
        summary = {'schema': 'pex.wirepool-import-grade.v1', 'outcome': problem,
                   'checks': 0, 'passed': 0, 'failed': 0, 'expected_checks': 8,
                   'loader_errors': 1, 'complete': False, 'all_pass': False}
        print(json.dumps(summary, sort_keys=True))
        return 1 if problem == 'candidate_import_failure' else 2
    failed = len(result.failed_groups)
    summary = {'schema': 'pex.wirepool-grade.v1', 'checks': result.testsRun,
               'passed': result.testsRun - failed, 'failed': failed,
               'complete': True, 'all_pass': result.wasSuccessful() and failed == 0}
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary['all_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

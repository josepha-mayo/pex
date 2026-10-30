"""Run ONLY inside isolated evaluation after worker revocation, or on authored reference."""
import contextlib
import io
import importlib
import json
import sys
from pathlib import Path
import unittest

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('exact isolated candidate directory required')
    candidate = Path(sys.argv[1]).absolute()
    if candidate.resolve() != candidate or not candidate.is_dir():
        raise SystemExit('plain candidate directory required')
    sys.path.insert(0, str(candidate))
    capture = io.StringIO()
    # A loader failure is not eight executed acceptance checks. Attribute it
    # only when the actual exception originates in the candidate, or the exact
    # required candidate module/API is absent. Other loader failures stay infra.
    import_problem = None
    try:
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            module = importlib.import_module('asyncpool')
            origin_file=getattr(module,'__file__',None)
            if origin_file is None and not (candidate/'asyncpool/__init__.py').is_file():
                import_problem='candidate_import_failure'
            elif origin_file is None or Path(origin_file).resolve() != candidate / 'asyncpool/__init__.py':
                raise RuntimeError('candidate_module_origin_unproven')
            if not hasattr(module, 'Pool'):
                import_problem = 'candidate_import_failure'
    except (Exception, SystemExit) as error:
        locations = []
        tb = error.__traceback__
        while tb is not None:
            locations.append(tb.tb_frame.f_code.co_filename)
            tb = tb.tb_next
        if isinstance(error, SyntaxError) and error.filename:
            locations.append(error.filename)
        origin = any(Path(name).resolve().is_relative_to(candidate) for name in locations)
        missing_module = isinstance(error, ModuleNotFoundError) and error.name == 'asyncpool'
        import_problem = 'candidate_import_failure' if origin or missing_module else 'grader_import_infrastructure'
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_acceptance.py')
        result = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
    if import_problem is None and result.testsRun == 1 and len(result.errors) == 1:
        import_problem = 'grader_import_infrastructure'
    if import_problem is not None:
        summary = {'schema': 'pex.asyncpool-import-grade.v1', 'outcome': import_problem,
                   'checks': 0, 'passed': 0, 'failed': 0, 'expected_checks': 8,
                   'loader_errors': len(result.errors), 'complete': False, 'all_pass': False}
        print(json.dumps(summary, sort_keys=True))
        raise SystemExit(1 if import_problem == 'candidate_import_failure' else 2)
    failed = len(result.failures) + len(result.errors)
    summary = {'schema': 'pex.asyncpool-grade.v1', 'checks': result.testsRun,
               'passed': result.testsRun - failed, 'failed': failed,
               'complete': result.testsRun == 8, 'all_pass': result.wasSuccessful() and result.testsRun == 8}
    print(json.dumps(summary, sort_keys=True))
    raise SystemExit(0 if summary['all_pass'] else 1)

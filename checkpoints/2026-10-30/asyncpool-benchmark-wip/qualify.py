"""Offline AUTHOR-REFERENCE/mutation qualification; never runs a worker artifact."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent

def qualify():
    reference = (ROOT/'reference/asyncpool/__init__.py').read_text()
    mutations = {
        'lost_awakened_cancellation': (
            'self._release(key)  # Reclaim the promise, not just queue membership.',
            'pass  # AUTHORED MUTATION: leaked promise'),
        'head_of_line_block': (
            'continue  # Other keys can still be eligible.',
            'break  # AUTHORED MUTATION: block other keys'),
        'ignore_per_key_limit': (
            'if self._keys.get(waiter.key, 0) >= self._key_limit:',
            'if False:  # AUTHORED MUTATION: ignore key capacity'),
        'double_release_inflates_capacity': (
            'if self._released:\n            return',
            'if self._released:\n            self._pool._release(self._key); return'),
        'context_exception_leaks_lease': (
            'finally:\n            lease.release()',
            'finally:\n            pass  # AUTHORED MUTATION: no context release'),
    }
    # Deliberate AUTHOR-REFERENCE mutants validate tests; these are never worker baselines.
    reserved_lines = ('        self._held += 1\n'
                      '        self._keys[waiter.key] = self._keys.get(waiter.key, 0) + 1\n')
    assert reference.count(reserved_lines) == 1
    delayed = reference.replace(reserved_lines, '')
    delayed = delayed.replace('        return Lease(self, key)',
        '        self._held += 1\n        self._keys[key] = self._keys.get(key, 0) + 1\n        return Lease(self, key)')
    cases = {'reference': reference, 'delayed_capacity_reservation': delayed}
    for name, (old, new) in mutations.items():
        assert reference.count(old) == 1, name
        cases[name] = reference.replace(old, new)
    results = []
    for name, source in cases.items():
        with tempfile.TemporaryDirectory(prefix='authored-asyncpool-') as tmp:
            path = Path(tmp)
            (path/'asyncpool').mkdir(); (path/'asyncpool/__init__.py').write_text(source)
            (path/'tests').mkdir()
            shutil.copy(ROOT/'public/tests/test_public.py', path/'tests/test_public.py')
            shutil.copy(ROOT/'heldout/test_acceptance.py', path/'tests/test_acceptance.py')
            env = dict(os.environ, PYTHONPATH=str(path), PYTHONDONTWRITEBYTECODE='1')
            run = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(path/'tests'), '-v'],
                                 cwd=path, env=env, capture_output=True, timeout=45)
            raw = run.stdout + run.stderr
            failed_checks=re.findall(r'^(?:FAIL|ERROR): (test_[a-z_]+)',raw.decode(errors='replace'),re.MULTILINE)
            if name=='delayed_capacity_reservation':
                assert {'test_arrival_cannot_steal_woken_global_slot','test_arrival_cannot_exceed_woken_per_key_slot'} <= set(failed_checks), failed_checks
            results.append({'failed_checks':failed_checks,'case':name,'exit_code':run.returncode,'output_sha256':hashlib.sha256(raw).hexdigest(),
                            'expected': 'pass' if name=='reference' else 'rejected',
                            'qualification':'AUTHORED_REFERENCE_OR_MUTATION_NOT_WORKER_OR_INFERENCE'})
            assert (run.returncode == 0) == (name == 'reference'), (name, raw.decode(errors='replace'))
    return {'schema':'pex.asyncpool-authored-qualification.v1','python':sys.version,
            'reference_checks':12,'mutants_rejected':len(cases)-1,'cases':results,
            'real_inference':False,'PEX_benefit_measured':False}

if __name__ == '__main__':
    print(json.dumps(qualify(),sort_keys=True))

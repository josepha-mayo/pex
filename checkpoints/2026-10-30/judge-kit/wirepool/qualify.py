"""Run only AUTHOR-REFERENCE, AUTHOR-STARTER and AUTHOR-MUTANTS locally.
Never accepts a worker artifact or uses model inference/network resources.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def variant(files, file, old, new):
    assert files[file].count(old) == 1, (file, old)
    changed = dict(files)
    changed[file] = files[file].replace(old, new)
    return changed


def qualify():
    reference = {p.name: p.read_text() for p in (ROOT/'reference/wirepool').glob('*.py')}
    mutations = [
        ('catch_exception_not_cancellation', 'connection.py',
         '        except BaseException:', '        except Exception:'),
        ('raise_pipeline_error_before_draining', 'connection.py',
         '                    replies.append(value)',
         "                    from .protocol import CommandError\n                    if isinstance(value, CommandError):\n                        raise value\n                    replies.append(value)"),
        ('leak_lease_on_baseexception', 'client.py',
         '        finally:\n            lease.release()',
         '        finally:\n            import sys\n            if sys.exception() is None or isinstance(sys.exception(), Exception):\n                lease.release()'),
        ('lose_assigned_handoff_on_cancel', 'pool.py',
         '            if future.done() and not future.cancelled() and future.exception() is None:',
         '            if False:'),
        ('accept_invalid_decimal_grammar', 'protocol.py',
         '        if not _DECIMAL.fullmatch(raw):\n            raise ProtocolError(\'invalid decimal\')\n', ''),
        ('return_factory_after_shutdown', 'pool.py',
         '            if self._closed:\n                connection.close()',
         '            if False:\n                connection.close()'),
        ('double_release_duplicates_idle_connection', 'pool.py',
         '        if self._released:\n            return',
         '        if self._released:\n            self._pool._put(self.connection)\n            return'),
        ('reset_decoder_between_exchanges', 'connection.py',
         '            await self._transport.send(payload)',
         '            self._decoder = Decoder()\n            await self._transport.send(payload)'),
        ('shutdown_exception_overrides_cancellation', 'pool.py',
         'if future.done() and not future.cancelled() and future.exception() is None:',
         'if future.done() and not future.cancelled():'),
    ]
    cases = [('reference', reference)]
    for name, file, old, new in mutations:
        cases.append((name, variant(reference, file, old, new)))
    late = variant(reference, 'pool.py',
                   '                self._total += 1  # Reserve before publishing the factory promise.\n', '')
    late = variant(late, 'pool.py', '            connection = Connection(transport)',
                   '            self._total += 1\n            connection = Connection(transport)')
    cases.append(('count_capacity_only_after_factory_returns', late))
    # Starter failures are task diagnostics, never a baseline/model result.
    starter = {p.name: p.read_text() for p in (ROOT/'public/wirepool').glob('*.py')}
    cases.append(('starter', starter))
    records = []
    evidence = ROOT/'evidence'
    evidence.mkdir(exist_ok=True)
    for name, sources in cases:
        with tempfile.TemporaryDirectory(prefix='authored-wirepool-') as tmp:
            path = Path(tmp); (path/'wirepool').mkdir(); (path/'tests').mkdir()
            for file, text in sources.items(): (path/'wirepool'/file).write_text(text)
            shutil.copy(ROOT/'public/tests/test_public.py', path/'tests/test_public.py')
            shutil.copy(ROOT/'heldout/test_acceptance.py', path/'tests/test_acceptance.py')
            env = dict(os.environ, PYTHONPATH=str(path), PYTHONDONTWRITEBYTECODE='1')
            try:
                result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover',
                                         '-s', str(path/'tests'), '-v'], cwd=path,
                                        env=env, capture_output=True, timeout=45)
                raw = result.stdout + result.stderr
                code, timed_out = result.returncode, False
            except subprocess.TimeoutExpired as error:
                raw = (error.stdout or b'') + (error.stderr or b'')
                code, timed_out = None, True
            (evidence/(name+'.log')).write_bytes(raw)
            failed = sorted(set(re.findall(r'^(?:FAIL|ERROR): (test_[a-zA-Z0-9_]+)',
                                          raw.decode(errors='replace'), re.MULTILINE)))
            record = {'case': name, 'exit_code': code, 'timed_out': timed_out,
                      'failed_groups': failed, 'log_sha256': hashlib.sha256(raw).hexdigest(),
                      'source_sha256': {file: hashlib.sha256(text.encode()).hexdigest() for file, text in sorted(sources.items())},
                      'kind': 'AUTHORED_REFERENCE' if name == 'reference' else 'AUTHORED_STARTER' if name == 'starter' else 'AUTHORED_MUTATION',
                      'expected': 'pass' if name == 'reference' else 'rejected'}
            records.append(record)
            if name == 'reference':
                assert code == 0 and not timed_out, raw.decode(errors='replace')
            elif name != 'starter':
                assert code != 0 and failed and not timed_out, (name, raw.decode(errors='replace'))
    report = {'schema': 'pex.wirepool-authored-qualification.v1',
              'python_implementation': platform.python_implementation(), 'python_version': platform.python_version(),
              'reference_public_checks': 8, 'reference_protected_groups': 8,
              'mutants_rejected': len(cases)-2, 'cases': records,
              'real_inference': False, 'PEX_benefit_measured': False,
              'candidate_worker_code_executed_locally': False}
    (evidence/'qualification.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    return report


if __name__ == '__main__':
    report = qualify()
    print(json.dumps({'schema': report['schema'], 'python_version': report['python_version'],
                      'reference_pass': True, 'mutants_rejected': report['mutants_rejected'],
                      'starter': report['cases'][-1], 'real_inference': False}, sort_keys=True))

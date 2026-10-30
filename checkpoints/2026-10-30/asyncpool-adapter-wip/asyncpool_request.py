"""Trusted public test/diff/snapshot collector for the separate asyncpool task.
No controller-side candidate execution. Call only with already-owned isolated remote.
"""
import base64,hashlib,json,shlex
from pathlib import Path
from stockroom_request import bounded_text,PublicEvidenceInfrastructureError
from asyncpool_adapter import PUBLIC_CHECK_COMMAND,allowed_snapshot_path,validate_snapshot,digest,canonical
def collect_public_observation(remote,receipt,*,capture_public_snapshot=False,snapshot_sink=None):
    """Remote public tests + diff only; invoke at natural stop before review.
    Runtime owner must use this instead of its legacy test_smoke.py collector.
    """
    result=remote.run(PUBLIC_CHECK_COMMAND)
    if type(result.get('exit_code')) is not int or result['exit_code'] not in (0,1):
        raise PublicEvidenceInfrastructureError('public_check_non_test_terminal')
    check={'command':PUBLIC_CHECK_COMMAND,'exit_code':result['exit_code'],
           'output':bounded_text(result['stdout']+'\n'+result['stderr'])}
    check['receipt_sha256']=hashlib.sha256(json.dumps(check,sort_keys=True).encode()).hexdigest()
    diff_source=(Path(__file__).parent/'public_diff.py').read_text()
    diff=remote.run('python3 -I -B -c '+shlex.quote(diff_source))
    if type(diff.get('exit_code')) is not int or diff['exit_code']!=0:raise PublicEvidenceInfrastructureError('public_diff_failed')
    observation={'assistant_final':bounded_text('\n'.join(receipt.messages),tail=True),
            'public_check':check,'public_diff':bounded_text(diff['stdout']),
            'receipt_sha256':receipt.stdout_sha256}
    if type(capture_public_snapshot)is not bool:raise ValueError('explicit_public_snapshot_profile_required')
    if capture_public_snapshot:
        source=(Path(__file__).parent/'export_candidate.py').read_text()
        result=remote.run('python3 -I -B -c '+shlex.quote(source))
        if type(result.get('exit_code'))is not int or result['exit_code']!=0 or len(result.get('stdout','').encode())>200000:
            raise PublicEvidenceInfrastructureError('public_candidate_snapshot_unproven')
        export=json.loads(result['stdout'])
        if type(export)is not dict or set(export)!={'schema','files'} or export['schema']!='pex.asyncpool-export.v1' or type(export['files'])is not dict:
            raise PublicEvidenceInfrastructureError('public_candidate_snapshot_shape')
        files={};total=0
        for path,encoded_content in export['files'].items():
            if not allowed_snapshot_path(path):continue  # No binary, hidden or non-public resources offered.
            raw=base64.b64decode(encoded_content,validate=True);total+=len(raw)
            if total>131072:raise PublicEvidenceInfrastructureError('public_candidate_snapshot_bound')
            files[path]={'sha256':hashlib.sha256(raw).hexdigest(),'content':raw.decode('utf8')}
        snapshot={'schema':'pex.public-candidate-snapshot.v1','files':files,
                  'snapshot_sha256':digest(canonical(files))}
        observation['public_candidate_snapshot']=validate_snapshot(snapshot)
        if snapshot_sink is not None:
            if not callable(snapshot_sink):raise ValueError('trusted_snapshot_sink_required')
            snapshot_sink(export,observation['public_candidate_snapshot'])
    return observation


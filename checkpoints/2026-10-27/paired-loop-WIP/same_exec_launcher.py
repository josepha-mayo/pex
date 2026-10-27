"""Root-pinned same-execution platform-proxy derivation; never starts a run.

The static policy explicitly delegates ONLY the supplied HTTPS_PROXY value.
No arbitrary proxy argument, endpoint change, TLS downgrade, budget reset, or
implicit successor run is available. Cumulative admission remains a separate gate.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def sha(raw):return hashlib.sha256(raw).hexdigest()

def validate_platform_proxy(config,read_private):
    template=json.loads(read_private(config['supervisor_template_path']))
    binding=template.get('platform_proxy')
    if type(binding)is not dict or set(binding)!={'proxy_sha256','ca_path','ca_sha256'}:
        raise ValueError('explicit_platform_proxy_binding_required')
    proxy=os.environ.get('HTTPS_PROXY','')
    parts=urlsplit(proxy)
    if not proxy or parts.scheme not in ('http','https') or not parts.hostname or parts.path not in ('','/') or parts.query or parts.fragment:
        raise ValueError('provided_platform_proxy_invalid')
    if sha(proxy.encode())!=binding['proxy_sha256']:raise ValueError('platform_proxy_changed_before_resources')
    if os.environ.get('SSL_CERT_FILE')!=binding['ca_path']:raise ValueError('platform_ca_path_changed')
    ca=Path(binding['ca_path'])
    if not ca.is_absolute() or not ca.is_file() or ca.stat().st_size>4*1024*1024 or sha(ca.read_bytes())!=binding['ca_sha256']:
        raise ValueError('platform_ca_identity_changed')
    return binding

@dataclass(frozen=True)
class BoundConfig:
    path:Path
    digest:str
    proxy_sha256:str
    def assert_same_execution_environment(self):
        if sha(os.environ.get('HTTPS_PROXY','').encode())!=self.proxy_sha256:
            raise ValueError('same_execution_proxy_changed')


def _write_private(path,raw):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def bind_root_policy(policy_path,expected_policy_sha256,destination):
    # Imports only stdlib-bound admission, no provider clients/framework here.
    from pilot_nebius import load,read_private
    raw=read_private(policy_path)
    if sha(raw)!=expected_policy_sha256:raise ValueError('root_static_policy_digest_mismatch')
    policy=json.loads(raw)
    if type(policy)is not dict or set(policy)!={'schema','mode','driver_config_path','driver_config_sha256'} or policy['schema']!=1 or policy['mode']!='same_exec_provided_platform_proxy':
        raise ValueError('root_static_policy_refused')
    config=load(Path(policy['driver_config_path']),policy['driver_config_sha256'])
    if Path(config['output_dir']).exists():raise ValueError('closed_or_existing_run_cannot_be_rebound')
    # Source identity is already bound by the static driver config.
    if config['source_sha256'].get(Path(__file__).name)!=sha(Path(__file__).read_bytes()):
        raise ValueError('launcher_not_bound_by_root')
    template_raw=read_private(config['supervisor_template_path']);template=json.loads(template_raw)
    binding=template.get('platform_proxy')
    if type(binding)is not dict or set(binding)!={'proxy_sha256','ca_path','ca_sha256'}:
        raise ValueError('static_platform_CA_binding_required')
    # Delegate only current provided proxy; preserve endpoint/model/CA/all funding.
    proxy=os.environ.get('HTTPS_PROXY','');proxy_sha=sha(proxy.encode())
    template['platform_proxy']={**binding,'proxy_sha256':proxy_sha}
    dest=Path(destination)
    if not dest.is_absolute() or dest.parent.resolve()!=dest.parent:raise ValueError('private_derivation_path_required')
    dest.mkdir(mode=0o700,exist_ok=False)
    derived_template=dest/'supervisor-template.json'
    t_raw=json.dumps(template,sort_keys=True,separators=(',',':')).encode()
    _write_private(derived_template,t_raw)
    derived={**config,'supervisor_template_path':str(derived_template),'supervisor_template_sha256':sha(t_raw)}
    validate_platform_proxy(derived,read_private)
    derived_path=dest/'pilot-config.json';d_raw=json.dumps(derived,sort_keys=True,separators=(',',':')).encode()
    _write_private(derived_path,d_raw)
    receipt={'schema':1,'kind':'same_exec_binding_only_no_run','static_policy_sha256':expected_policy_sha256,
             'static_driver_sha256':policy['driver_config_sha256'],'static_template_sha256':sha(template_raw),
             'derived_driver_sha256':sha(d_raw),'derived_template_sha256':sha(t_raw),'proxy_sha256':proxy_sha,'ca_sha256':binding['ca_sha256']}
    _write_private(dest/'derivation.json',json.dumps(receipt,sort_keys=True).encode())
    return BoundConfig(derived_path,sha(d_raw),proxy_sha)

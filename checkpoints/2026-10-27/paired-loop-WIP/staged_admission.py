"""WIP staged admission: one independently reviewed exploratory recovery08 identity.

A candidate inspection is not authority. The new source-reviewed identity below
still requires an independently pinned root Grant and a fresh private claim. Historical
liabilities (including unknown requests) are supplied by a pinned predecessor;
this module never refunds them or reuses the consumed legacy approval.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from staged_envelope import PHASES, VM_SECONDS, WALL_PROFILE, reservation_envelope

PROVIDER_CAP = 2_000_000_000
COMPUTE_CAP = 120_000_000  # Legacy default; an exact per-run Grant pins its ceiling.
SUPPORTED_COMPUTE_CAPS = (COMPUTE_CAP,140_000_000,250_000_000)  # Capability alone is never spend authority.
WORKER_MODEL = 'deepseek-ai/DeepSeek-V4.1-Flash-1017'
SUPERVISOR_MODEL = 'nvidia/nemotron-3-super-120b-a12b'
REQUIRED_PREDECESSORS = frozenset(('original_workers', 'original_supervisor',
    'diagnostic1423', 'retry01', 'shape02', 'cache03', 'nested04', 'nullable05',
    'null_function06', 'pair03_workers', 'pair03_supervisor', 'pair03_compute',
    'denied_pair02_workers', 'denied_pair02_supervisor', 'denied_pair02_compute',
    'denied_pair02_authoritative_reconciliation',
    'failed_staged03_workers','failed_staged03_supervisor','failed_staged03_compute',
    'failed_staged03_terminal','failed_staged03_report',
    'failed_staged04_workers','failed_staged04_supervisor','failed_staged04_compute',
    'failed_staged04_terminal','failed_staged04_report',
    'failed_staged05_workers','failed_staged05_supervisor','failed_staged05_compute',
    'failed_staged05_terminal','failed_staged05_report',
    'interrupted_staged06_workers','interrupted_staged06_supervisor','interrupted_staged06_compute',
    'interrupted_staged06_admission','interrupted_staged06_poll_denial','interrupted_staged06_cleanup',
    'failed_staged07_workers','failed_staged07_supervisor','failed_staged07_compute',
    'failed_staged07_terminal','failed_staged07_report','failed_staged07_diagnostics'))
_SEAL = object()

class AdmissionRefused(PermissionError): pass

def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
def digest(value): return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None

def read_pin(pin, *, private=False, limit=8*1024*1024):
    if type(pin) is not dict or set(pin) != {'path','sha256'} or not digest(pin['sha256']):
        raise AdmissionRefused('exact_file_pin_required')
    path = Path(pin['path'])
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise AdmissionRefused('absolute_unlinked_path_required')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise AdmissionRefused('regular_bounded_file_required')
    if private and (info.st_uid != os.geteuid() or info.st_mode & 0o077 or path.parent.stat().st_mode & 0o077):
        raise AdmissionRefused('private_owned_file_required')
    raw = path.read_bytes()
    if sha(raw) != pin['sha256']: raise AdmissionRefused('pinned_file_changed')
    return raw

@dataclass(frozen=True)
class GrantGate:
    """Source-reviewed identity, deliberately excludes hashes of this source.

    Exact immutable hashes come from a separately trusted root launcher Grant;
    embedding config_sha256 here would make config->source->config circular.
    Neither candidate JSON nor an environment value can supply this gate.
    """
    approval_ref: str
    run_id: str
    config_path: str
    expires_at: str

    @classmethod
    def identity(cls, grant):
        if type(grant) is not Grant:
            raise AdmissionRefused('independent_exact_grant_identity_required')
        return cls(grant.approval_ref,grant.run_id,grant.config_path,grant.expires_at)

@dataclass(frozen=True)
class Grant:
    approval_ref: str
    run_id: str
    config_path: str
    config_sha256: str
    profile_sha256: str
    predecessor_sha256: str
    sources_sha256: str
    task_sha256: str
    expires_at: str

# Pair07 consumed its claim: two verified VMs, local worker admission failure, no model calls.
# Its full330s compute charge remains; no retry/replacement or old-claim reopen.
# Any later grant requires independently reviewed authority and cumulative bounds.
APPROVED_STAGED_GRANT = GrantGate(
    approval_ref='Sentinel_3dd0c75c32048191a3b47145b5d3f267',
    run_id='stockroom-staged-pair-20261029-08',
    config_path='/workspace/scratch/c62c151ada7d/runtime-private/pex-pilot-20261027/stockroom-staged-pair-20261029-08/pair.json',
    expires_at='2026-10-29T15:30:00+00:00')

@dataclass(frozen=True, repr=False)
class Admitted:
    grant: Grant
    raw: bytes = field(repr=False)
    _seal: object = field(repr=False)
    def config(self):
        check_authority(self)
        return json.loads(self.raw)  # Never expose a shared mutable admission.
    def __repr__(self): return '<private closed-gate staged admission>'

def check_authority(admitted):
    if (type(admitted) is not Admitted or admitted._seal is not _SEAL
            or type(APPROVED_STAGED_GRANT) is not GrantGate
            or GrantGate.identity(admitted.grant) != APPROVED_STAGED_GRANT):
        raise AdmissionRefused('fresh_staged_pair_approval_pending')
    expiry = datetime.fromisoformat(admitted.grant.expires_at)
    if expiry.tzinfo is None or datetime.now(timezone.utc) >= expiry:
        raise AdmissionRefused('staged_grant_expired')

def validate_transport(net):
    """Keep proxy values in this process only; return no proxy credentials."""
    if type(net) is not dict or set(net) != {'proxy_sha256','ca'} or not digest(net['proxy_sha256']):
        raise AdmissionRefused('exact_transport_binding_required')
    proxy = os.environ.get('HTTPS_PROXY', '')
    parts = urlsplit(proxy)
    if (not proxy or sha(proxy.encode()) != net['proxy_sha256'] or parts.scheme not in ('http','https')
            or not parts.hostname or parts.path not in ('','/') or parts.query or parts.fragment):
        raise AdmissionRefused('same_process_ordinary_proxy_changed')
    if os.environ.get('SSL_CERT_FILE') != net['ca']['path']:
        raise AdmissionRefused('ordinary_CA_path_changed')
    read_pin(net['ca'], limit=4*1024*1024)
    # Refuse routing overrides rather than deleting/changing the environment.
    for name in ('E2B_API_URL','E2B_SANDBOX_URL','E2B_DOMAIN','E2B_DEBUG'):
        if os.environ.get(name): raise AdmissionRefused('SDK_route_override_refused')

def inspect_candidate(raw, grant, *, now=None):
    """Read-only validation. Returns accounting, NOT an Admitted capability."""
    if type(grant) is not Grant or not all(digest(getattr(grant, n)) for n in
            ('config_sha256','profile_sha256','predecessor_sha256','sources_sha256','task_sha256')):
        raise AdmissionRefused('independent_exact_grant_identity_required')
    if sha(raw) != grant.config_sha256: raise AdmissionRefused('config_identity_changed')
    cfg = json.loads(raw)
    required = {'schema','approval_ref','run_id','expires_at','profile','predecessor','sources','task','network','output_dir','e2b_key','nebius_key','sdk_sources','cli'}
    if type(cfg) is not dict or set(cfg) != required or cfg['schema'] != 'pex.staged.closed-candidate.v1':
        raise AdmissionRefused('staged_candidate_schema')
    if (not grant.approval_ref or cfg['approval_ref'] != grant.approval_ref or cfg['run_id'] != grant.run_id
            or not re.fullmatch('[a-z0-9-]{1,80}',grant.run_id) or cfg['expires_at'] != grant.expires_at):
        raise AdmissionRefused('single_grant_run_identity_required')
    expiry = datetime.fromisoformat(grant.expires_at)
    if expiry.tzinfo is None or (now or datetime.now(timezone.utc))+timedelta(seconds=2*VM_SECONDS+30) >= expiry:
        raise AdmissionRefused('complete_pair_execution_window_required')
    profile = cfg['profile']
    if sha(canonical(profile)) != grant.profile_sha256: raise AdmissionRefused('frozen_profile_changed')
    if type(profile)is not dict or type(profile.get('compute_cap'))is not int or profile['compute_cap'] not in SUPPORTED_COMPUTE_CAPS:
        raise AdmissionRefused('supported_pinned_compute_profile_required')
    fixed = {'provider_cap':PROVIDER_CAP,'compute_cap':profile['compute_cap'],'worker_model':WORKER_MODEL,
        'supervisor_model':SUPERVISOR_MODEL,'phases':[vars(p) for p in PHASES],
        'vm_seconds':VM_SECONDS,'wall_profile':dict(WALL_PROFILE),'supervisor_attempts':12,'forced_textual_finalization':True}
    if set(profile) != set(fixed)|{'equal_worker_fresh','supervisor_fresh','supervisor_pricing_sha256'} or any(profile[k] != v for k,v in fixed.items()):
        raise AdmissionRefused('equal_frozen_staged_protocol_required')
    if not digest(profile['supervisor_pricing_sha256']): raise AdmissionRefused('frozen_supervisor_pricing_identity_required')
    if cfg['predecessor']['sha256'] != grant.predecessor_sha256: raise AdmissionRefused('predecessor_identity_changed')
    prior = json.loads(read_pin(cfg['predecessor'],private=True))
    if (type(prior) is not dict or set(prior) != {'schema','provider_nano_usd','compute_nano_usd','ledgers','uncertain_reservations_retained'}
            or prior['schema'] != 'pex.staged.predecessors.v1' or prior['uncertain_reservations_retained'] is not True
            or set(prior['ledgers']) != REQUIRED_PREDECESSORS):
        raise AdmissionRefused('complete_retained_predecessor_set_required')
    for pin in prior['ledgers'].values(): read_pin(pin,private=True,limit=32*1024*1024)
    for name in ('sources','sdk_sources'):
        if not isinstance(cfg[name],dict) or not cfg[name]: raise AdmissionRefused('source_identity_required')
        for pin in cfg[name].values(): read_pin(pin)
    # The independent source-set digest includes paths and hashes of BOTH app
    # and installed SDK sources; changed implementation is not silently reused.
    if sha(canonical({k:cfg[k] for k in ('sources','sdk_sources')})) != grant.sources_sha256:
        raise AdmissionRefused('reviewed_source_set_changed')
    if cfg['task']['sha256'] != grant.task_sha256: raise AdmissionRefused('frozen_task_changed')
    read_pin(cfg['task'])
    cli=cfg['cli']
    if type(cli) is not dict or set(cli)!={'binary','modules_path','plugin_package'}:
        raise AdmissionRefused('frozen_CLI_identity_required')
    read_pin(cli['binary'],limit=512*1024*1024);read_pin(cli['plugin_package'])
    modules=Path(cli['modules_path'])
    if (not modules.is_absolute() or modules.resolve()!=modules or not modules.is_dir()
            or cli['plugin_package']['path']!=str(modules/'@opencode/plugin/package.json')):
        raise AdmissionRefused('frozen_plugin_path_required')
    validate_transport(cfg['network'])
    output = Path(cfg['output_dir'])
    config = Path(grant.config_path)
    if (not config.is_absolute() or config.resolve() != config or config.name != 'pair.json'
            or output != config.parent/'run' or output.exists() or (config.parent/'launch.claim').exists()
            or config.parent.stat().st_mode & 0o077):
        raise AdmissionRefused('fresh_private_single_run_required')
    # Key pin syntax only; no key read until separately admitted SDK use.
    for key in ('e2b_key','nebius_key'):
        if set(cfg[key]) != {'path','sha256'} or not digest(cfg[key]['sha256']):
            raise AdmissionRefused('existing_private_key_pin_required')
    return reservation_envelope(prior_provider=prior['provider_nano_usd'],equal_worker_fresh=profile['equal_worker_fresh'],
        supervisor_fresh=profile['supervisor_fresh'],provider_ceiling=PROVIDER_CAP,prior_compute=prior['compute_nano_usd'],
        verified_vm_bound=9_982_500,uncertain_create_reserve=48_840_000,compute_ceiling=profile['compute_cap'])

def load(grant=None):
    # CLOSED source gate precedes reads and caller input. A future trusted root
    # launcher must supply its independently reviewed immutable full Grant, NOT
    # deserialize authority from candidate bytes, worker input or environment.
    gate = APPROVED_STAGED_GRANT
    if type(gate) is not GrantGate: raise AdmissionRefused('fresh_staged_pair_approval_pending')
    if GrantGate.identity(grant) != gate:
        raise AdmissionRefused('independent_grant_gate_identity_changed')
    raw = read_pin({'path':grant.config_path,'sha256':grant.config_sha256},private=True)
    inspect_candidate(raw,grant)
    return Admitted(grant,raw,_SEAL)

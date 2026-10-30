"""WIP staged admission: one independently reviewed exploratory paired20 identity.

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
from staged_envelope import PHASES, VM_SECONDS, WALL_PROFILE, WORKER_OUTPUT_PER_CALL, reservation_envelope
from cumulative_compute import allocation_bounds, NEXT_PAIR_ENVELOPE, NEXT_RETRY_ENVELOPE, OBSERVATION_RETRY_ENVELOPE
from asyncpool_adapter import MANIFEST_SHA256 as ASYNCPOOL_MANIFEST
import asyncpool_history

PROVIDER_CAP = 5_000_000_000  # Fresh contextualized user approval; cumulative, never reset.
COMPUTE_CAP = 120_000_000  # Legacy default; an exact per-run Grant pins its ceiling.
SUPPORTED_COMPUTE_CAPS = (COMPUTE_CAP,140_000_000,250_000_000,500_000_000,NEXT_PAIR_ENVELOPE,NEXT_RETRY_ENVELOPE,OBSERVATION_RETRY_ENVELOPE)  # Capability alone is never spend authority.
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
    'failed_staged07_terminal','failed_staged07_report','failed_staged07_diagnostics',
    'failed_staged08_workers','failed_staged08_supervisor','failed_staged08_compute',
    'failed_staged08_terminal','failed_staged08_report','failed_staged08_diagnostics','failed_staged08_validated_summary',
    'interrupted_staged09_workers','interrupted_staged09_supervisor','interrupted_staged09_compute',
    'interrupted_staged09_admission','interrupted_staged09_poll_denial','interrupted_staged09_manager_status',
    'interrupted_staged09_observation_correction','interrupted_staged09_model_revocation',
    'interrupted_staged09_post_revocation','interrupted_staged09_validated_partial','interrupted_staged09_cleanup',
    'prospective_staged06_compute_reconciliation','root_accepted_staged06_compute_reconciliation',
    'completed_staged10_workers','completed_staged10_supervisor','completed_staged10_compute',
    'completed_staged10_terminal','completed_staged10_report','completed_staged10_evidence',
    'unknown_receipt_diagnostic01_ledger','unknown_receipt_diagnostic01_config','unknown_receipt_diagnostic01_claim',
    'captured_receipt_diagnostic02_ledger','captured_receipt_diagnostic02_terminal','captured_receipt_diagnostic02_raw_response',
    'completed_staged11_workers','completed_staged11_supervisor','completed_staged11_compute',
    'completed_staged11_terminal','completed_staged11_report','completed_staged11_baseline','completed_staged11_pex',
    'completed_staged11_executed_sources',
    'completed_staged12_workers','completed_staged12_supervisor','completed_staged12_compute',
    'completed_staged12_terminal','completed_staged12_report','completed_staged12_baseline','completed_staged12_pex',
    'completed_staged12_executed_sources','completed_staged12_actual_outcome','completed_staged12_recording_terminal',
    'failed_staged13_workers','failed_staged13_supervisor','failed_staged13_compute','failed_staged13_terminal',
    'failed_staged13_config','failed_staged13_admission','failed_staged13_claim','failed_staged13_executed_sources',
    'interrupted_staged14_workers','interrupted_staged14_supervisor','interrupted_staged14_compute',
    'interrupted_staged14_config','interrupted_staged14_admission','interrupted_staged14_claim',
    'interrupted_staged14_executed_sources','interrupted_staged14_interruption','interrupted_staged14_summary',
    'interrupted_staged14_cleanup_scope','interrupted_staged14_cleanup_receipt','interrupted_staged14_cleanup_result',
    'interrupted_staged14_local_cleanup','interrupted_staged14_recording_terminal',
    'interrupted_staged17_workers','interrupted_staged17_supervisor','interrupted_staged17_compute',
    'interrupted_staged17_config','interrupted_staged17_admission','interrupted_staged17_claim',
    'interrupted_staged17_executed_sources','interrupted_staged17_owned_vm','interrupted_staged17_interruption',
    'interrupted_staged17_cleanup_scope','interrupted_staged17_cleanup_result','interrupted_staged17_cleanup_before',
    'interrupted_staged17_cleanup_delete','interrupted_staged17_cleanup_after','interrupted_staged17_local_recovery',
    'interrupted_staged17_recording_terminal',
    'interrupted_staged18_workers','interrupted_staged18_supervisor','interrupted_staged18_compute',
    'interrupted_staged18_config','interrupted_staged18_admission','interrupted_staged18_claim',
    'interrupted_staged18_executed_sources','interrupted_staged18_interruption',
    'interrupted_staged18_cleanup_scope','interrupted_staged18_cleanup_result',
    'interrupted_staged18_review_denial','interrupted_staged18_recording_terminal',
    'failed_staged19_workers','failed_staged19_supervisor','failed_staged19_compute',
    'failed_staged19_config','failed_staged19_admission','failed_staged19_claim',
    'failed_staged19_executed_sources','failed_staged19_terminal','failed_staged19_report',
    'failed_staged19_preservation','failed_staged19_cleanup_scope','failed_staged19_cleanup_result',
    'failed_staged19_recording_terminal',
    'failed_staged20_workers','failed_staged20_supervisor','failed_staged20_compute','failed_staged20_config','failed_staged20_admission','failed_staged20_claim','failed_staged20_executed_sources','failed_staged20_terminal','failed_staged20_report','failed_staged20_preservation','failed_staged20_recording_terminal','failed_staged20_remote_diagnostics','failed_staged20_owned_baseline','failed_staged20_owned_pex','failed_staged20_baseline_public','failed_staged20_baseline_grade'))
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

# Pair17 stopped after eight settled baseline calls; no paired result was produced.
# Its exact VM cleanup is proven, but original launcher exit remains unproven.
# Pair14 and all earlier uncertain reservations remain fully retained.
# Fresh user approval explicitly covers authored task/code/public-test payload to Nebius.
# All uncertain model/compute charges remain retained; no old claim can reopen.
# Pair18 unknown creation retains its entire 111000000 reservation.
# User approved E2B authored benchmark/candidate transfer and continued resources.
# Operational envelopes bound this run; they do not redefine user spending approval.
# Exact independently reviewed config/source pins and unused claim remain required.
APPROVED_STAGED_GRANT = GrantGate(
    approval_ref='Sentinel_5ad659664cb48191842ac9c9406468d1',
    run_id='stockroom-staged-pair-20261030-21',
    config_path='/tmp/pex-paired-live-20261029/stockroom-staged-pair-20261030-21/pair.json',
    expires_at='2026-10-30T02:00:00+00:00')

# New task requires its own independently reviewed exact gate; no legacy reuse.
APPROVED_ASYNCPOOL_GRANT=GrantGate(
    approval_ref='Sentinel_6dbbc3710b3881919e6650c9b3b2170e',
    run_id='asyncpool-staged-pair-20261030-08',
    config_path='/tmp/pex-paired-live-20261030/asyncpool-staged-pair-20261030-08/pair.json',
    expires_at='2026-10-30T16:00:00+00:00')

def task_gate(grant):
    if type(grant)is Grant and grant.run_id.startswith('asyncpool-staged-pair-'):
        return APPROVED_ASYNCPOOL_GRANT
    return APPROVED_STAGED_GRANT

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
            or type(task_gate(admitted.grant)) is not GrantGate
            or GrantGate.identity(admitted.grant) != task_gate(admitted.grant)):
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
    is_asyncpool=grant.task_sha256==ASYNCPOOL_MANIFEST
    if is_asyncpool != grant.run_id.startswith('asyncpool-staged-pair-'):
        raise AdmissionRefused('separate_asyncpool_task_identity_required')
    profile = cfg['profile']
    if sha(canonical(profile)) != grant.profile_sha256: raise AdmissionRefused('frozen_profile_changed')
    if type(profile)is not dict or type(profile.get('compute_cap'))is not int or profile['compute_cap'] not in ((asyncpool_history.COMPUTE_ENVELOPE,) if is_asyncpool else SUPPORTED_COMPUTE_CAPS):
        raise AdmissionRefused('supported_pinned_compute_profile_required')
    fixed = {'provider_cap':PROVIDER_CAP,'compute_cap':profile['compute_cap'],'worker_model':WORKER_MODEL,
        'supervisor_model':SUPERVISOR_MODEL,'phases':[vars(p) for p in PHASES],
        'vm_seconds':VM_SECONDS,'wall_profile':dict(WALL_PROFILE),'equal_worker_fresh':750000000,'worker_output_per_call':WORKER_OUTPUT_PER_CALL,
        'supervisor_fresh':350000000,'supervisor_attempts':12,'forced_textual_finalization':True,'public_snapshot_inspection':True,'grade_phase0_after_final':True,
        'runtime_contract':{'python_implementation':'CPython','python_version':'3.11.6','sqlite_version':'3.40.1','workspace':'/home/user/pex-task'}}
    if (set(profile) != set(fixed)|{'equal_worker_fresh','supervisor_fresh','supervisor_pricing_sha256'}
            or profile.get('public_snapshot_inspection') is not True or profile.get('grade_phase0_after_final') is not True
            or any(profile[k] != v for k,v in fixed.items())):
        raise AdmissionRefused('equal_frozen_staged_protocol_required')
    if not digest(profile['supervisor_pricing_sha256']): raise AdmissionRefused('frozen_supervisor_pricing_identity_required')
    if cfg['predecessor']['sha256'] != grant.predecessor_sha256: raise AdmissionRefused('predecessor_identity_changed')
    prior = json.loads(read_pin(cfg['predecessor'],private=True))
    if (type(prior) is not dict or set(prior) != {'schema','provider_nano_usd','compute_nano_usd','ledgers','uncertain_reservations_retained'}
            or prior['schema'] != 'pex.staged.predecessors.v1' or prior['uncertain_reservations_retained'] is not True
            or set(prior['ledgers']) != (asyncpool_history.required_predecessors(REQUIRED_PREDECESSORS) if is_asyncpool else REQUIRED_PREDECESSORS)):
        raise AdmissionRefused('complete_retained_predecessor_set_required')
    if is_asyncpool and (prior['provider_nano_usd']!=asyncpool_history.PRIOR_PROVIDER or prior['compute_nano_usd']!=asyncpool_history.PRIOR_COMPUTE):raise AdmissionRefused('asyncpool_all_historical_charges_required')
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
        verified_vm_bound=allocation_bounds(VM_SECONDS)[1],uncertain_create_reserve=allocation_bounds(VM_SECONDS)[0],compute_ceiling=profile['compute_cap'])

def load(grant=None):
    # CLOSED source gate precedes reads and caller input. A future trusted root
    # launcher must supply its independently reviewed immutable full Grant, NOT
    # deserialize authority from candidate bytes, worker input or environment.
    gate = task_gate(grant)
    if type(gate) is not GrantGate: raise AdmissionRefused('fresh_staged_pair_approval_pending')
    if GrantGate.identity(grant) != gate:
        raise AdmissionRefused('independent_grant_gate_identity_changed')
    raw = read_pin({'path':grant.config_path,'sha256':grant.config_sha256},private=True)
    inspect_candidate(raw,grant)
    return Admitted(grant,raw,_SEAL)

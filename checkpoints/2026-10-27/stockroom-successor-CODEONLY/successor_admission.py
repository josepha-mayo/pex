"""Explicit root-pinned successor admission, not user/resource authority itself."""
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
from urllib.parse import urlsplit
from successor_budget import PRIOR_WORKERS, PRIOR_SUPERVISOR, PRIOR_COMPUTE, WORKER_SHARED_OUTER

# A fresh pair requires an exact new approval pinned by root, not caller data.
APPROVED_PAIR_REF = None  # One authorized pair consumed; no additional dispatch.
APPROVED_RUN_ID = "stockroom-approved-pair-20261028-03"
APPROVED_PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "runtime-private" / "pex-pilot-20261027" / APPROVED_RUN_ID

TASK_SHA='c242f9128edd87b34c678e5e0db36527b556f0b2163533577e5c96320c3b5f19'
REQUIRED_SOURCES={'successor_budget','successor_admission','successor_runner','stockroom_task','stockroom_request','stockroom_grade','export_candidate','public_diff','controller','review','nebius_worker','nebius_guard','worker_funding','accounting','cumulative_compute','e2b_transport','remote_mcp','budget_rpc','opencode_cli','opencode_v2_receipt','process_adapter'}
REQUIRED={'schema','run_id','approval_ref','funding_approval_ref','expires_at','package_path','output_dir','nebius_key','e2b_key','binary','modules_path','sources','predecessor','supervisor','network'}
class AdmissionRefused(PermissionError):pass

def sha(b):return hashlib.sha256(b).hexdigest()
def digest(value):return type(value)is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def private_read(path,max_bytes=65536):
    p=Path(path)
    if not p.is_absolute() or p.resolve(strict=True)!=p:raise AdmissionRefused('absolute_unlinked_private_path_required')
    info=p.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.geteuid() or info.st_mode&0o077 or p.parent.stat().st_mode&0o077 or info.st_size>max_bytes:raise AdmissionRefused('private_file_permissions_or_bound')
    return p.read_bytes()
def pinned_file(record,*,private=False,max_bytes=8*1024*1024):
    if type(record)is not dict or set(record)!={'path','sha256'} or not digest(record['sha256']):raise AdmissionRefused('file_pin_required')
    p=Path(record['path'])
    if not p.is_absolute() or p.resolve(strict=True)!=p or not p.is_file() or p.stat().st_size>max_bytes:raise AdmissionRefused('source_path_or_bound')
    b=private_read(p,max_bytes) if private else p.read_bytes()
    if sha(b)!=record['sha256']:raise AdmissionRefused('file_identity_changed')
    return b

def timestamp(value):
    d=datetime.fromisoformat(value)
    if d.tzinfo is None:raise AdmissionRefused('timezone_required')
    return d

@dataclass(frozen=True)
class RootAdmission:
    """Root must construct from independently confirmed approval/evidence, never worker data."""
    config_sha256:str
    approval_ref:str
    funding_approval_ref:str
    expires_at:str
    predecessor_sha256:str
    supervisor_entry_sha256:str

    def validate(self,cfg,raw,now):
        if not digest(self.config_sha256) or sha(raw)!=self.config_sha256:raise AdmissionRefused('independent_config_digest_mismatch')
        if not self.approval_ref or cfg['approval_ref']!=self.approval_ref or cfg['funding_approval_ref']!=self.funding_approval_ref:raise AdmissionRefused('independent_approval_identity_mismatch')
        if cfg['predecessor']['sha256']!=self.predecessor_sha256 or cfg['supervisor']['entry']['sha256']!=self.supervisor_entry_sha256:raise AdmissionRefused('independent_predecessor_or_supervisor_mismatch')
        expiry=timestamp(cfg['expires_at'])
        if expiry>timestamp(self.expires_at) or now+timedelta(seconds=360)>=expiry:raise AdmissionRefused('successor_execution_window_insufficient')

def load(path,root,*,now=None):
    if type(root)is not RootAdmission:raise AdmissionRefused('explicit_root_admission_required')
    if APPROVED_PAIR_REF is None or root.approval_ref != APPROVED_PAIR_REF:
        raise AdmissionRefused('new_pair_approval_pending')
    if Path(path) != APPROVED_PRIVATE_ROOT/'pair.json':raise AdmissionRefused('one_approved_config_path_required')
    raw=private_read(path);cfg=json.loads(raw)
    if type(cfg)is not dict or set(cfg)!=REQUIRED or cfg['schema']!='pex.stockroom-successor.v1':raise AdmissionRefused('successor_config_schema')
    if cfg['run_id'] != APPROVED_RUN_ID or cfg['output_dir'] != str(APPROVED_PRIVATE_ROOT/'run'):raise AdmissionRefused('one_approved_run_identity_required')
    now=now or datetime.now(timezone.utc);root.validate(cfg,raw,now)
    if type(cfg['run_id'])is not str or not cfg['run_id'] or len(cfg['run_id'])>80:raise AdmissionRefused('run_identity_required')
    if type(cfg['sources'])is not dict or set(cfg['sources'])!=REQUIRED_SOURCES:raise AdmissionRefused('complete_source_identity_required')
    for source in cfg['sources'].values():pinned_file(source)
    for name in ('nebius_key','e2b_key'):pinned_file(cfg[name],private=True,max_bytes=65536)
    pinned_file(cfg['binary'],max_bytes=512*1024*1024)
    modules=Path(cfg['modules_path'])
    if not modules.is_absolute() or modules.resolve()!=modules or not modules.is_dir():raise AdmissionRefused('module_path_required')
    predecessor=json.loads(pinned_file(cfg['predecessor'],private=True))
    fields={'schema','closed','worker_charged_nano_usd','supervisor_charged_nano_usd','compute_upper_bound_nano_usd','closed_evidence_sha256'}
    if type(predecessor)is not dict or set(predecessor)!=fields or predecessor['schema']!='pex.cumulative-predecessor.v1' or predecessor['closed'] is not True or not digest(predecessor['closed_evidence_sha256']):raise AdmissionRefused('closed_predecessor_evidence_required')
    prior=predecessor['worker_charged_nano_usd']
    if type(prior)is not dict or set(prior)!={'baseline','pex'} or any(type(v)is not int or not 0<=v<=WORKER_SHARED_OUTER for v in prior.values()):raise AdmissionRefused('worker_prior_bound')
    if prior != PRIOR_WORKERS:raise AdmissionRefused('frozen_worker_predecessor_mismatch')
    for key,cap in [('supervisor_charged_nano_usd',PRIOR_SUPERVISOR),('compute_upper_bound_nano_usd',PRIOR_COMPUTE)]:
        if type(predecessor[key])is not int or predecessor[key]!=cap:raise AdmissionRefused('prior_charge_bound')
    if set(cfg['supervisor'])!={'entry','config'}:raise AdmissionRefused('successor_supervisor_schema')
    # A separately reviewed successor module is mandatory. No legacy loader edit/fallback.
    pinned_file(cfg['supervisor']['entry']);pinned_file(cfg['supervisor']['config'],private=True)
    net=cfg['network']
    if type(net)is not dict or set(net)!={'proxy_sha256','ca'}:raise AdmissionRefused('network_binding_required')
    proxy=os.environ.get('HTTPS_PROXY','');parts=urlsplit(proxy)
    if not proxy or parts.scheme not in ('http','https') or not parts.hostname or parts.path not in ('','/') or parts.query or parts.fragment or sha(proxy.encode())!=net['proxy_sha256']:raise AdmissionRefused('same_execution_platform_proxy_mismatch')
    if os.environ.get('SSL_CERT_FILE')!=net['ca']['path']:raise AdmissionRefused('same_execution_CA_path_mismatch')
    pinned_file(net['ca'])
    package=Path(cfg['package_path'])
    if not package.is_absolute() or package.resolve()!=package or sha((package/'MANIFEST.json').read_bytes())!=TASK_SHA:raise AdmissionRefused('frozen_task_identity_changed')
    out=Path(cfg['output_dir'])
    if not out.is_absolute() or out.parent.resolve()!=out.parent or out.parent.stat().st_mode&0o077:raise AdmissionRefused('private_output_parent_required')
    return cfg,predecessor

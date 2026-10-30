"""Exact retained predecessor inventory for the next, never auto-admitted pair.
All historical unknown reservations remain charged. These are accounting
identities, not permission or a replacement for root source/config review.
"""
PRIOR_PROVIDER=2_892_060_300
PRIOR_COMPUTE=721_245_000
COMPUTE_ENVELOPE=943_245_000  # prior + two111m worst-case reservations, not user cap.
PAIR21_NAMES=('pair21_claim', 'pair21_cleanup_1-receipt', 'pair21_cleanup_2-receipt', 'pair21_cleanup_3-receipt', 'pair21_cleanup_owned-identity', 'pair21_cleanup_result', 'pair21_cleanup_scope', 'pair21_compute', 'pair21_config', 'pair21_interrupted_manifest', 'pair21_owned', 'pair21_recording_qualification', 'pair21_supervisor', 'pair21_workers')
RETROSPECTIVE_FILES=('PRESERVATION.json', 'config.json', 'executed-source/accounting', 'executed-source/managed_chat', 'executed-source/managed_tool_chat', 'executed-source/pex_protocol.actions', 'executed-source/pex_protocol.enums', 'executed-source/pex_protocol.goal', 'executed-source/pex_protocol.redaction', 'executed-source/pex_protocol.session', 'executed-source/pex_protocol.supervisor', 'executed-source/pex_supervisor.evidence_observations', 'executed-source/pex_supervisor.evidence_tools', 'executed-source/pex_supervisor.loop', 'executed-source/process_adapter', 'executed-source/retrospective_review', 'executed-source/review', 'executed-source/stockroom_request', 'executed-source/stockroom_task', 'executed-source/strands_bridge', 'executed-source/successor_admission', 'executed-source/successor_budget', 'executed-source/successor_supervisor', 'executed-source/tool_protocol', 'launch_once.py', 'owner_once.py', 'predecessor.json', 'request.json', 'run/admission.json', 'run/launch.claim', 'run/main_before_model_and_credential.json', 'run/supervisor.sqlite', 'run/supervisor.sqlite-journal', 'run/wire/65be5209758d7c9a0278320065471526ae40d9b2c7ee3d17e5f4fa51948dcd85.json', 'same-exec-owner.json', 'trusted_root_grant.py')
def retrospective_name(path):return 'retrospective01_'+path.replace('/','__')
PAIR05_FILES=('PRESERVATION.json','pair.json','predecessor.json','launch.claim','launcher-admission.json','compute.sqlite','run/workers.sqlite','run/supervisor.sqlite','poll-denial.json','cleanup-current/scope.json','cleanup-fullroute-approved/scope.json','cleanup-fullroute-approved/1-receipt.json','cleanup-fullroute-approved/result.json')
def pair05_name(path):return 'asyncpool05_'+path.replace('/','__')
def required_predecessors(legacy):
    return frozenset(legacy)|frozenset(PAIR21_NAMES)|frozenset(retrospective_name(p) for p in RETROSPECTIVE_FILES)|frozenset(pair05_name(p) for p in PAIR05_FILES)

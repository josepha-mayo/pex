"""WIP exact closed-grant worker capability, checked BEFORE key or CLI setup."""
from pathlib import Path
from staged_admission import AdmissionRefused,read_pin
from staged_sdk_binding import SDKTransportBinding


def validate_worker(binding,funding,*,private_root,binary,modules,key_path):
    if type(binding) is not SDKTransportBinding:raise AdmissionRefused('closed_staged_worker_binding_required')
    binding._check();cfg=binding.admitted.config()
    from staged_funding import PhaseFunding
    from staged_accounting import WorkerPhaseLedger
    if (set(funding or {})!={'baseline','pex'} or any(type(v) is not PhaseFunding or v.mode!='closed-admitted'
            or type(v.ledger) is not WorkerPhaseLedger or v.ledger.owner.binding is not binding
            or v.ledger.arm!=arm for arm,v in funding.items())):
        raise AdmissionRefused('exact_equal_staged_worker_funding_required')
    for value in funding.values():value.ledger.owner.before_reserve()
    cli=cfg['cli']
    if (Path(private_root)!=Path(cfg['output_dir'])/'cli' or str(Path(binary))!=cli['binary']['path']
            or str(Path(modules))!=cli['modules_path'] or str(Path(key_path))!=cfg['nebius_key']['path']
            or cli['plugin_package']['path']!=str(Path(modules)/'@opencode/plugin/package.json')):
        raise AdmissionRefused('frozen_staged_worker_paths_required')
    read_pin(cli['binary'],limit=512*1024*1024);read_pin(cli['plugin_package'])
    read_pin(cfg['nebius_key'],private=True,limit=16384)
    return cfg

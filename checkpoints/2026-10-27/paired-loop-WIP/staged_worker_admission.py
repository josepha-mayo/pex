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


def bind_child_environment(binding, environment):
    """Same-process ordinary route/CA inheritance; no global settings changed.

    Bun1.4.4's SSL_CERT_FILE support is qualified by local TLS/CONNECT probes.
    It adds the approved CA to Bun's bundled roots, NOT an exclusive trust store
    and NOT proof of the real provider route. Never substitute another proxy,
    add a trust bypass, or return/log current proxy credentials separately.
    """
    import os
    import re
    from urllib.parse import urlsplit
    from staged_admission import sha
    if type(binding) is not SDKTransportBinding:
        raise AdmissionRefused('closed_staged_worker_binding_required')
    binding._check();cfg=binding.admitted.config()
    if type(environment) is not dict or any(type(k) is not str or type(v) is not str for k,v in environment.items()):
        raise AdmissionRefused('explicit_string_child_environment_required')
    result=dict(environment);proxy=result.get('HTTPS_PROXY','')
    if not proxy or sha(proxy.encode())!=cfg['network']['proxy_sha256']:
        raise AdmissionRefused('child_ordinary_proxy_identity_changed')
    for name in ('HTTP_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        if result.get(name) not in (None,'',proxy):
            raise AdmissionRefused('ambiguous_child_proxy_alias_refused')
    host='api.tokenfactory.nebius.com'
    for name in ('NO_PROXY','no_proxy'):
        for token in re.split(r'[,\s]+',result.get(name,'')):
            token=token.lower()
            if not token:continue
            if token=='*':raise AdmissionRefused('provider_proxy_bypass_refused')
            # A port-specific bypass can match the canonical HTTPS endpoint.
            port=None
            if ':' in token:token,port=token.rsplit(':',1)
            suffix=token.removeprefix('*.').lstrip('.').rstrip('.')
            if host==suffix or host.endswith('.'+suffix):
                # Accept only a proven different numeric port; ambiguous or
                # zero-padded default ports must never become route bypasses.
                if port is None or not port.isdecimal() or int(port)==443:
                    raise AdmissionRefused('provider_proxy_bypass_refused')
    if result.get('NODE_TLS_REJECT_UNAUTHORIZED') not in (None,'1'):
        raise AdmissionRefused('child_TLS_verification_required')
    if any(result.get(n) for n in ('NODE_EXTRA_CA_CERTS','SSL_CERT_DIR','NODE_OPTIONS','BUN_OPTIONS')):
        raise AdmissionRefused('unreviewed_child_TLS_or_runtime_override')
    ca=cfg['network']['ca']['path']
    if os.environ.get('SSL_CERT_FILE')!=ca or result.get('SSL_CERT_FILE') not in (None,ca):
        raise AdmissionRefused('child_ordinary_CA_identity_changed')
    read_pin(cfg['network']['ca'],limit=4*1024*1024)
    result['SSL_CERT_FILE']=ca  # Existing approved file; never a copied certificate.
    return result

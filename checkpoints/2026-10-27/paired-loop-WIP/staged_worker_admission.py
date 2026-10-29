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
    if any(value.output_token_bound!=cfg['profile']['worker_output_per_call'] for value in funding.values()):
        raise AdmissionRefused('frozen_staged_worker_output_required')
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
    """Recheck exact authority, then the same pure local transport admission."""
    if type(binding) is not SDKTransportBinding:
        raise AdmissionRefused('closed_staged_worker_binding_required')
    binding._check()
    return validate_child_environment(binding.admitted.config(),environment)


def validate_child_environment(cfg,environment):
    """No client/key/claim/network: validate the frozen ordinary HTTPS route."""
    import os
    import re
    from staged_admission import sha,validate_transport
    validate_transport(cfg['network'])
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


LOCAL_REASON_CODES=frozenset((
    'closed_staged_worker_binding_required','explicit_string_child_environment_required',
    'child_ordinary_proxy_identity_changed','ambiguous_child_proxy_alias_refused',
    'provider_proxy_bypass_refused','child_TLS_verification_required',
    'unreviewed_child_TLS_or_runtime_override','child_ordinary_CA_identity_changed',
    'same_process_ordinary_proxy_changed','ordinary_CA_path_changed','pinned_file_changed',
    'local_worker_CLI_identity_changed','local_worker_plugin_identity_changed',
    'local_worker_key_format_unproven','local_worker_CLI_version_unproven',
    'local_worker_CLI_version_timeout','local_worker_preflight_directory_required',
    'parent_environment_changed_during_local_preflight'))


def local_admission_reason(error):
    # Never persist arbitrary exception messages/URLs/headers/credential material.
    value=error.args[0] if isinstance(error,AdmissionRefused) and len(error.args)==1 else None
    return value if type(value)is str and value in LOCAL_REASON_CODES else 'unclassified_local_admission_refusal'


def prepare_child_environment(cfg,profile):
    """Explicit least-privilege child projection, parent environment untouched.

    HTTPS model URL uses the EXISTING pinned HTTPS proxy. Ambient ALL_PROXY is
    an unused fallback for this route (real Bun TLS/CONNECT fixture qualifies
    precedence) and is not inherited. A caller explicitly injecting any
    conflicting alias is still refused by validate_child_environment().
    """
    import os
    profile=Path(profile)
    env={'PATH':'/usr/bin:/bin','HOME':str(profile/'home'),
        'XDG_CONFIG_HOME':str(profile/'config'),'XDG_DATA_HOME':str(profile/'data'),
        'XDG_CACHE_HOME':str(profile/'cache'),'XDG_STATE_HOME':str(profile/'state'),
        'LANG':'C.UTF-8','TERM':'dumb','OPENCODE_DISABLE_MODELS_FETCH':'1',
        'OPENCODE_DISABLE_AUTOUPDATE':'1','OPENCODE_DISABLE_FREE_MODELS':'1'}
    for name in ('HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy'):
        if name in os.environ:env[name]=os.environ[name]
    env['NO_PROXY']=env.get('NO_PROXY','')+',127.0.0.1,localhost'
    env['no_proxy']=env.get('no_proxy',env['NO_PROXY'])+',127.0.0.1,localhost'
    return validate_child_environment(cfg,env)


def preflight_worker_configuration(cfg,directory,*,check_credentials=False):
    """Exact production child path + pinned CLI --version BEFORE any VM/claim.

    No SDK/client, model call, provider result, proxy/CA replacement or parent
    environment edit. Before a trusted Grant, credentials are not opened; the
    final launcher repeats with existing credential pins checked locally.
    """
    import hashlib,json,os,subprocess,tempfile
    from nebius_worker import PIN
    from staged_admission import sha
    directory=Path(directory)
    if (not directory.is_absolute() or directory.resolve()!=directory or not directory.is_dir()
            or directory.stat().st_mode&0o077):raise AdmissionRefused('local_worker_preflight_directory_required')
    raw=read_pin(cfg['cli']['binary'],limit=512*1024*1024)
    if hashlib.sha256(raw).hexdigest()!=PIN:raise AdmissionRefused('local_worker_CLI_identity_changed')
    package=json.loads(read_pin(cfg['cli']['plugin_package']))
    if package.get('version')!='2.1.4':raise AdmissionRefused('local_worker_plugin_identity_changed')
    if check_credentials:
        for name in ('nebius_key','e2b_key'):
            try:secret=read_pin(cfg[name],private=True,limit=16384).decode('ascii').strip()
            except UnicodeError:raise AdmissionRefused('local_worker_key_format_unproven') from None
            if not secret or '\n' in secret or '\r' in secret:raise AdmissionRefused('local_worker_key_format_unproven')
            del secret
    parent=dict(os.environ)
    with tempfile.TemporaryDirectory(prefix='.local-worker-preflight-',dir=directory) as temporary:
        env=prepare_child_environment(cfg,Path(temporary)/'profile')
        try:
            version=subprocess.run([cfg['cli']['binary']['path'],'--version'],cwd=temporary,
                env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        except subprocess.TimeoutExpired:raise AdmissionRefused('local_worker_CLI_version_timeout') from None
        if version.returncode!=0 or version.stdout.strip()!=b'opencode v2.1.4':
            raise AdmissionRefused('local_worker_CLI_version_unproven')
        if os.environ!=parent:raise AdmissionRefused('parent_environment_changed_during_local_preflight')
        return {'schema':'pex.local-worker-preflight.v1','status':'passed',
            'qualification':'local_admission_and_CLI_version_only_NOT_inference',
            'binary_sha256':cfg['cli']['binary']['sha256'],'CLI_version':'2.1.4',
            'canonical_HTTPS_proxy_identity_preserved':sha(env['HTTPS_PROXY'].encode())==cfg['network']['proxy_sha256'],
            'ALL_PROXY_fallbacks_not_inherited':not any(n in env for n in ('ALL_PROXY','all_proxy')),
            'approved_CA_path_unchanged':env['SSL_CERT_FILE']==cfg['network']['ca']['path'],
            'parent_environment_unchanged':True,'existing_credential_pins_checked':check_credentials,
            'SDK_clients_or_claims_created':0,'provider_or_model_calls':0}

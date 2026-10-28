"""Root-only prelaunch handoff; never grants provider/resource authority.

Replace the preparing interpreter so the once-only launcher gets a fresh Python
process but inherits the CURRENT ordinary platform environment unchanged. Never
persist/copy proxy credentials or relax successor admission. The launcher still
owns the exclusive claim and all original source/config/budget/transport checks.
"""
import json
import os
from pathlib import Path
import sys
from successor_admission import AdmissionRefused, private_read, pinned_file, sha


def exec_verified_launcher(*, config_path, config_sha256, launcher_sha256):
    config_path = Path(config_path)
    raw = private_read(config_path)
    if sha(raw) != config_sha256:
        raise AdmissionRefused('handoff_config_identity_changed')
    cfg = json.loads(raw)
    proxy = os.environ.get('HTTPS_PROXY', '')
    if not proxy or sha(proxy.encode()) != cfg['network']['proxy_sha256']:
        raise AdmissionRefused('same_execution_platform_proxy_mismatch')
    ca = cfg['network']['ca']
    if os.environ.get('SSL_CERT_FILE') != ca['path']:
        raise AdmissionRefused('same_execution_CA_path_mismatch')
    pinned_file(ca)
    launcher = config_path.with_name('launch_once.py')
    if sha(private_read(launcher)) != launcher_sha256:
        raise AdmissionRefused('handoff_launcher_identity_changed')
    # execv deliberately inherits os.environ. No replacement env dictionary,
    # proxy extraction, shell, transport override or retry is involved.
    os.execv(sys.executable, [sys.executable, str(launcher),
                             '--execute-exact-approved-pair', config_sha256])
    raise RuntimeError('execv_unexpectedly_returned')

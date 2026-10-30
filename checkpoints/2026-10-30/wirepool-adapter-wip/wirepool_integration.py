"""Task-only composition components; no admission, transport or dispatch authority."""
from pathlib import Path
from wirepool_adapter import load_public_package,stage_public,build_monitor_request


def stage(package,directory):
    frozen=load_public_package(package);directory=Path(directory)
    if not directory.is_absolute() or directory.resolve()!=directory or directory.exists():raise ValueError('fresh_stage_required')
    (directory/'workers').mkdir(parents=True,mode=0o700)
    values=[stage_public(frozen,directory/'workers'/arm) for arm in ('baseline','pex')]
    if values[0]!=values[1]:raise ValueError('equal_public_bytes_required')
    return values[0],frozen.initial_prompt


def make_public_request(package):
    frozen=load_public_package(package)
    return lambda arm,observation,session_id:build_monitor_request(frozen,arm,observation,session_id)


def frozen_inputs(package):
    frozen=load_public_package(package)
    return frozen.public_sha256,frozen.initial_prompt+'\n\n'+frozen.files['TASK.md'].decode()

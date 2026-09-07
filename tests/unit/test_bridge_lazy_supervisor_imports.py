"""Local bridge startup must not eagerly initialize a model-provider SDK."""

import os
import subprocess
import sys


def test_bridge_without_a_model_does_not_import_strands(tmp_path):
    environment = {name: value for name, value in os.environ.items() if not name.startswith("PEX_")}
    environment.update({
        "PEX_HOME": str(tmp_path), "PEX_SUPERVISOR_DISABLE": "1",
        "PEX_CLOUD_REASONING": "false", "PEX_CODEX_ATTACH": "false",
        "PEX_CURSOR_ATTACH": "false",
    })
    script = """
import importlib.abc
import sys

class NoEagerStrands(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'strands' or fullname.startswith('strands.'):
            raise RuntimeError('Strands must load only for model setup or semantic invocation')
        return None

sys.meta_path.insert(0, NoEagerStrands())
from pex_bridge.app import create_app, state
from pex_supervisor.providers import load_supervisor_model
assert state.pipeline.model is None
assert load_supervisor_model() is None
assert create_app().title == 'PEX Bridge'
assert 'strands' not in sys.modules
print('bridge_without_model_ready')
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=environment, cwd=tmp_path,
        capture_output=True, text=True, timeout=90,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "bridge_without_model_ready"

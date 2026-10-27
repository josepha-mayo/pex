"""Fresh-process combined authored suite; no real worker/provider/VM calls."""
from pathlib import Path
from process_adapter import initialize_process
initialize_process()
import pytest
own=Path(__file__).resolve().parent
adapter=own.parent/'pex-stockroom-adapter-WIP-20261027-1432'
raise SystemExit(pytest.main(['-q',str(own/'test_successor.py'),str(own/'test_successor_supervisor.py'),str(own/'test_pending_budget.py'),str(adapter/'test_stockroom_adapter.py'),str(adapter/'test_stockroom_request.py')]))

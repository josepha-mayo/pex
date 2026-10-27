"""Run in fresh isolated interpreter with explicit trusted local source roots only."""
from pathlib import Path
from process_adapter import initialize_process
initialize_process()
import pytest
raise SystemExit(pytest.main(['-q',str(Path(__file__).with_name('test_successor_supervisor.py'))]))

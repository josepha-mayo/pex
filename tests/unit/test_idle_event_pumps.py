from __future__ import annotations

from dataclasses import dataclass

from pex_bridge import app as app_module


@dataclass
class _PumpAdapter:
    name: str
    started: list[str]
    transport: object | None = None

    def start_pipeline_pump(self, _ingest) -> None:
        self.started.append(self.name)


@dataclass
class _AcpPumpAdapter:
    name: str
    started: list[str]
    acp: object | None = None

    def start_pipeline_pump(self, _ingest) -> None:
        self.started.append(self.name)


@dataclass
class _AlwaysOnPumpAdapter:
    name: str
    started: list[str]

    def start_pipeline_pump(self, _ingest) -> None:
        self.started.append(self.name)


class _Registry:
    def __init__(self, adapters: list[object]) -> None:
        self._adapters = adapters

    def all(self) -> list[object]:
        return self._adapters


def test_event_pumps_start_only_for_adapters_with_an_event_source(monkeypatch) -> None:
    started: list[str] = []
    http = _PumpAdapter("http", started)
    acp = _AcpPumpAdapter("acp", started)
    configured = _PumpAdapter("configured", started, transport=object())
    always_on = _AlwaysOnPumpAdapter("always-on", started)
    registry = _Registry([http, acp, configured, always_on])
    monkeypatch.setattr(app_module.state, "adapters", registry)

    app_module._start_event_pumps()

    assert started == ["configured", "always-on"]

    http.transport = object()
    acp.acp = object()
    started.clear()
    app_module._start_event_pumps()

    assert started == ["http", "acp", "configured", "always-on"]

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEX_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 7420
    home: Path = Field(default_factory=lambda: Path.home() / ".pex")
    autonomy: str = "manage"
    cloud_reasoning: bool = True
    require_auth: bool = True
    token: str | None = None
    db_path: Path | None = None
    supervisor_mode: str = "local"  # local | agentcore | hybrid
    agentcore_url: str | None = None
    opencode_url: str | None = None
    qwen_url: str | None = None
    qwen_token: str | None = None
    devin_url: str | None = None
    devin_token: str | None = None
    devin_org_id: str | None = None
    codex_bin: str | None = None
    codex_attach: bool = True
    cursor_agent: str | None = None
    cursor_attach: bool = False
    max_recent_events: int = 80
    suppress_routine_success: bool = True

    @property
    def data_dir(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path:
            return self.db_path
        return self.data_dir / "pex.sqlite"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "bridge.token"

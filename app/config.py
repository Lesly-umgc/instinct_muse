from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Engine selection: "opencode_server" (local OpenCode CLI, no API key needed
    # once the CLI is logged in) or "zen_api" (OpenCode Zen API key).
    app_version: str = "0.1.6"

    default_engine: str = "opencode_server"

    # OpenCode server adapter. If opencode_server_url is empty, the gateway
    # spawns `opencode serve` itself when the CLI is detected on PATH.
    opencode_server_url: str = ""
    opencode_server_password: str = ""
    opencode_binary: str = "opencode"
    opencode_server_port: int = 4096

    # Legacy direct API provider (zen_api engine).
    model_provider: str = "opencode_zen"
    opencode_api_key: str = ""
    opencode_base_url: str = "https://opencode.ai/zen/v1"
    model: str = "big-pickle"

    # Local app state. SQLite is the default for the Mac app; Postgres
    # (database_url) remains for the optional server deploy.
    data_dir: str = str(Path.home() / ".instinct_muse")
    db_path: str = ""  # default: <data_dir>/muse.db
    database_url: str = "postgresql://muse:muse@localhost:5432/muse"

    broker_socket: str = "/run/muse/broker.sock"
    egress_allowlist: str = "opencode.ai"
    max_agent_steps: int = 12

    @property
    def resolved_db_path(self) -> str:
        if self.db_path:
            return self.db_path
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        return str(Path(self.data_dir) / "muse.db")


settings = Settings()

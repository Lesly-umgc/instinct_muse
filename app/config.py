from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    model_provider: str = "opencode_zen"
    opencode_api_key: str = ""
    opencode_base_url: str = "https://opencode.ai/zen/v1"
    model: str = "big-pickle"

    database_url: str = "postgresql://muse:muse@localhost:5432/muse"
    broker_socket: str = "/run/muse/broker.sock"
    egress_allowlist: str = "opencode.ai"
    max_agent_steps: int = 12


settings = Settings()

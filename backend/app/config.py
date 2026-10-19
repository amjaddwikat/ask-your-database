from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables (or a local .env file).

    Startup fails fast with a clear validation error if anything required is missing.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API
    api_key: SecretStr = Field(description="Clients send this in the X-API-Key header")
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    log_level: str = "INFO"

    # Data warehouse the agents query. Use a READ-ONLY database user here.
    warehouse_url: SecretStr = Field(
        description="e.g. mysql+aiomysql://readonly:pass@localhost:3306/telecom_dw"
    )
    warehouse_schemas: list[str] = ["telecom_dw"]
    query_timeout_ms: int = 5_000
    max_result_rows: int = 500

    # Application database (conversation memory). Can be the same server, different schema.
    app_db_url: SecretStr = Field(description="e.g. mysql+aiomysql://app:pass@localhost:3306/app")
    history_window: int = 10

    # LLM
    gemini_api_key: SecretStr
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_s: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment

"""Central configuration.

Every tunable value lives here and is read from the environment (or a local
.env file), so the whole system can be configured from docker compose without
touching code. Keep this module boring and flat on purpose.
"""

from __future__ import annotations

from datetime import time
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_time(value: str) -> time:
    """Parse an "HH:MM" string into a datetime.time."""
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


class Settings(BaseSettings):
    """All configurable values for the MCP server and the ingestion script."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Postgres -----------------------------------------------------------
    pg_host: str = "db"
    pg_port: int = 5432
    pg_user: str = "app"
    pg_password: str = "app"
    pg_db: str = "municipal"

    # --- Embedding service --------------------------------------------------
    embedding_service_url: str = "http://embedder:8000"
    embedding_model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dim: int = 1024
    # sentence-transformers prompt name used for QUERIES only (documents get none).
    embedding_query_prompt_name: str = "query"

    # --- Hybrid retrieval ---------------------------------------------------
    # alpha weights the vector arm vs the lexical arm in RRF fusion.
    # 1.0 = pure vector, 0.0 = pure lexical. vector_search_enabled is a hard
    # switch that turns the vector arm off regardless of alpha.
    retrieval_alpha: float = 0.5
    vector_search_enabled: bool = True
    rrf_k: int = 60
    retrieval_top_k: int = 5

    # --- Appointments / slots ----------------------------------------------
    appointment_duration_minutes: int = 30
    # Python weekday() numbering: Monday=0 .. Sunday=6.
    office_open_days: str = "0,1,2,3,4"
    office_open_time: str = "09:00"
    office_close_time: str = "12:30"
    booking_timezone: str = "Europe/Rome"

    # --- MCP server ---------------------------------------------------------
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000
    mcp_path: str = "/mcp"
    # When empty, the server requires no authentication (fine for a local demo).
    mcp_auth_token: str = ""

    @property
    def pg_dsn(self) -> str:
        """Standard libpq connection string used by psycopg."""
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def open_weekdays(self) -> set[int]:
        """Set of open weekdays using Python's Monday=0 numbering."""
        return {int(d) for d in self.office_open_days.split(",") if d.strip()}

    @property
    def open_time(self) -> time:
        return _parse_time(self.office_open_time)

    @property
    def close_time(self) -> time:
        return _parse_time(self.office_close_time)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

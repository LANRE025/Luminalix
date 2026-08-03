"""Application configuration, loaded from environment variables (and `.env`).

Values can be overridden with the usual environment variables (e.g.
``VERTEX_PROJECT``). Run the backend from the ``backend/`` directory and it
picks up ``backend/.env`` automatically.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Backend package root, i.e. the `backend/` directory. Used to resolve default
# file paths against the repo layout regardless of the process working directory.
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Settings for the Outbreak Vulnerability Sentinel backend."""

    # Vertex AI. Auth uses Google Cloud Application Default Credentials (ADC) —
    # set up locally via `gcloud auth application-default login` — not an API key.
    vertex_project: str = ""
    vertex_location: str = "us-central1"

    # Gemini Developer API. Kept only as a legacy fallback; Vertex AI is the
    # active backend and does not use an API key. Model defaults to
    # `gemini-3.5-flash`; override via GEMINI_MODEL in backend/.env if needed.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    # DataHub GMS / MCP connection (see backend/.env: DATAHUB_GMS_URL, DATAHUB_TOKEN).
    datahub_gms_url: str = "http://localhost:8080"
    datahub_token: str = ""

    # Agent tuning.
    staleness_threshold_days: int = 30
    admissions_lookback_days: int = 14

    # Where the latest run report is persisted. Relative values resolve against
    # the process working directory; the default is anchored to the repo root.
    report_file_path: Path = BACKEND_DIR.parent / "data" / "latest_report.json"

    # Allowed frontend origins for CORS. pydantic-settings parses JSON lists.
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()

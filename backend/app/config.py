"""Application configuration, loaded from environment variables (and `.env`).

Values can be overridden with the usual environment variables (e.g.
``GEMINI_API_KEY``). Run the backend from the ``backend/`` directory and it
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

    # Gemini API. `gemini-2.5-pro` was fixed in the hackathon scaffold and is
    # still operational, but it was deprecated in June 2026 (shutdown planned for
    # 16 Oct 2026). The official replacement is `gemini-3.1-pro-preview`; set
    # GEMINI_MODEL to override once you are ready to migrate.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"

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

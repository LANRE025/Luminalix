"""Persistence for per-source re-ingestion status, one JSON file per source.

Mirrors the ``ReportStore`` pattern from report_store.py: no database needed,
each source's latest re-ingestion result is read/written as a single JSON file
under ``data/ingestion/status/<source>.json``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class IngestionStatusStore:
    """Reads/writes the latest re-ingestion result per source as one JSON file."""

    def __init__(self, dir_path: Path) -> None:
        self._dir = Path(dir_path)

    @property
    def dir_path(self) -> Path:
        """Absolute path of the directory this store manages."""
        return self._dir

    def _path(self, source_name: str) -> Path:
        return self._dir / f"{source_name}.json"

    def load(self, source_name: str) -> dict | None:
        """Return the latest re-ingestion result for a source, or ``None``."""
        path = self._path(source_name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load ingestion status for %s: %s", source_name, exc)
            return None

    def save(self, source_name: str, status: dict) -> None:
        """Persist a re-ingestion result, creating parent directories as needed."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(source_name)
        path.write_text(json.dumps(status, indent=2), encoding="utf-8")
        logger.info("Saved ingestion status for %s to %s", source_name, path)

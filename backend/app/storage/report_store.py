"""Persistence for the latest agent run, backed by a single JSON file.

No database needed for hackathon scope — the whole ``VulnerableRegionsReport``
is read/written as one JSON file (default ``data/latest_report.json``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.models.schemas import VulnerableRegionsReport

logger = logging.getLogger(__name__)


class ReportStore:
    """Reads and writes the latest ``VulnerableRegionsReport`` as one file."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        """Absolute path of the report file this store manages."""
        return self._path

    def load(self) -> VulnerableRegionsReport | None:
        """Return the latest report, or ``None`` if it does not exist / is corrupt."""
        if not self._path.exists():
            return None
        try:
            raw = self._path.read_text(encoding="utf-8")
            return VulnerableRegionsReport.model_validate_json(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load report from %s: %s", self._path, exc)
            return None

    def save(self, report: VulnerableRegionsReport) -> None:
        """Persist the report, creating parent directories as needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Saved report to %s", self._path)

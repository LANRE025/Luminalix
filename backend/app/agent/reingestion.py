"""reingestion.py

Manual, on-demand re-ingestion of a defined data source.

This module is ONLY ever called by an explicit user action — the
POST /ingestion/run/{source} API endpoint (which the frontend "Reingest"
button calls). There is no scheduler, cron, or background timer here: a
re-ingestion starts because a user asked for it.

Flow for a given source (see ingestion_sources.py):
  1. Acquire the input — download the source URL (covid) or read the
     existing local file (tb/malaria/influenza).
  2. Run the source's process step to regenerate data/processed/*.csv.
  3. Run the shared tail pipeline: combine all processed + synthetic rows
     into data/combined/regional_survey_data.csv and regenerate the derived
     synthetic datasets (all existing scripts in data/ingestion/ — nothing
     is re-implemented here).
  4. Rebuild BOTH SQLite DBs atomically (temp file + os.replace swap):
       - data/luminalix.db            <- the DB the agent queries
       - data/combined/luminalix.db   <- the DB DataHub ingests
  5. Trigger the existing DataHub CLI recipe:
       datahub ingest -c data/ingestion/recipe_sqlite_all_datasets.yml

Failure handling mirrors write_finding(): the whole body is wrapped in
try/except with logger.exception, and the caller always gets a result dict
back (never an exception) with the same shape as /agent/status.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from app.agent.ingestion_sources import (
    DATAHUB_RECIPE,
    INGESTION_SOURCES,
    REPO_ROOT,
)

logger = logging.getLogger(__name__)

# Shared tail pipeline run after every source's process step. All are existing
# scripts in data/ingestion/ and are safe to re-run (deterministic/seeded).
_PROCESS_STEPS = [
    "data/ingestion/combine_regional_survey_data.py",
    "data/ingestion/generate_synthetic_diseases.py",
    "data/ingestion/generate_hospital_admissions.py",
    "data/ingestion/generate_resource_allocation.py",
]

_AGENT_DB = REPO_ROOT / "data" / "luminalix.db"
_DATAHUB_DB = REPO_ROOT / "data" / "combined" / "luminalix.db"

# On Windows os.replace fails while the live DB is held open by an in-flight
# reader (e.g. a polling API request, or a transient lock held by Windows
# Defender / Search Indexer on a freshly-written file), so retry the swap with
# a short backoff. The transient indexer/AV lock on a newly-swapped file can
# persist for ~60-90s, so the window is sized to outlast it (~2 minutes).
_SWAP_RETRIES = 60
_SWAP_RETRY_DELAY_S = 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    """Run a command, streaming its output to the log, and raise on failure."""
    logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout is not None:
        for line in proc.stdout:
            logger.info("[ingest] %s", line.rstrip())
    returncode = proc.wait()
    if returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {returncode}: {' '.join(cmd)}"
        )


def _download(url: str, dest: Path) -> None:
    """Download a URL to a local file, replacing any existing copy."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s -> %s", url, dest)
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - pinned source URL
        data = response.read()
    dest.write_bytes(data)
    logger.info("Downloaded %d bytes", len(data))


def _build_db(script: str, tmp_path: Path, final_path: Path) -> None:
    """Rebuild one SQLite DB into a temp file, then atomically swap it in.

    Using a temp file + os.replace means a failure mid-build never leaves the
    live DB in a partially-replaced state. On Windows the destination can be
    briefly held open by an in-flight reader, which makes os.replace fail with
    a transient PermissionError — so retry the swap before giving up.
    """
    final_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [sys.executable, str(REPO_ROOT / script), "--db", str(tmp_path)],
        cwd=REPO_ROOT,
    )
    for attempt in range(_SWAP_RETRIES):
        try:
            os.replace(tmp_path, final_path)
            logger.info("Atomically swapped %s -> %s", tmp_path, final_path)
            return
        except OSError as exc:
            if attempt == _SWAP_RETRIES - 1:
                raise
            logger.warning(
                "Swap %s -> %s blocked (attempt %d/%d): %s; retrying",
                tmp_path,
                final_path,
                attempt + 1,
                _SWAP_RETRIES,
                exc,
            )
            time.sleep(_SWAP_RETRY_DELAY_S)


def _count_survey_rows(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM regional_survey_data").fetchone()
    return int(row[0]) if row else 0


def _resolve_datahub_cli() -> str:
    exe = shutil.which("datahub")
    if exe:
        return exe
    candidate = REPO_ROOT / "datahub-venv" / "Scripts" / "datahub.exe"
    if candidate.exists():
        return str(candidate)
    raise RuntimeError("datahub CLI not found on PATH or in datahub-venv/Scripts")


def run_reingestion(source_name: str, *, datahub_token: str = "") -> dict:
    """Re-ingest one named source from the registry.

    Returns a result dict mirroring the /agent/status shape:
        {source, status, rows_ingested, started_at, completed_at, error_message}
    `status` is "complete" or "error". Never raises — failures are logged and
    returned inside the dict.
    """
    started = _now_iso()
    result = {
        "source": source_name,
        "status": "error",
        "rows_ingested": 0,
        "started_at": started,
        "completed_at": None,
        "error_message": None,
    }

    try:
        source = INGESTION_SOURCES.get(source_name)
        if source is None:
            raise ValueError(f"Unknown ingestion source: {source_name!r}")

        # 1. Acquire the input.
        if source.input_type == "url":
            dest = REPO_ROOT / "data" / "raw" / source.raw_filename
            _download(source.input, dest)
        else:
            dest = source.input_path
            if dest is None or not dest.exists():
                raise FileNotFoundError(
                    f"Input file not found for source {source_name!r}: {dest}"
                )

        # 2. Run this source's process step.
        cmd = [sys.executable, str(REPO_ROOT / source.process_script)]
        if source.process_arg:
            cmd.append(source.process_arg)
        _run(cmd, cwd=REPO_ROOT)

        # 3. Shared tail: combine + derived synthetic datasets.
        for step in _PROCESS_STEPS:
            _run([sys.executable, str(REPO_ROOT / step)], cwd=REPO_ROOT)

        # 4. Rebuild both SQLite DBs atomically.
        tmp_agent = _AGENT_DB.with_suffix(".tmp")
        tmp_datahub = _DATAHUB_DB.with_suffix(".tmp")
        try:
            _build_db("data/ingestion/build_sqlite_db.py", tmp_agent, _AGENT_DB)
            _build_db(
                "data/ingestion/load_csvs_to_sqlite.py", tmp_datahub, _DATAHUB_DB
            )
        finally:
            for tmp in (tmp_agent, tmp_datahub):
                if tmp.exists():
                    tmp.unlink(missing_ok=True)

        result["rows_ingested"] = _count_survey_rows(_AGENT_DB)

        # 5. DataHub CLI ingestion.
        env = os.environ.copy()
        if datahub_token:
            env["DATAHUB_TOKEN"] = datahub_token
        _run(
            [_resolve_datahub_cli(), "ingest", "-c", str(REPO_ROOT / DATAHUB_RECIPE)],
            cwd=REPO_ROOT,
            env=env,
        )

        result.update(status="complete", completed_at=_now_iso())
        logger.info(
            "Re-ingestion of '%s' complete: %d survey rows",
            source_name,
            result["rows_ingested"],
        )
    except Exception as exc:  # noqa: BLE001 - never propagate; return the error
        logger.exception("Re-ingestion of '%s' failed", source_name)
        result.update(error_message=str(exc), completed_at=_now_iso())

    return result

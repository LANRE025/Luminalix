"""
data_access.py

The agent's REAL data layer. Region-level values (survey staleness,
admissions trends, resource levels) are queried directly from SQLite —
not through DataHub MCP, because DataHub's MCP server has no tool that
returns row-level data. Region is a column value, not a DataHub entity,
so there's no per-region metadata surface to query there at all.

This is the correct architecture, not a workaround: in a real DataHub
deployment, this same role would be played by a warehouse client
(Snowflake/BigQuery connector) sitting alongside DataHub, with DataHub
providing schema/lineage/governance context around it. SQLite is our
local stand-in for that warehouse.

DataHub MCP (see datahub_client.py) is used for what it actually can do:
dataset-level freshness/schema/lineage, and writing findings back as
discoverable annotations on the dataset entities.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Anchor to the repo root (<repo>/backend/app/agent -> <repo>) so the SQLite DB
# is found regardless of the process working directory (uvicorn runs from
# backend/, the ingestion scripts from the repo root).
REPO_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = REPO_ROOT / "data" / "luminalix.db"


@dataclass
class RegionSurveyRow:
    region: str
    country: str
    disease: str
    last_survey_date: datetime
    reported_case_rate: float
    data_source: str
    days_stale: int


@dataclass
class AdmissionsTrend:
    region: str
    daily_counts: list[int]
    first_value: int
    last_value: int
    pct_change: float


@dataclass
class ResourceLevel:
    region: str
    country: str
    funding_level_pct_of_avg: float
    staff_count: int
    vaccine_stock_units: int


class DataAccess:
    """Direct SQLite access to region-level values. Synchronous and simple
    on purpose — this is a hackathon-scale local database, not a
    production warehouse client."""

    def __init__(self, db_path: Path = DB_PATH, reference_date: datetime | None = None):
        self.db_path = db_path
        # reference_date lets you pin "today" for reproducible staleness
        # calculations instead of relying on wall-clock time everywhere.
        self.reference_date = reference_date or datetime.utcnow()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_regions(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT region FROM regional_survey_data"
            ).fetchall()
        return [r["region"] for r in rows]

    def get_survey_row(self, region: str) -> RegionSurveyRow | None:
        """Returns the most recent survey entry for a region (if a region
        has multiple disease rows, returns the single most recent one —
        callers needing all diseases for a region should use
        get_all_survey_rows instead)."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM regional_survey_data
                   WHERE region = ?
                   ORDER BY last_survey_date DESC LIMIT 1""",
                (region,),
            ).fetchone()

        if row is None:
            return None

        last_date = datetime.fromisoformat(row["last_survey_date"])
        days_stale = (self.reference_date - last_date).days

        return RegionSurveyRow(
            region=row["region"], country=row["country"], disease=row["disease"],
            last_survey_date=last_date, reported_case_rate=row["reported_case_rate"],
            data_source=row["data_source"], days_stale=days_stale,
        )

    def get_all_survey_rows(self, region: str) -> list[RegionSurveyRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM regional_survey_data WHERE region = ?", (region,)
            ).fetchall()

        result = []
        for row in rows:
            last_date = datetime.fromisoformat(row["last_survey_date"])
            result.append(RegionSurveyRow(
                region=row["region"], country=row["country"], disease=row["disease"],
                last_survey_date=last_date, reported_case_rate=row["reported_case_rate"],
                data_source=row["data_source"],
                days_stale=(self.reference_date - last_date).days,
            ))
        return result

    def get_admissions_trend(self, region: str, lookback_days: int = 14) -> AdmissionsTrend:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT date, admission_count FROM hospital_admissions
                   WHERE region = ? ORDER BY date ASC LIMIT ?""",
                (region, lookback_days),
            ).fetchall()

        counts = [r["admission_count"] for r in rows]
        first_value = counts[0] if counts else 0
        last_value = counts[-1] if counts else 0
        pct_change = ((last_value - first_value) / first_value * 100) if first_value else 0.0

        return AdmissionsTrend(
            region=region, daily_counts=counts,
            first_value=first_value, last_value=last_value,
            pct_change=round(pct_change, 1),
        )

    def get_resource_level(self, region: str) -> ResourceLevel | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM resource_allocation WHERE region = ?", (region,)
            ).fetchone()

        if row is None:
            return None

        return ResourceLevel(
            region=row["region"], country=row["country"],
            funding_level_pct_of_avg=row["funding_level_pct_of_avg"],
            staff_count=row["staff_count"],
            vaccine_stock_units=row["vaccine_stock_units"],
        )

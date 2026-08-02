"""Pydantic models for the Outbreak Vulnerability Sentinel.

These mirror the Data Schema section of the scaffold spec and MUST stay in sync
with the TypeScript types in ``frontend/src/types/region.ts``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class VulnerabilityLevel(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"


class Confidence(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class AgentRunStatusValue(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class RegionInfo(BaseModel):
    """Identity of a region as exposed by the DataHub survey dataset."""

    region: str
    country: str


class RegionFreshness(BaseModel):
    """Freshness metadata for one dataset entity (used to detect stale surveys)."""

    region: str
    dataset: str
    last_updated: datetime | None = None
    days_stale: int = 0


class RegionAssessment(BaseModel):
    """A single region flagged by the agent (matches the scaffold schema)."""

    region: str
    country: str
    vulnerability_level: VulnerabilityLevel
    justification: str
    confidence: Confidence
    key_signals: list[str] = Field(default_factory=list)
    days_stale: int
    flagged_at: datetime


class VulnerableRegionsReport(BaseModel):
    """Aggregated report, persisted to ``data/latest_report.json``."""

    generated_at: datetime
    total_regions_evaluated: int
    total_flagged: int
    regions: list[RegionAssessment] = Field(default_factory=list)


class AgentRunStatus(BaseModel):
    """Lifecycle status of the most recent agent run."""

    status: AgentRunStatusValue = AgentRunStatusValue.IDLE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

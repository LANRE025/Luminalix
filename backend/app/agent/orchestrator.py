"""Main agent loop: read data → reason → write back → build report.

The orchestrator depends only on the ``DataHubClient`` *interface*, so the full
loop can be unit-tested (see ``tests/test_orchestrator.py``) before the real MCP
calls are implemented.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agent.datahub_client import DataHubClient
from app.agent.reasoning import GeminiReasoner
from app.config import Settings
from app.models.schemas import (
    RegionAssessment,
    VulnerabilityLevel,
    VulnerableRegionsReport,
)
from app.storage.report_store import ReportStore

logger = logging.getLogger(__name__)

SURVEY_DATASET = "regional_survey_data"
ADMISSIONS_DATASET = "hospital_admissions"
RESOURCES_DATASET = "resource_allocation"

_LEVEL_RANK = {
    VulnerabilityLevel.HIGH: 3,
    VulnerabilityLevel.MODERATE: 2,
    VulnerabilityLevel.LOW: 1,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Orchestrator:
    """Runs one full vulnerability-scan cycle and persists the resulting report."""

    def __init__(
        self,
        settings: Settings,
        datahub: DataHubClient,
        reasoner: GeminiReasoner,
        report_store: ReportStore,
    ) -> None:
        self._settings = settings
        self._datahub = datahub
        self._reasoner = reasoner
        self._store = report_store

    def run(self) -> VulnerableRegionsReport:
        """Execute the scan and return the aggregated, persisted report."""
        regions = self._datahub.get_regions(SURVEY_DATASET)

        # Pull resource levels up front so the regional average can be computed
        # and passed to the model as reference context.
        resource_levels: dict[str, dict[str, float]] = {
            info.region: self._datahub.get_values(info.region, RESOURCES_DATASET)
            for info in regions
        }
        resource_average = _average_resources(resource_levels)

        assessments: list[RegionAssessment] = []
        flagged = 0
        for info in regions:
            freshness = self._datahub.get_freshness(info.region, SURVEY_DATASET)
            if freshness.days_stale < self._settings.staleness_threshold_days:
                logger.info("Region %s not stale (%d days); skipped", info.region, freshness.days_stale)
                continue

            admissions_trend = self._datahub.get_recent_values(
                info.region,
                ADMISSIONS_DATASET,
                self._settings.admissions_lookback_days,
            )

            reasoning = self._reasoner.evaluate_region(
                region=info.region,
                country=info.country,
                days_stale=freshness.days_stale,
                admissions_trend=admissions_trend,
                resources=resource_levels.get(info.region, {}),
                resource_average=resource_average,
            )

            assessment = RegionAssessment(
                region=info.region,
                country=info.country,
                vulnerability_level=reasoning.vulnerability_level,
                justification=reasoning.justification,
                confidence=reasoning.confidence,
                key_signals=reasoning.key_signals,
                days_stale=freshness.days_stale,
                flagged_at=_now(),
            )

            if assessment.vulnerability_level in (
                VulnerabilityLevel.MODERATE,
                VulnerabilityLevel.HIGH,
            ):
                self._datahub.write_annotation(
                    region=info.region,
                    dataset=SURVEY_DATASET,
                    assessment=assessment,
                )
                assessments.append(assessment)
                flagged += 1
            else:
                logger.info("Region %s assessed as Low; not flagged", info.region)

        # Sort by vulnerability level (High first), then by staleness (days).
        assessments.sort(key=lambda a: (_LEVEL_RANK[a.vulnerability_level], a.days_stale), reverse=True)

        report = VulnerableRegionsReport(
            generated_at=_now(),
            total_regions_evaluated=len(regions),
            total_flagged=flagged,
            regions=assessments,
        )
        self._store.save(report)
        logger.info("Scan complete: %d regions evaluated, %d flagged", len(regions), flagged)
        return report


def _average_resources(resource_levels: dict[str, dict[str, float]]) -> dict[str, float]:
    """Mean of each resource metric across all regions (empty-safe)."""
    keys: set[str] = set()
    for values in resource_levels.values():
        keys.update(values)
    averages: dict[str, float] = {}
    for key in keys:
        values = [v[key] for v in resource_levels.values() if key in v]
        averages[key] = round(sum(values) / len(values), 2) if values else 0.0
    return averages

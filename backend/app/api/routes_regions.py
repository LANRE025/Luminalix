"""Region query routes, backed by the latest persisted report."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.schemas import (
    RegionAssessment,
    VulnerabilityLevel,
    VulnerableRegionsReport,
)

router = APIRouter(prefix="/regions", tags=["regions"])

_LEVEL_RANK = {
    VulnerabilityLevel.HIGH: 3,
    VulnerabilityLevel.MODERATE: 2,
    VulnerabilityLevel.LOW: 1,
}


def _empty_report() -> VulnerableRegionsReport:
    return VulnerableRegionsReport(
        generated_at=datetime.now(timezone.utc),
        total_regions_evaluated=0,
        total_flagged=0,
        regions=[],
    )


@router.get("/vulnerable", response_model=VulnerableRegionsReport)
async def list_vulnerable_regions(
    request: Request,
    min_level: VulnerabilityLevel = Query(default=VulnerabilityLevel.MODERATE),
    country: str | None = Query(default=None),
) -> VulnerableRegionsReport:
    """Return the latest report, filtered by minimum level and/or country."""
    report = request.app.state.report_store.load() or _empty_report()
    regions = [
        r
        for r in report.regions
        if _LEVEL_RANK[r.vulnerability_level] >= _LEVEL_RANK[min_level]
        and (country is None or r.country.lower() == country.lower())
    ]
    return report.model_copy(update={"regions": regions, "total_flagged": len(regions)})


@router.get("/{region_id}", response_model=RegionAssessment)
async def get_region(request: Request, region_id: str) -> RegionAssessment:
    """Return a single region assessment from the latest report (404 if absent)."""
    report = request.app.state.report_store.load()
    if report is None:
        raise HTTPException(status_code=404, detail="No report available yet — run the agent first.")
    for region in report.regions:
        if region.region == region_id:
            return region
    raise HTTPException(status_code=404, detail=f"Region {region_id!r} not found in the latest report")

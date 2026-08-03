"""
orchestrator.py (corrected)

Key architectural fix from the earlier version: region-level staleness,
admissions trend, and resource levels all come from DataAccess (real
SQLite queries) — NOT from DataHub MCP, which has no concept of a
"region" entity to query. DataHub MCP is used only for what it can
actually do: confirming dataset-level metadata exists/is fresh, and
writing the agent's findings back as a discoverable note on the
regional_survey_data dataset entity.

    for each region (from DataAccess, real data):
        get survey row (real data) -> days_stale
        if stale:
            get admissions trend (real data)
            get resource level (real data)
            ask Gemini to assess vulnerability
            if Moderate/High:
                write_finding via DataHubClient (real MCP write-back)
    compile Highly Vulnerable Regions report
"""

import json
from datetime import datetime
from pathlib import Path

from app.agent.data_access import DataAccess
from app.agent.datahub_client import DataHubClient
from app.agent.reasoning import assess_region, VulnerabilityAssessment  # from reasoning.py (Gemini call)

STALENESS_THRESHOLD_DAYS = 14  # tune based on what your demo data actually shows
MIN_REPORT_LEVEL = "Moderate"
LEVEL_RANK = {"Low": 0, "Moderate": 1, "High": 2}


def run(
    data_access: DataAccess,
    datahub_client: DataHubClient,
    output_path: str = "examples/vulnerable_regions_report.json",
    write_back_enabled: bool = True,
) -> list[dict]:
    flagged_regions: list[dict] = []
    regions = data_access.list_regions()
    print(f"[orchestrator] Evaluating {len(regions)} regions from real data")

    for region in regions:
        survey = data_access.get_survey_row(region)
        if survey is None:
            continue

        if survey.days_stale < STALENESS_THRESHOLD_DAYS:
            continue  # this region's data is current enough, skip

        print(f"[orchestrator] {region}: stale by {survey.days_stale} days ({survey.disease}) — checking proxy signals")

        trend = data_access.get_admissions_trend(region)
        resources = data_access.get_resource_level(region)

        if resources is None:
            print(f"[orchestrator] {region}: no resource data, skipping")
            continue

        assessment: VulnerabilityAssessment = assess_region(
            region=region,
            days_stale=survey.days_stale,
            admissions_trend={
                "first_value": trend.first_value,
                "last_value": trend.last_value,
                "pct_change": trend.pct_change,
            },
            resources={
                "funding_level_pct_of_avg": resources.funding_level_pct_of_avg,
                "staff_count": resources.staff_count,
                "vaccine_stock_units": resources.vaccine_stock_units,
            },
        )

        print(f"[orchestrator] {region}: {assessment.vulnerability_level} (confidence={assessment.confidence})")

        if LEVEL_RANK[assessment.vulnerability_level] < LEVEL_RANK[MIN_REPORT_LEVEL]:
            continue

        if write_back_enabled:
            try:
                datahub_client.write_finding(
                    dataset="regional_survey_data",
                    region=region,
                    vulnerability_level=assessment.vulnerability_level,
                    justification=assessment.justification,
                    confidence=assessment.confidence,
                    key_signals=assessment.key_signals,
                )
            except NotImplementedError:
                # Expected until datahub_client.py's MCP calls are wired
                # against a live session — don't let this block the rest
                # of the demo/report generation.
                print(f"[orchestrator] (write-back not yet wired for {region} — see datahub_client.py TODOs)")

        flagged_regions.append({
            **assessment.to_dict(),
            "days_stale": survey.days_stale,
            "disease": survey.disease,
            "country": survey.country,
            "flagged_at": datetime.utcnow().isoformat(),
        })

    flagged_regions.sort(
        key=lambda r: (LEVEL_RANK[r["vulnerability_level"]], r["days_stale"]),
        reverse=True,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(flagged_regions, f, indent=2, default=str)

    print(f"[orchestrator] Wrote {len(flagged_regions)} flagged regions to {output_path}")
    return flagged_regions


if __name__ == "__main__":
    da = DataAccess()
    dh = DataHubClient(gms_url="http://localhost:8080", token="")
    run(da, dh)

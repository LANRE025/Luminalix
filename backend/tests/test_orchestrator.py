"""Unit tests for the agent orchestrator, using a mocked DataHubClient and a
mocked Gemini response (no live DataHub / Gemini required)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.agent.orchestrator import Orchestrator
from app.agent.reasoning import RegionReasoning, ReasoningError
from app.config import Settings
from app.models.schemas import RegionFreshness, RegionInfo
from app.storage.report_store import ReportStore


def _settings(**overrides) -> Settings:
    return Settings(
        gemini_api_key="test-key",
        gemini_model="test-model",
        staleness_threshold_days=30,
        report_file_path="data/latest_report.json",
        **overrides,
    )


def _region(region: str, country: str = "Kenya") -> RegionInfo:
    return RegionInfo(region=region, country=country)


def _reasoning(
    region: str,
    level: str,
    confidence: str = "High",
    key_signals: list[str] | None = None,
) -> RegionReasoning:
    return RegionReasoning(
        region=region,
        vulnerability_level=level,
        justification=f"Justification for {region}.",
        confidence=confidence,
        key_signals=key_signals or [f"signal for {region}"],
    )


def _build_orchestrator(
    regions: list[RegionInfo],
    stale_days: dict[str, int],
    reasoning_by_region: dict[str, RegionReasoning],
) -> tuple[Orchestrator, Mock, Mock, Mock]:
    datahub = Mock(spec=["get_regions", "get_freshness", "get_recent_values", "get_values", "write_annotation"])
    datahub.get_regions.return_value = regions
    datahub.get_freshness.side_effect = lambda region, dataset: RegionFreshness(
        region=region, dataset=dataset, days_stale=stale_days[region]
    )
    datahub.get_recent_values.return_value = [100.0, 110.0, 120.0, 130.0, 140.0]
    datahub.get_values.return_value = {"funding_usd": 1_000_000.0, "staff_count": 120.0}

    reasoner = Mock(spec=["evaluate_region"])
    reasoner.evaluate_region.side_effect = lambda **kwargs: reasoning_by_region[kwargs["region"]]

    store = Mock(spec=ReportStore)

    orchestrator = Orchestrator(
        settings=_settings(),
        datahub=datahub,
        reasoner=reasoner,
        report_store=store,
    )
    return orchestrator, datahub, reasoner, store


def test_flags_high_and_moderate_but_not_low_or_fresh():
    regions = [_region("Region-A"), _region("Region-B"), _region("Region-C"), _region("Region-D")]
    stale_days = {"Region-A": 45, "Region-B": 40, "Region-C": 10, "Region-D": 60}
    reasoning_by_region = {
        "Region-A": _reasoning("Region-A", "High"),
        "Region-B": _reasoning("Region-B", "Low", confidence="Low"),
        "Region-D": _reasoning("Region-D", "Moderate", confidence="Medium"),
    }

    orchestrator, datahub, reasoner, store = _build_orchestrator(
        regions, stale_days, reasoning_by_region
    )

    report = orchestrator.run()

    assert report.total_regions_evaluated == 4
    assert report.total_flagged == 2
    assert [r.region for r in report.regions] == ["Region-A", "Region-D"]
    assert report.regions[0].days_stale == 45
    assert report.regions[0].country == "Kenya"

    # Fresh region never evaluated; Low region evaluated but not flagged.
    assert reasoner.evaluate_region.call_count == 3
    assert datahub.write_annotation.call_count == 2
    store.save.assert_called_once_with(report)


def test_report_sorted_by_level_then_staleness_desc():
    regions = [_region("Region-A"), _region("Region-B"), _region("Region-C")]
    stale_days = {"Region-A": 50, "Region-B": 70, "Region-C": 90}
    reasoning_by_region = {
        "Region-A": _reasoning("Region-A", "High"),
        "Region-B": _reasoning("Region-B", "Moderate"),
        "Region-C": _reasoning("Region-C", "High"),
    }

    orchestrator, _, _, _ = _build_orchestrator(regions, stale_days, reasoning_by_region)

    report = orchestrator.run()

    # High regions (C has more days_stale than A) come first, then Moderate.
    assert [r.region for r in report.regions] == ["Region-C", "Region-A", "Region-B"]
    assert [r.vulnerability_level for r in report.regions] == ["High", "High", "Moderate"]


def test_no_stale_regions_produces_empty_report():
    regions = [_region("Region-A"), _region("Region-B")]
    stale_days = {"Region-A": 5, "Region-B": 12}
    orchestrator, datahub, reasoner, store = _build_orchestrator(regions, stale_days, {})

    report = orchestrator.run()

    assert report.total_regions_evaluated == 2
    assert report.total_flagged == 0
    assert report.regions == []
    reasoner.evaluate_region.assert_not_called()
    datahub.write_annotation.assert_not_called()
    store.save.assert_called_once_with(report)


def test_reasoner_failure_propagates_for_error_status():
    regions = [_region("Region-A")]
    stale_days = {"Region-A": 45}
    datahub = Mock(spec=["get_regions", "get_freshness", "get_recent_values", "get_values", "write_annotation"])
    datahub.get_regions.return_value = regions
    datahub.get_freshness.side_effect = lambda region, dataset: RegionFreshness(
        region=region, dataset=dataset, days_stale=stale_days[region]
    )
    datahub.get_values.return_value = {}

    reasoner = Mock(spec=["evaluate_region"])
    reasoner.evaluate_region.side_effect = ReasoningError("Gemini is down")

    orchestrator = Orchestrator(
        settings=_settings(),
        datahub=datahub,
        reasoner=reasoner,
        report_store=Mock(spec=ReportStore),
    )

    with pytest.raises(ReasoningError, match="Gemini is down"):
        orchestrator.run()

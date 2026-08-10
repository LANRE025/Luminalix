"""Unit tests for the orchestrator run(), using a fake DataAccess, a mocked
DataHubClient, and a stubbed assess_region (no live SQLite / Gemini / MCP)."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from app.agent.data_access import (
    AdmissionsTrend,
    RegionSurveyRow,
    ResourceLevel,
)
from app.agent.orchestrator import run
from app.agent.reasoning import VulnerabilityAssessment


def _survey(region: str, days_stale: int, disease: str = "Lassa fever", country: str = "Nigeria"):
    return RegionSurveyRow(
        region=region,
        country=country,
        disease=disease,
        last_survey_date=None,  # not read by run()
        reported_case_rate=0.0,
        data_source="test",
        days_stale=days_stale,
    )


def _trend(region: str, pct_change: float = 20.0) -> AdmissionsTrend:
    return AdmissionsTrend(
        region=region,
        daily_counts=[100, 110, 120],
        first_value=100,
        last_value=120,
        pct_change=pct_change,
    )


def _resources(region: str) -> ResourceLevel:
    return ResourceLevel(
        region=region,
        country="Nigeria",
        funding_level_pct_of_avg=80.0,
        staff_count=15,
        vaccine_stock_units=500,
    )


class FakeDataAccess:
    """Stands in for the real SQLite-backed DataAccess with canned rows."""

    def __init__(self, regions, surveys, trends=None, resources=None):
        self.regions = regions
        self.surveys = surveys
        self.trends = trends or {}
        self.resources = resources or {}

    def list_regions(self) -> list[str]:
        return list(self.regions)

    def get_survey_row(self, region: str):
        return self.surveys.get(region)

    def get_admissions_trend(self, region: str):
        return self.trends.get(region, _trend(region))

    def get_resource_level(self, region: str):
        return self.resources.get(region, _resources(region))


def _assessment(region: str, level: str, confidence: str = "High") -> VulnerabilityAssessment:
    return VulnerabilityAssessment(
        region=region,
        vulnerability_level=level,
        justification=f"Justification for {region}.",
        confidence=confidence,
        key_signals=[f"signal for {region}"],
    )


def _make_datahub(write_back_enabled: bool = True):
    datahub = Mock()
    if write_back_enabled:
        datahub.write_finding.return_value = True
    else:
        datahub.write_finding.side_effect = NotImplementedError("not wired yet")
    return datahub


def test_flags_high_and_moderate_but_not_low_or_fresh(tmp_path, monkeypatch):
    regions = ["Region-A", "Region-B", "Region-C", "Region-D"]
    surveys = {
        "Region-A": _survey("Region-A", 45, disease="Ebola", country="Uganda"),
        "Region-B": _survey("Region-B", 40),
        "Region-C": _survey("Region-C", 10),  # not stale -> never assessed
        "Region-D": _survey("Region-D", 60),
    }
    by_region = {
        "Region-A": _assessment("Region-A", "High"),
        "Region-B": _assessment("Region-B", "Low", confidence="Low"),
        "Region-D": _assessment("Region-D", "Moderate", confidence="Medium"),
    }

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return by_region[region]

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)
    datahub = _make_datahub()
    da = FakeDataAccess(regions, surveys)

    results = run(da, datahub, output_path=str(tmp_path / "report.json"))

    assert [r["region"] for r in results] == ["Region-A", "Region-D"]
    assert results[0]["disease"] == "Ebola"
    assert results[0]["country"] == "Uganda"
    assert results[0]["days_stale"] == 45
    assert datahub.write_finding.call_count == 2


def test_report_sorted_by_level_then_staleness_desc(tmp_path, monkeypatch):
    regions = ["Region-A", "Region-B", "Region-C"]
    surveys = {
        "Region-A": _survey("Region-A", 50),
        "Region-B": _survey("Region-B", 70),
        "Region-C": _survey("Region-C", 90),
    }
    by_region = {
        "Region-A": _assessment("Region-A", "High"),
        "Region-B": _assessment("Region-B", "Moderate"),
        "Region-C": _assessment("Region-C", "High"),
    }

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return by_region[region]

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)

    results = run(
        FakeDataAccess(regions, surveys),
        _make_datahub(),
        output_path=str(tmp_path / "report.json"),
    )

    assert [r["region"] for r in results] == ["Region-C", "Region-A", "Region-B"]
    assert [r["vulnerability_level"] for r in results] == ["High", "High", "Moderate"]


def test_write_back_not_implemented_does_not_block(tmp_path, monkeypatch):
    regions = ["Region-A", "Region-D"]
    surveys = {
        "Region-A": _survey("Region-A", 45),
        "Region-D": _survey("Region-D", 60),
    }
    by_region = {
        "Region-A": _assessment("Region-A", "High"),
        "Region-D": _assessment("Region-D", "Moderate"),
    }

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return by_region[region]

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)
    datahub = _make_datahub(write_back_enabled=False)  # write_finding raises NotImplementedError

    results = run(da := FakeDataAccess(regions, surveys), datahub, output_path=str(tmp_path / "report.json"))

    assert len(results) == 2
    datahub.write_finding.assert_called()


def test_no_stale_regions_produces_empty_report_and_no_writes(tmp_path, monkeypatch):
    regions = ["Region-A", "Region-B"]
    surveys = {
        "Region-A": _survey("Region-A", 5),
        "Region-B": _survey("Region-B", 12),
    }
    datahub = _make_datahub()

    def fake_assess_region(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("should not be called for fresh regions")

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)

    results = run(FakeDataAccess(regions, surveys), datahub, output_path=str(tmp_path / "report.json"))

    assert results == []
    datahub.write_finding.assert_not_called()


def test_writes_report_json_to_output_path(tmp_path, monkeypatch):
    regions = ["Region-A"]
    surveys = {"Region-A": _survey("Region-A", 45, disease="Malaria", country="Kenya")}
    by_region = {"Region-A": _assessment("Region-A", "High")}

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return by_region[region]

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)

    out = tmp_path / "nested" / "report.json"
    run(FakeDataAccess(regions, surveys), _make_datahub(), output_path=str(out))

    payload = json.loads(out.read_text())
    assert payload[0]["region"] == "Region-A"
    assert payload[0]["disease"] == "Malaria"
    assert payload[0]["country"] == "Kenya"


def test_region_without_survey_or_resources_is_skipped(tmp_path, monkeypatch):
    regions = ["Region-A", "Region-B"]
    surveys = {"Region-A": _survey("Region-A", 45)}
    resources = {"Region-A": _resources("Region-A")}  # Region-B has none

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return _assessment(region, "High")

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)

    da = FakeDataAccess(regions, surveys, resources=resources)
    results = run(da, _make_datahub(), output_path=str(tmp_path / "report.json"))

    assert [r["region"] for r in results] == ["Region-A"]


def test_freshness_monitoring_runs_once_with_touched_datasets(tmp_path, monkeypatch):
    regions = ["Region-A"]
    surveys = {"Region-A": _survey("Region-A", 45)}
    resources = {"Region-A": _resources("Region-A")}

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return _assessment(region, "High")

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)
    monitor = Mock(return_value=None)
    monkeypatch.setattr("app.agent.orchestrator.monitor_datasets_freshness", monitor)

    da = FakeDataAccess(regions, surveys, resources=resources)
    run(da, _make_datahub(), output_path=str(tmp_path / "report.json"))

    # Called exactly once for the whole run (not per region), after the loop.
    assert monitor.call_count == 1
    _, kwargs = monitor.call_args
    assert kwargs["data_access"] is da
    assert set(kwargs["datasets"]) == {
        "regional_survey_data",
        "hospital_admissions",
        "resource_allocation",
    }


def test_freshness_monitoring_can_be_disabled(tmp_path, monkeypatch):
    regions = ["Region-A"]
    surveys = {"Region-A": _survey("Region-A", 45)}

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return _assessment(region, "High")

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)
    monitor = Mock()
    monkeypatch.setattr("app.agent.orchestrator.monitor_datasets_freshness", monitor)

    run(
        FakeDataAccess(regions, surveys),
        _make_datahub(),
        output_path=str(tmp_path / "report.json"),
        freshness_monitoring_enabled=False,
    )

    monitor.assert_not_called()


def test_freshness_monitoring_failure_does_not_block_run(tmp_path, monkeypatch):
    regions = ["Region-A"]
    surveys = {"Region-A": _survey("Region-A", 45)}

    def fake_assess_region(region, days_stale, admissions_trend, resources, client=None):
        return _assessment(region, "High")

    monkeypatch.setattr("app.agent.orchestrator.assess_region", fake_assess_region)

    def boom(*args, **kwargs):
        raise RuntimeError("GMS unreachable")

    monkeypatch.setattr("app.agent.orchestrator.monitor_datasets_freshness", boom)

    results = run(
        FakeDataAccess(regions, surveys),
        _make_datahub(),
        output_path=str(tmp_path / "report.json"),
    )

    assert [r["region"] for r in results] == ["Region-A"]

"""Unit tests for freshness_monitor.py evaluation logic (no live GMS)."""

from __future__ import annotations

import pytest

from app.agent.freshness_monitor import (
    DATASET_FRESHNESS_CONFIG,
    FreshnessEvaluation,
    evaluate_dataset_freshness,
)


class FakeSurveyRow:
    def __init__(self, days_stale: int):
        self.days_stale = days_stale


class FakeDataAccess:
    def __init__(self, stale_by_region: dict[str, int]):
        self._stale = stale_by_region

    def list_regions(self) -> list[str]:
        return list(self._stale)

    def get_survey_row(self, region: str):
        days = self._stale.get(region)
        if days is None:
            return None
        return FakeSurveyRow(days)


def test_evaluate_passes_when_newest_row_is_within_window():
    ev = evaluate_dataset_freshness(
        FakeDataAccess({"A": 2, "B": 5, "C": 45}),
        "regional_survey_data",
        max_age_days=30,
    )

    assert isinstance(ev, FreshnessEvaluation)
    assert ev.passed is True
    assert ev.newest_days_stale == 2
    assert ev.oldest_days_stale == 45
    assert ev.regions_evaluated == 3
    assert ev.threshold_days == 30
    assert "fresh" in ev.message.lower()


def test_evaluate_fails_when_newest_row_is_older_than_window():
    ev = evaluate_dataset_freshness(
        FakeDataAccess({"A": 31, "B": 60}),
        "regional_survey_data",
        max_age_days=30,
    )

    assert ev.passed is False
    assert ev.newest_days_stale == 31
    assert "stale" in ev.message.lower()


def test_evaluate_skips_regions_without_survey_row():
    ev = evaluate_dataset_freshness(
        FakeDataAccess({"A": 5, "B": None}),
        "regional_survey_data",
        max_age_days=30,
    )

    assert ev.regions_evaluated == 1
    assert ev.passed is True


def test_evaluate_with_no_rows_reports_failure():
    ev = evaluate_dataset_freshness(
        FakeDataAccess({"A": None}),
        "regional_survey_data",
        max_age_days=30,
    )

    assert ev.passed is False
    assert ev.regions_evaluated == 0
    assert ev.newest_days_stale is None


def test_evaluate_unknown_dataset_raises():
    with pytest.raises(ValueError):
        evaluate_dataset_freshness(FakeDataAccess({}), "hospital_admissions")


def test_survey_dataset_is_configured():
    assert "regional_survey_data" in DATASET_FRESHNESS_CONFIG
    assert DATASET_FRESHNESS_CONFIG["regional_survey_data"]["last_modified_field"]

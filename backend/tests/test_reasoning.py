"""Unit tests for the Gemini reasoning helpers (prompt building, parsing)."""

from __future__ import annotations

from app.agent.reasoning import (
    VulnerabilityAssessment,
    assess_region,
    build_user_prompt,
)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text
        self.last_kwargs: dict | None = None

    def generate_content(self, **kwargs):  # noqa: ANN003
        self.last_kwargs = kwargs
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.models = _FakeModels(text)


def test_build_user_prompt_contains_all_signals():
    prompt = build_user_prompt(
        region="Bauchi, Nigeria",
        days_stale=21,
        admissions_trend={"first_value": 100, "last_value": 182, "pct_change": 82.0},
        resources={"funding_level_pct_of_avg": 37.5, "staff_count": 12, "vaccine_stock_units": 300},
    )
    assert "Bauchi, Nigeria" in prompt
    assert "21" in prompt
    assert "82.0" in prompt
    assert "37.5" in prompt


def test_assess_region_parses_gemini_json_response():
    client = _FakeClient(
        '{"vulnerability_level": "High", "justification": "Signals align.", '
        '"confidence": "High", "key_signals": ["admissions +82%", "funding low"]}'
    )
    assessment = assess_region(
        region="Bauchi, Nigeria",
        days_stale=21,
        admissions_trend={"first_value": 100, "last_value": 182, "pct_change": 82.0},
        resources={"funding_level_pct_of_avg": 37.5},
        client=client,
    )
    assert isinstance(assessment, VulnerabilityAssessment)
    assert assessment.region == "Bauchi, Nigeria"
    assert assessment.vulnerability_level == "High"
    assert assessment.confidence == "High"
    assert assessment.key_signals == ["admissions +82%", "funding low"]

    config = client.models.last_kwargs["config"]
    assert config["response_mime_type"] == "application/json"
    assert "system_instruction" in config


def test_assessment_to_dict_matches_report_fields():
    assessment = VulnerabilityAssessment(
        region="Region-X",
        vulnerability_level="Moderate",
        justification="Watch closely.",
        confidence="Medium",
        key_signals=["stale survey"],
    )
    data = assessment.to_dict()
    assert data == {
        "region": "Region-X",
        "vulnerability_level": "Moderate",
        "justification": "Watch closely.",
        "confidence": "Medium",
        "key_signals": ["stale survey"],
    }


def test_build_user_prompt_hydrates_dataclass_style_inputs():
    prompt = build_user_prompt(
        region="Region-Y",
        days_stale=40,
        admissions_trend={"first_value": 50, "last_value": 65, "pct_change": 30.0},
        resources={"funding_level_pct_of_avg": 70.0, "staff_count": 20, "vaccine_stock_units": 100},
    )
    assert "Region-Y" in prompt
    assert "40" in prompt

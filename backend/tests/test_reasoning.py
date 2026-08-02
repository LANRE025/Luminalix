"""Unit tests for the Gemini reasoning helpers (JSON parsing, trend math)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agent.reasoning import (
    LLM_RESPONSE_SCHEMA,
    RegionReasoning,
    _parse_json,
    pct_change,
)


def test_parse_json_plain_object():
    assert _parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_with_markdown_fences():
    text = '```json\n{"region": "Region-X", "vulnerability_level": "High"}\n```'
    assert _parse_json(text)["region"] == "Region-X"


def test_parse_json_with_fence_and_language_prefix():
    text = '```json\n{"a": 2}\n```'
    assert _parse_json(text) == {"a": 2}


def test_parse_json_extracts_object_from_prose():
    text = 'Here is the result: {"level": "Low"} thanks!'
    assert _parse_json(text) == {"level": "Low"}


def test_parse_json_raises_on_no_object():
    with pytest.raises(json.JSONDecodeError):
        _parse_json("not json at all")


def test_parse_json_raises_on_invalid_inside_fences():
    with pytest.raises(json.JSONDecodeError):
        _parse_json('```json\n{"broken": }\n```')


def test_region_reasoning_validates_and_coerces_enums():
    payload = {
        "region": "Region-X",
        "vulnerability_level": "High",
        "justification": "Signals align.",
        "confidence": "Medium",
        "key_signals": ["survey stale 40 days"],
    }
    reasoning = RegionReasoning.model_validate(payload)
    assert reasoning.vulnerability_level.value == "High"
    assert reasoning.confidence.value == "Medium"
    assert reasoning.key_signals == ["survey stale 40 days"]


def test_region_reasoning_rejects_bad_level():
    payload = {
        "region": "Region-X",
        "vulnerability_level": "Critical",
        "justification": "nope",
        "confidence": "High",
        "key_signals": [],
    }
    with pytest.raises(ValidationError):
        RegionReasoning.model_validate(payload)


def test_pct_change():
    assert pct_change([100.0, 110.0, 138.0]) == 38.0
    assert pct_change([]) is None
    assert pct_change([0.0, 5.0]) is None
    assert pct_change([50.0, 50.0]) == 0.0


def test_response_schema_matches_public_schema_fields():
    assert LLM_RESPONSE_SCHEMA["type"] == "object"
    assert set(LLM_RESPONSE_SCHEMA["required"]) == {
        "region",
        "vulnerability_level",
        "justification",
        "confidence",
        "key_signals",
    }
    assert LLM_RESPONSE_SCHEMA["properties"]["vulnerability_level"]["enum"] == [
        "Low",
        "Moderate",
        "High",
    ]

"""Unit tests for the DataHub client's pure helpers (no live MCP server).

Covers the finding-append/cap logic and entity extraction from get_entities
payloads. Network-facing paths are exercised by the live smoke test instead.
"""

from __future__ import annotations

from app.agent.datahub_client import (
    FINDING_MARKER,
    MAX_FINDINGS,
    DataHubClient,
    DatasetNotFoundError,
    DataHubMCPError,
)


def _note(i: int) -> str:
    return f"{FINDING_MARKER}2026-01-{i:02d} 00:00 UTC]**\nFinding {i}."


def test_append_finding_to_empty_description():
    combined = DataHubClient._append_finding("", _note(1))
    assert combined == _note(1)


def test_append_finding_keeps_preamble():
    preamble = "Regional survey data snapshot for the Luminalix pipeline."
    combined = DataHubClient._append_finding(f"{preamble}\n\n{_note(1)}", _note(2))
    assert combined.startswith(preamble)
    assert "Finding 1." in combined
    assert "Finding 2." in combined
    assert combined.count(FINDING_MARKER) == 2


def test_append_finding_caps_at_max_findings():
    current = "\n\n".join(_note(i) for i in range(1, MAX_FINDINGS + 2))
    combined = DataHubClient._append_finding(current, _note(99))
    assert combined.count(FINDING_MARKER) == MAX_FINDINGS
    assert "Finding 1." not in combined  # oldest dropped
    assert "Finding 99." in combined


def test_append_finding_plain_text_without_marker_has_no_findings():
    combined = DataHubClient._append_finding("Just a description.", _note(1))
    assert combined == "Just a description.\n\n" + _note(1)


def test_extract_entity_returns_matching_entity():
    urn = "urn:li:dataset:(urn:li:dataPlatform:sqlite,main.x,PROD)"
    payload = [
        {"error": "Entity urn:... not found", "urn": "urn:li:dataset:(a)"},
        {"urn": urn, "name": "x", "properties": {"description": "hi"}},
    ]
    assert DataHubClient._extract_entity(payload, urn)["urn"] == urn


def test_extract_entity_raises_dataset_not_found():
    urn = "urn:li:dataset:(urn:li:dataPlatform:sqlite,main.x,PROD)"
    payload = [{"error": "Entity not found", "urn": urn}]
    try:
        DataHubClient._extract_entity(payload, urn)
    except DatasetNotFoundError:
        pass
    else:
        raise AssertionError("expected DatasetNotFoundError")


def test_extract_entity_unexpected_shape_raises_mcp_error():
    urn = "urn:li:dataset:(urn:li:dataPlatform:sqlite,main.x,PROD)"
    try:
        DataHubClient._extract_entity([], urn)
    except DataHubMCPError:
        pass
    else:
        raise AssertionError("expected DataHubMCPError")

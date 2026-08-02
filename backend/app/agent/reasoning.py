"""Gemini-backed reasoning step.

This module is implemented for real — it calls the Gemini API via the
``google-genai`` SDK and returns structured output. It includes defensive
handling for malformed / non-JSON responses from the model (retry once, then
raise ``ReasoningError``).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.models.schemas import Confidence, VulnerabilityLevel

logger = logging.getLogger(__name__)


class ReasoningError(RuntimeError):
    """Raised when the Gemini step fails (API error or unparseable output)."""


class RegionReasoning(BaseModel):
    """Structured output produced by the LLM for a single region.

    ``days_stale`` and ``flagged_at`` are filled in by the orchestrator, not the
    model.
    """

    region: str
    vulnerability_level: VulnerabilityLevel
    justification: str
    confidence: Confidence
    key_signals: list[str] = Field(default_factory=list)


# A plain dict schema (rather than the Pydantic model) so it works across the
# widest range of google-genai SDK versions.
LLM_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "region": {"type": "string"},
        "vulnerability_level": {"type": "string", "enum": ["Low", "Moderate", "High"]},
        "justification": {"type": "string"},
        "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "key_signals": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["region", "vulnerability_level", "justification", "confidence", "key_signals"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are an epidemiological surveillance analyst. For each region you are given three signals:
1. How stale the official survey data is (days since the last survey).
2. A recent hospital admissions trend (daily counts over the lookback window).
3. The region's current resource allocation (funding, staff, vaccine stock) relative to the regional average.

Classify how vulnerable the region is to an undetected or escalating outbreak:
- "High": survey data is stale AND admissions are clearly trending up AND/OR resources are well below the regional average.
- "Moderate": some but not all risk signals point to an emerging problem.
- "Low": no meaningful divergence from normal.

Respond with ONLY a JSON object matching this schema:
{
  "region": string,
  "vulnerability_level": "Low" | "Moderate" | "High",
  "justification": string,   // 1-3 plain-language sentences a non-technical analyst can act on
  "confidence": "Low" | "Medium" | "High",
  "key_signals": string[]    // e.g. "survey stale 42 days", "admissions +38% over 14 days"
}
"""


class GeminiReasoner:
    """Wraps the Gemini API call that turns raw signals into an assessment."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = (
            genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
        )

    def evaluate_region(
        self,
        *,
        region: str,
        country: str,
        days_stale: int,
        admissions_trend: list[float],
        resources: dict[str, float],
        resource_average: dict[str, float],
    ) -> RegionReasoning:
        """Ask the model to classify one region and return structured output."""
        if self._client is None:
            raise ReasoningError(
                "GEMINI_API_KEY is not set. Add it to backend/.env (see .env.example)."
            )

        context = {
            "region": region,
            "country": country,
            "days_since_last_survey": days_stale,
            "hospital_admissions_daily": admissions_trend,
            "admissions_change_pct": pct_change(admissions_trend),
            "resource_allocation": resources,
            "regional_average_allocation": resource_average,
        }
        contents = (
            "Evaluate outbreak vulnerability for this region based on the signals below.\n\n"
            f"{json.dumps(context, indent=2, default=str)}"
        )

        for attempt in range(2):
            try:
                response = self._client.models.generate_content(
                    model=self._settings.gemini_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=LLM_RESPONSE_SCHEMA,
                        temperature=0.2,
                    ),
                )
                data = _parse_json(response.text or "")
                reasoning = RegionReasoning.model_validate(data)
                if reasoning.region != region:
                    logger.warning(
                        "Model echoed region %r; expected %r — overriding.",
                        reasoning.region,
                        region,
                    )
                    reasoning.region = region
                return reasoning
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Gemini attempt %d produced malformed output: %s", attempt + 1, exc
                )
                if attempt == 1:
                    raise ReasoningError(
                        f"Gemini returned malformed output for region {region!r}: {exc}"
                    ) from exc
                contents += (
                    "\n\nYour previous response was not valid JSON. "
                    "Reply with ONLY the JSON object matching the schema."
                )

        raise ReasoningError("Gemini reasoning failed.")  # pragma: no cover


def pct_change(series: list[float]) -> float | None:
    """Percent change from the start to the end of a series.

    Returns ``None`` when the series is empty or its baseline is zero.
    """
    if not series:
        return None
    baseline = series[0]
    if baseline == 0:
        return None
    return round((series[-1] - baseline) / baseline * 100.0, 1)


def _parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object out of the model's text output, tolerating fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise json.JSONDecodeError("No JSON object found in model output", text, 0)

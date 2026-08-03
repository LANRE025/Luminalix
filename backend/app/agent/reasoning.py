"""
reasoning.py

The LLM reasoning step — using Gemini via Vertex AI (not Claude, per project
decision). Given a region's real survey staleness, admissions trend, and
resource levels (all from data_access.py), produce a structured vulnerability
assessment.
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import Any

from google import genai
from google.genai import errors
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import get_settings

MODEL = os.getenv("AGENT_MODEL", "gemini-3.5-flash")  # fallback only; prefer settings.gemini_model


def _is_retryable(exc: BaseException) -> bool:
    # Retry only transient quota / availability errors; let everything else propagate.
    return isinstance(exc, errors.APIError) and exc.code in (429, 503)


def _client() -> genai.Client:
    # Vertex AI authenticates with Application Default Credentials (ADC), not an
    # API key. Set up ADC locally with `gcloud auth application-default login`;
    # an explicit env var override still wins for project/location.
    settings = get_settings()
    if not settings.vertex_project:
        raise RuntimeError(
            "Vertex AI project missing: set VERTEX_PROJECT in backend/.env "
            "(or export it in the environment) before running the agent."
        )
    return genai.Client(
        vertexai=True,
        project=settings.vertex_project,
        location=settings.vertex_location,
    )


def _model() -> str:
    return get_settings().gemini_model or MODEL


@dataclass
class VulnerabilityAssessment:
    region: str
    vulnerability_level: str  # "Low" | "Moderate" | "High"
    justification: str
    confidence: str  # "Low" | "Medium" | "High"
    key_signals: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SYSTEM_PROMPT = """You are an epidemiological risk assessment assistant. \
You will be given, for a single region: how many days it has been since \
the official survey data was last updated, a recent hospital admissions \
trend, and the region's current resource allocation level relative to \
its historical average.

Classify the region's outbreak vulnerability as Low, Moderate, or High, \
and explain your reasoning in 1-3 plain-language sentences a non-technical \
health data analyst can act on immediately.

Consider:
- A stale survey alone is not necessarily high risk — it only matters if \
  paired with a concerning admissions trend.
- A concerning admissions trend combined with low resource allocation is \
  more urgent than the same trend with adequate resources.
- Be conservative: only assign "High" when multiple signals align.

Respond ONLY with a JSON object matching this schema, no other text, no \
markdown fencing:
{
  "vulnerability_level": "Low" | "Moderate" | "High",
  "justification": "string, 1-3 sentences",
  "confidence": "Low" | "Medium" | "High",
  "key_signals": ["string", ...]
}
"""


def build_user_prompt(
    region: str, days_stale: int, admissions_trend: dict[str, Any], resources: dict[str, Any]
) -> str:
    return (
        f"Region: {region}\n"
        f"Days since last survey update: {days_stale}\n"
        f"Recent hospital admissions trend: {json.dumps(admissions_trend)}\n"
        f"Current resource allocation: {json.dumps(resources)}\n"
    )


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _generate_content(client: genai.Client, model: str, user_prompt: str) -> Any:
    return client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
        },
    )


def assess_region(
    region: str,
    days_stale: int,
    admissions_trend: dict[str, Any],
    resources: dict[str, Any],
    client: "genai.Client | None" = None,
) -> VulnerabilityAssessment:
    client = client or _client()

    user_prompt = build_user_prompt(region, days_stale, admissions_trend, resources)

    response = _generate_content(client, _model(), user_prompt)

    raw_text = response.text.strip()
    parsed = json.loads(raw_text)

    return VulnerabilityAssessment(
        region=region,
        vulnerability_level=parsed["vulnerability_level"],
        justification=parsed["justification"],
        confidence=parsed["confidence"],
        key_signals=parsed["key_signals"],
    )

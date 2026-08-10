"""
freshness_monitor.py

Publishes real DataHub Assertions -- freshness monitoring for the datasets the
agent touches -- and the per-run evaluation results.

Why this exists: self-hosted OSS DataHub does NOT evaluate assertions on a
schedule the way DataHub Cloud / Acryl Observe does. OSS only supports
*defining* assertion entities and *publishing* results to them via the API; the
actual evaluation must be triggered by our own code on our own schedule. This
module does exactly that, synchronously at the end of each agent run:

  1. REGISTER a FreshnessAssertion entity for a dataset if one does not already
     exist (deterministic assertion urn + graph.exists check, so it is
     idempotent). The definition is emitted as an AssertionInfo aspect via the
     REST emitter (graph.emit_mcp) -- the supported create path in the
     installed acryl-datahub 1.6.0.17 SDK. There is no GraphQL upsert wrapper
     for native freshness assertions in this SDK.

  2. EVALUATE freshness by reusing the staleness data already computed in
     app/agent/data_access.py (per-region days_stale from get_survey_row) --
     this module does NOT reimplement staleness logic.

  3. PUBLISH the run result (PASS/FAIL + timestamp + human-readable message) to
     the assertion via the GraphQL reportAssertionResult mutation
     (DataHubGraph.report_assertion_result), which is what the DataHub UI
     Quality tab / assertion run history reads back.

Everything here is defensive: a failure in any step is logged with
logger.exception (the same way write_finding failures are handled in
datahub_client.py) and never blocks the rest of the agent run.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from datahub.emitter.mce_builder import datahub_guid, make_assertion_source, make_assertion_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig
from datahub.metadata.com.linkedin.pegasus2avro.assertion import (
    AssertionInfo,
    AssertionType,
    FixedIntervalSchedule,
    FreshnessAssertionInfo,
    FreshnessAssertionSchedule,
    FreshnessAssertionScheduleType,
    FreshnessAssertionType,
)
from datahub.metadata.com.linkedin.pegasus2avro.timeseries import CalendarInterval

logger = logging.getLogger(__name__)

# How fresh "fresh" is. The assertion definition and the evaluation both use
# this as the dataset's maximum allowed age in days.
DEFAULT_FRESHNESS_INTERVAL_DAYS = 30

# Datasets the freshness monitor knows how to monitor, keyed by the dataset
# name as used by the agent, with the column that carries the last-updated
# signal. Evaluation reuses DataAccess' per-region days_stale for the survey
# dataset; other datasets would need their own staleness source before being
# added here.
DATASET_FRESHNESS_CONFIG: dict[str, dict[str, str]] = {
    "regional_survey_data": {
        "last_modified_field": "last_survey_date",
        "description": (
            "regional_survey_data is considered fresh when its newest survey "
            "row is updated within the freshness interval."
        ),
    },
}


@dataclass
class FreshnessEvaluation:
    """Outcome of a single dataset freshness evaluation."""

    dataset: str
    passed: bool
    newest_days_stale: int | None  # age of the newest survey row, in days
    oldest_days_stale: int | None  # age of the oldest survey row, in days
    regions_evaluated: int
    threshold_days: int
    message: str
    evaluated_at: datetime


def _resolve_dataset_urn(graph: DataHubGraph, dataset: str) -> str:
    """Resolve a dataset name (e.g. "regional_survey_data") to its DataHub URN
    by searching datasets and matching on the exact entity name -- the same
    strategy the MCP-based DataHubClient uses in datahub_client.py."""
    query = """
    query SearchDatasets($query: String!, $count: Int!) {
        searchAcrossEntities(input: {
            query: $query, types: [DATASET], start: 0, count: $count,
            searchFlags: { skipHighlighting: true }
        }) {
            searchResults {
                entity {
                    ... on Dataset { urn name properties { name } }
                }
            }
        }
    }
    """
    result = graph.execute_graphql(query, variables={"query": dataset, "count": 20})
    for item in (result.get("searchAcrossEntities") or {}).get("searchResults") or []:
        entity = item.get("entity") or {}
        name = entity.get("name") or (entity.get("properties") or {}).get("name")
        if name and name.lower() == dataset.lower():
            return entity["urn"]
    raise ValueError(
        f"Dataset '{dataset}' was not found in DataHub (GMS {graph.config.server})."
    )


def register_freshness_assertion(
    graph: DataHubGraph,
    dataset_urn: str,
    *,
    id_raw: str,
    description: str,
    last_modified_field: str,
    interval_days: int = DEFAULT_FRESHNESS_INTERVAL_DAYS,
) -> str:
    """Register a FreshnessAssertion entity for ``dataset_urn`` if one does not
    already exist, and return its assertion urn.

    The assertion urn is deterministic: ``urn:li:assertion:<guid(entity,
    "freshness", id_raw)>`` -- the same scheme the SDK's
    ``FixedIntervalFreshnessAssertion.get_id()`` uses. Idempotency comes from
    checking ``graph.exists`` before creating.

    The definition is emitted as an ``AssertionInfo`` aspect (AssertionType
    FRESHNESS, DATASET_CHANGE, fixed-interval schedule). The schedule is built
    directly from the metadata model with ``CalendarInterval.DAY`` because the
    SDK's ``FixedIntervalFreshnessAssertion`` serialises the interval as
    ``unit=SECOND, multiple=interval.seconds`` (0 for any interval >= 1 day).
    """
    assertion_urn = make_assertion_urn(
        datahub_guid({"entity": dataset_urn, "type": "freshness", "id_raw": id_raw})
    )

    if graph.exists(assertion_urn):
        print(
            f"[freshness] Assertion already exists for {dataset_urn}: {assertion_urn}"
        )
        return assertion_urn

    info = AssertionInfo(
        type=AssertionType.FRESHNESS,
        description=description,
        freshnessAssertion=FreshnessAssertionInfo(
            type=FreshnessAssertionType.DATASET_CHANGE,
            entity=dataset_urn,
            schedule=FreshnessAssertionSchedule(
                type=FreshnessAssertionScheduleType.FIXED_INTERVAL,
                fixedInterval=FixedIntervalSchedule(
                    unit=CalendarInterval.DAY,
                    multiple=interval_days,
                ),
            ),
        ),
        source=make_assertion_source(),
    )

    graph.emit_mcp(MetadataChangeProposalWrapper(entityUrn=assertion_urn, aspect=info))
    print(f"[freshness] Registered FreshnessAssertion {assertion_urn}")
    return assertion_urn


def evaluate_dataset_freshness(
    data_access: Any,
    dataset: str,
    *,
    max_age_days: int = DEFAULT_FRESHNESS_INTERVAL_DAYS,
) -> FreshnessEvaluation:
    """Evaluate whether ``dataset`` is fresh, reusing the per-region
    ``days_stale`` values DataAccess already computes for survey rows.

    The dataset's last-update signal is its newest survey row: the minimum
    ``days_stale`` across regions. If the newest row is older than
    ``max_age_days`` the dataset fails the assertion.
    """
    if dataset not in DATASET_FRESHNESS_CONFIG:
        raise ValueError(f"No freshness evaluation is defined for dataset '{dataset}'.")

    regions = data_access.list_regions()
    per_region_stale: list[int] = []
    for region in regions:
        row = data_access.get_survey_row(region)
        if row is not None and row.days_stale is not None:
            per_region_stale.append(row.days_stale)

    evaluated_at = datetime.now(timezone.utc)
    if not per_region_stale:
        return FreshnessEvaluation(
            dataset=dataset,
            passed=False,
            newest_days_stale=None,
            oldest_days_stale=None,
            regions_evaluated=0,
            threshold_days=max_age_days,
            message=(
                f"Dataset '{dataset}' has no survey rows to evaluate -- "
                "cannot confirm freshness."
            ),
            evaluated_at=evaluated_at,
        )

    newest = min(per_region_stale)
    oldest = max(per_region_stale)
    passed = newest <= max_age_days
    message = (
        f"Dataset '{dataset}' is {'fresh' if passed else 'STALE'}: newest "
        f"survey row is {newest} day(s) old, oldest is {oldest} day(s) old, "
        f"across {len(per_region_stale)} region(s). Max allowed age: "
        f"{max_age_days} day(s)."
    )
    return FreshnessEvaluation(
        dataset=dataset,
        passed=passed,
        newest_days_stale=newest,
        oldest_days_stale=oldest,
        regions_evaluated=len(per_region_stale),
        threshold_days=max_age_days,
        message=message,
        evaluated_at=evaluated_at,
    )


def publish_freshness_result(
    graph: DataHubGraph,
    assertion_urn: str,
    evaluation: FreshnessEvaluation,
) -> bool:
    """Publish the evaluation result (PASS/FAIL + message + timestamp) to the
    assertion via GraphQL ``reportAssertionResult``.

    Failures are logged with ``logger.exception`` and swallowed (return False)
    so a publish problem can never block the rest of the agent run -- the same
    contract write_finding() has in datahub_client.py.
    """
    result_type = "SUCCESS" if evaluation.passed else "FAILURE"
    try:
        published = graph.report_assertion_result(
            urn=assertion_urn,
            timestamp_millis=int(evaluation.evaluated_at.timestamp() * 1000),
            type=result_type,  # type: ignore[arg-type]  # Literal str, typed in SDK
            properties=[
                {"key": "message", "value": evaluation.message},
                {"key": "newest_days_stale",
                 "value": str(evaluation.newest_days_stale)},
                {"key": "regions_evaluated",
                 "value": str(evaluation.regions_evaluated)},
            ],
        )
    except Exception as exc:  # noqa: BLE001 - never let publish failures escape
        logger.exception(
            "DataHub freshness publish failed for assertion %s (%s): %s",
            assertion_urn,
            type(exc).__name__,
            exc,
        )
        return False

    print(
        f"[freshness] Published {result_type} for {assertion_urn} at "
        f"{evaluation.evaluated_at.isoformat()}: {evaluation.message}"
    )
    return bool(published)


def monitor_datasets_freshness(
    data_access: Any,
    datahub_client: Any,
    datasets: list[str] | set[str],
    *,
    interval_days: int = DEFAULT_FRESHNESS_INTERVAL_DAYS,
) -> None:
    """Register + evaluate + publish freshness for every dataset the agent
    touched this run. Runs once per run (not per region), after the agent loop.

    Never raises: every failure is logged via ``logger.exception`` so freshness
    monitoring cannot block or slow down the rest of the agent run.
    """
    if not datasets:
        return

    graph = _build_graph(datahub_client)
    if graph is None:
        return

    for dataset in sorted(datasets):
        try:
            if dataset not in DATASET_FRESHNESS_CONFIG:
                print(
                    f"[freshness] No staleness signal configured for "
                    f"dataset '{dataset}' -- skipping"
                )
                continue

            dataset_urn = _resolve_dataset_urn(graph, dataset)
            config = DATASET_FRESHNESS_CONFIG[dataset]
            assertion_urn = register_freshness_assertion(
                graph,
                dataset_urn,
                id_raw=f"{dataset}_freshness",
                description=config["description"],
                last_modified_field=config["last_modified_field"],
                interval_days=interval_days,
            )
            evaluation = evaluate_dataset_freshness(
                data_access, dataset, max_age_days=interval_days
            )
            publish_freshness_result(graph, assertion_urn, evaluation)
        except Exception as exc:  # noqa: BLE001 - one dataset's failure is not fatal
            logger.exception(
                "Freshness monitoring failed for dataset %s (%s): %s",
                dataset,
                type(exc).__name__,
                exc,
            )


def _build_graph(datahub_client: Any) -> DataHubGraph | None:
    """Build a DataHubGraph from the MCP client's own GMS endpoint/token (the
    same ones the MCP subprocess was launched with). Returns None -- after
    logging -- when the client exposes no usable credentials, so a stub/mock
    client (e.g. in unit tests) never triggers a real GMS connection."""
    gms_url = getattr(datahub_client, "gms_url", None)
    token = getattr(datahub_client, "token", None)
    if not isinstance(gms_url, str) or not isinstance(token, str):
        logger.warning(
            "datahub_client has no GMS credentials configured; "
            "skipping freshness monitoring"
        )
        return None
    try:
        return DataHubGraph(DatahubClientConfig(server=gms_url, token=token))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Could not build DataHub graph client for freshness monitoring "
            "(%s): %s",
            type(exc).__name__,
            exc,
        )
        return None

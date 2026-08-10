"""
test_freshness_assertion.py

Standalone smoke test for the DataHub freshness assertion pipeline used by
app/agent/freshness_monitor.py against the LOCAL self-hosted GMS.

What it does, against the live GMS (http://localhost:8080 by default):
  1. REGISTER a FreshnessAssertion for regional_survey_data (idempotent --
     re-running this script reuses the existing assertion).
  2. PUBLISH one PASS result (timestamp = now) and one FAIL result
     (timestamp = now - 1 day) via the GraphQL reportAssertionResult mutation.
  3. READ BACK the assertion + its run history through the GraphQL API and
     print it, so we confirm the results are actually queryable -- not just
     that the publish call returned 200/True.

Run from the repo root with the datahub venv:
    datahub-venv\\Scripts\\python.exe scripts\\test_freshness_assertion.py

Requires the local DataHub quickstart to be up (docker compose) and the
datasets ingested (regional_survey_data on platform sqlite).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

DATASET = "regional_survey_data"
ID_RAW = "regional_survey_data_freshness"
INTERVAL_DAYS = 30


def load_env(path: Path) -> dict[str, str]:
    """Minimal .env reader for the two DataHub settings this script needs."""
    env: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return env


def main() -> int:
    sys.path.insert(0, str(BACKEND_DIR))

    env = load_env(BACKEND_DIR / ".env")
    gms_url = env.get("DATAHUB_GMS_URL", "http://localhost:8080")
    token = env.get("DATAHUB_TOKEN", "")

    print(f"[1] Connecting to GMS {gms_url}")
    from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

    from app.agent.freshness_monitor import (
        DATASET_FRESHNESS_CONFIG,
        _resolve_dataset_urn,
        register_freshness_assertion,
    )

    graph = DataHubGraph(DatahubClientConfig(server=gms_url, token=token))

    print(f"[2] Resolving dataset '{DATASET}' -> URN")
    dataset_urn = _resolve_dataset_urn(graph, DATASET)
    print(f"    {dataset_urn}")

    print(f"[3] Registering FreshnessAssertion (idempotent) for {DATASET}")
    config = DATASET_FRESHNESS_CONFIG[DATASET]
    assertion_urn = register_freshness_assertion(
        graph,
        dataset_urn,
        id_raw=ID_RAW,
        description=config["description"],
        last_modified_field=config["last_modified_field"],
        interval_days=INTERVAL_DAYS,
    )
    print(f"    assertion urn: {assertion_urn}")
    print(f"    exists:        {graph.exists(assertion_urn)}")

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    yesterday_ms = now_ms - int(timedelta(days=1).total_seconds() * 1000)

    print("[4] Publishing PASS result (timestamp = now)")
    ok_pass = graph.report_assertion_result(
        urn=assertion_urn,
        timestamp_millis=now_ms,
        type="SUCCESS",
        properties=[
            {"key": "message", "value": "Manual PASS for test_freshness_assertion.py"},
            {"key": "newest_days_stale", "value": "3"},
            {"key": "regions_evaluated", "value": "30"},
        ],
    )
    print(f"    reportAssertionResult returned: {ok_pass}")

    print("[5] Publishing FAIL result (timestamp = now - 1 day)")
    ok_fail = graph.report_assertion_result(
        urn=assertion_urn,
        timestamp_millis=yesterday_ms,
        type="FAILURE",
        properties=[
            {"key": "message", "value": "Manual FAIL for test_freshness_assertion.py"},
            {"key": "newest_days_stale", "value": "45"},
            {"key": "regions_evaluated", "value": "30"},
        ],
    )
    print(f"    reportAssertionResult returned: {ok_fail}")

    if not ok_pass or not ok_fail:
        print("ERROR: one or both reportAssertionResult calls did not return True")
        return 1

    print("[6] Reading back assertion + run history via GraphQL")
    readback = None
    for attempt in range(6):
        readback = graph.execute_graphql(
            """
            query GetAssertion($urn: String!) {
                assertion(urn: $urn) {
                    urn
                    info {
                        type
                        description
                        freshnessAssertion {
                            entityUrn
                            type
                            schedule { type fixedInterval { unit multiple } }
                        }
                    }
                    runEvents(status: COMPLETE, limit: 5) {
                        total
                        failed
                        succeeded
                        runEvents {
                            timestampMillis
                            status
                            result {
                                type
                                nativeResults { key value }
                            }
                        }
                    }
                }
            }
            """,
            variables={"urn": assertion_urn},
        )
        total = readback["assertion"]["runEvents"]["total"]
        print(f"    poll {attempt}: run events visible = {total}")
        if total >= 2:
            break
        time.sleep(5)  # allow the run-event timeseries index to settle
    print(json.dumps(readback, indent=2, default=str))

    assertion = readback["assertion"]
    run_events = assertion["runEvents"]["runEvents"]
    print("[7] Summary")
    print(f"    assertion: {assertion['urn']}")
    print(f"    type: {assertion['info']['type']} / "
          f"{assertion['info']['freshnessAssertion']['type']}")
    print(f"    attached to: {assertion['info']['freshnessAssertion']['entityUrn']}")
    print(f"    schedule: {assertion['info']['freshnessAssertion']['schedule']}")
    print(f"    run events stored: {assertion['runEvents']['total']} "
          f"(failed={assertion['runEvents']['failed']}, "
          f"succeeded={assertion['runEvents']['succeeded']})")
    for event in run_events:
        when = datetime.fromtimestamp(
            event["timestampMillis"] / 1000, tz=timezone.utc
        ).isoformat()
        print(f"      {when} -> {event['result']['type']}")

    types = [e["result"]["type"] for e in run_events]
    if "SUCCESS" in types and "FAILURE" in types:
        print("[7] VERIFIED: both PASS and FAIL results are queryable back from GMS")
        return 0
    print("ERROR: expected both SUCCESS and FAILURE in the run history")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

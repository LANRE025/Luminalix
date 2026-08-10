"""
reset_demo_state.py

Standalone, idempotent reset of the Luminalix demo's write-back state to a
genuine zero state before recording a fresh demo. Run from the repo root with
the datahub venv:

    datahub-venv\\Scripts\\python.exe scripts\\reset_demo_state.py

What it does, in order:

  1. CLEAR the write-back description on the regional_survey_data dataset --
     the editableProperties.description that write_finding() populates with
     "[Luminalix Finding ...]" blocks. The MCP update_description tool
     REPLACES on operation="replace" but REJECTS an empty description
     (ValueError: "description is required"), so the reset clears via the
     GraphQL updateDescription mutation directly with an empty string -- the
     exact mutation that tool's operation="remove" path invokes. The dataset
     entity, its schema, and the ingested (non-editable) description are left
     untouched.

  2. DELETE the freshness assertion entity for regional_survey_data (and its
     run-history timeseries) with a hard delete via the "datahub delete
     by-filter --urn <urn> --hard --force" CLI. The GraphQL deleteAssertion
     mutation does exist in this GMS but only strips the assertion's info
     aspect -- the entity and its AssertionRunEvent timeseries rows remain --
     so the CLI hard delete is used instead (the same delete API the ingest
     pipeline talks to). The assertion URN is deterministic:
     urn:li:assertion:<guid(entity, "freshness", id_raw)> -- the candidate set
     is the known urn plus the URN recomputed from the resolved dataset urn, so
     the reset still lands if a future re-ingestion changed the dataset URN.

  3. DELETE the locally persisted latest report (data/latest_report.json).

  4. DELETE the locally persisted per-source ingestion status files
     (data/ingestion/status/<source>.json).

  5. PRINT a before/after summary of everything found and changed.

Deliberately NOT touched: the SQLite bridge DB (data/luminalix.db), the source
CSVs, the dataset entity itself, and the dataset schema. Every step is
defensive and idempotent: missing targets are reported and skipped, the current
state is reported before any write, and each write is verified by reading state
back before the summary is printed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
REPORT_FILE = REPO_ROOT / "data" / "latest_report.json"
INGESTION_STATUS_DIR = REPO_ROOT / "data" / "ingestion" / "status"

DATASET = "regional_survey_data"
ID_RAW = "regional_survey_data_freshness"
ASSERTION_URN = "urn:li:assertion:12bc937045a23a8b62b6a7ae1a12d4ee"


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


def resolve_dataset_urn(graph, dataset: str) -> str:
    """Resolve a dataset name to its DataHub URN via search, matching on the
    exact entity name -- the same strategy freshness_monitor uses."""
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


def get_editable_description(graph, urn: str) -> str | None:
    """Return the dataset's editableProperties.description, or None if the
    entity does not exist / the field is unset."""
    result = graph.execute_graphql(
        """
        query GetDataset($urn: String!) {
            entity(urn: $urn) {
                urn
                ... on Dataset { editableProperties { description } }
            }
        }
        """,
        variables={"urn": urn},
    )
    entity = result.get("entity") or {}
    if not entity:
        return None
    return (entity.get("editableProperties") or {}).get("description")


def clear_dataset_description(graph, urn: str) -> None:
    """Report the current write-back description, then clear it via the GraphQL
    updateDescription mutation (empty string) and verify the clear."""
    from app.agent.datahub_client import FINDING_MARKER

    marker = FINDING_MARKER
    before = get_editable_description(graph, urn)
    if before is None:
        print(f"    editable description: (unset)")
    elif not before:
        print(f"    editable description: (empty string)")
    else:
        count = before.count(marker)
        print(f"    editable description: {len(before)} chars, "
              f"{count} finding block(s) found (marker {marker!r})")
        print(f"    PREVIEW: {before[:200]!r}...")
        if count == 0:
            print("    NOTE: description has content but no finding markers -- "
                  "clearing anyway.")

    if not before:
        print("    already clear -- skipping write")
        return

    print(f"    clearing via updateDescription(resourceUrn={urn}, description='')")
    result = graph.execute_graphql(
        """
        mutation UpdateDescription($input: DescriptionUpdateInput!) {
            updateDescription(input: $input)
        }
        """,
        variables={"input": {"resourceUrn": urn, "description": ""}},
    )
    if result.get("errors"):
        raise RuntimeError(f"updateDescription failed: {result['errors']}")

    after = get_editable_description(graph, urn)
    if after:
        raise RuntimeError(
            f"VERIFICATION FAILED: description not cleared, got {len(after)} chars."
        )
    print("    VERIFIED: editable description is now clear")


def assertion_run_events_total(graph, urn: str) -> int:
    """Return the number of stored run events for an assertion (0 if none).

    The entity(urn:) GraphQL field returns a stub for ANY assertion URN --
    even one that never existed -- so it cannot be used to detect presence.
    Run events are stored as AssertionRunEvent timeseries aspects, which a
    hard delete removes; a zero total is therefore a reliable absence signal.
    """
    result = graph.execute_graphql(
        """
        query GetAssertion($urn: String!) {
            entity(urn: $urn) {
                urn
                ... on Assertion { runEvents { total } }
            }
        }
        """,
        variables={"urn": urn},
    )
    entity = result.get("entity") or {}
    return (entity.get("runEvents") or {}).get("total") or 0


def assertion_present(graph, urn: str) -> bool:
    """Whether the assertion entity genuinely exists: either its stored
    aspects are present (graph.exists) or it still has run-event history."""
    try:
        if graph.exists(urn):
            return True
    except Exception:  # noqa: BLE001 - fall through to the run-events signal
        pass
    return assertion_run_events_total(graph, urn) > 0


def _resolve_datahub_cli() -> str:
    """Locate the datahub CLI: prefer the repo's datahub-venv, then PATH."""
    exe = REPO_ROOT / "datahub-venv" / "Scripts" / "datahub.exe"
    if exe.exists():
        return str(exe)
    found = shutil.which("datahub")
    if found:
        return found
    raise RuntimeError("datahub CLI not found in datahub-venv/Scripts or on PATH")


def delete_assertion(graph, urn: str, *, cli_env: dict[str, str]) -> None:
    """Hard-delete an assertion entity and its run-history timeseries via the
    "datahub delete by-filter --hard" CLI, then poll-verify it is gone.

    The GraphQL deleteAssertion mutation in this GMS only removes the
    assertion's info aspect -- the entity and its AssertionRunEvent timeseries
    rows remain -- so the hard delete is done through the CLI's delete API
    instead (the same endpoint the ingest pipeline talks to).
    """
    total = assertion_run_events_total(graph, urn)
    if not assertion_present(graph, urn):
        print(f"    {urn}: not present -- skipping")
        return

    print(f"    {urn}: hard-deleting (run history = {total} event(s))")
    proc = subprocess.run(
        [
            _resolve_datahub_cli(),
            "delete", "by-filter",
            "--urn", urn,
            "--hard", "--force",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **cli_env},
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"datahub delete failed for {urn} (exit {proc.returncode}):\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    for _attempt in range(6):
        if not assertion_present(graph, urn):
            print(f"    VERIFIED: {urn} is gone")
            return
        time.sleep(2)
    raise RuntimeError(f"VERIFICATION FAILED: assertion {urn} still present.")


def delete_file_if_exists(path: Path, label: str) -> None:
    """Delete a single local file if it exists; report size before deleting."""
    if not path.exists():
        print(f"    {label}: {path} -- not present, skipping")
        return
    print(f"    {label}: deleting {path} ({path.stat().st_size} bytes)")
    path.unlink()
    if path.exists():
        raise RuntimeError(f"VERIFICATION FAILED: {path} still exists.")
    print(f"    VERIFIED: {path} is gone")


def main() -> int:
    sys.path.insert(0, str(BACKEND_DIR))

    env = load_env(BACKEND_DIR / ".env")
    gms_url = env.get("DATAHUB_GMS_URL", "http://localhost:8080")
    token = env.get("DATAHUB_TOKEN", "")

    from datahub.emitter.mce_builder import datahub_guid, make_assertion_urn
    from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

    print(f"[0] Connecting to DataHub GMS at {gms_url}")
    graph = DataHubGraph(DatahubClientConfig(server=gms_url, token=token))

    print(f"\n[1] Clear write-back description on '{DATASET}'")
    dataset_urn = resolve_dataset_urn(graph, DATASET)
    print(f"    dataset urn: {dataset_urn}")
    clear_dataset_description(graph, dataset_urn)

    print(f"\n[2] Delete freshness assertion + run history")
    recomputed = make_assertion_urn(
        datahub_guid(
            {"entity": dataset_urn, "type": "freshness", "id_raw": ID_RAW}
        )
    )
    candidates = dict.fromkeys([ASSERTION_URN, recomputed])
    print(f"    candidates: {list(candidates)}")
    cli_env = {
        "DATAHUB_GMS_URL": gms_url,
        "DATAHUB_TOKEN": token,
        "DATAHUB_TELEMETRY_ENABLED": "false",
    }
    for urn in candidates:
        delete_assertion(graph, urn, cli_env=cli_env)

    print(f"\n[3] Delete latest report file")
    delete_file_if_exists(REPORT_FILE, "report")

    print(f"\n[4] Delete per-source ingestion status files")
    if not INGESTION_STATUS_DIR.exists():
        print(f"    status dir: {INGESTION_STATUS_DIR} -- not present, skipping")
    else:
        status_files = sorted(INGESTION_STATUS_DIR.glob("*.json"))
        if not status_files:
            print(f"    status dir: {INGESTION_STATUS_DIR} -- no *.json files, skipping")
        for path in status_files:
            delete_file_if_exists(path, "status")

    print(f"\n[5] Summary")
    print(f"    GMS:                    {gms_url}")
    print(f"    dataset:                {DATASET} ({dataset_urn})")
    print(f"    description cleared:    {not (get_editable_description(graph, dataset_urn) or '')}")
    print(f"    assertion removed:      {all(not assertion_present(graph, u) for u in candidates)}")
    print(f"    report file removed:    {not REPORT_FILE.exists()}")
    remaining = sorted(INGESTION_STATUS_DIR.glob("*.json")) if INGESTION_STATUS_DIR.exists() else []
    print(f"    status files remaining: {len(remaining)}")
    print(f"    reset at:               {datetime.now(timezone.utc).isoformat()}")
    print("\nReset complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

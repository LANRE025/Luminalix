"""
cleanup_test_findings.py

One-time, standalone cleanup of the regional_survey_data dataset description
in DataHub. It removes leftover test findings for regions that don't exist in
the actual dataset (Region: Hauts-de-France, Region: Nouvelle-Aquitaine) while
keeping every real finding and the original preamble intact.

Safety protocol (run in order, never skipped):
  1. Read the CURRENT description via get_dataset_metadata and write it to a
     timestamped backup in data/backups/ BEFORE any write operation.
  2. Parse the description into individual finding blocks (each starts with
     "[Luminalix Finding - <timestamp>]") and print every block found.
  3. Classify each block as WOULD REMOVE / WOULD KEEP (exact region match only)
     and print both lists with full block content.
  4. Dry-run mode stops here: no write is performed. Review the output, then
     re-run with --apply to perform the write.
  5. (--apply) Write the cleaned description back via update_description using
     the exact same mechanism write_finding() uses (operation="replace", full
     description), then immediately read back what's stored and print it.

This script intentionally does NOT modify orchestrator.py, datahub_client.py,
or any part of the normal agent pipeline. It only reuses DataHubClient's
already-working MCP plumbing (search/get_entities/update_description).

Usage:
    datahub-venv\\Scripts\\python.exe scripts\\cleanup_test_findings.py           # steps 1-4, dry run
    datahub-venv\\Scripts\\python.exe scripts\\cleanup_test_findings.py --apply   # steps 1-6, writes
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

DATASET = "regional_survey_data"

# Regions that do not exist in the real dataset. Exact match only: a block is
# only classified as a test finding when its Region value equals one of these
# exactly.
TEST_REGIONS = {"Hauts-de-France", "Nouvelle-Aquitaine"}

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
BACKUP_DIR = REPO_ROOT / "data" / "backups"


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


def parse_findings(description: str) -> tuple[str, list[str]]:
    """Split the description into (preamble, list of full finding blocks).

    Mirrors the split used by DataHubClient._append_finding: everything before
    the first finding marker is the preamble; each remaining chunk is one
    finding block, re-prefixed with the marker so the block text is exactly as
    stored in DataHub.
    """
    from app.agent.datahub_client import FINDING_MARKER

    start = description.find(FINDING_MARKER)
    if start == -1:
        return description.strip(), []
    preamble = description[:start].strip()
    body = description[start:]
    blocks = [
        FINDING_MARKER + part.strip()
        for part in body.split(FINDING_MARKER)
        if part.strip()
    ]
    return preamble, blocks


def extract_region(block: str) -> str | None:
    """Return the exact Region value of a finding block, or None if the block
    has no 'Region: <value> |' line."""
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("Region: "):
            return stripped[len("Region: "):].split("|")[0].strip()
    return None


def classify(blocks: list[str]) -> tuple[list[str], list[str]]:
    removed = [b for b in blocks if extract_region(b) in TEST_REGIONS]
    kept = [b for b in blocks if extract_region(b) not in TEST_REGIONS]
    return removed, kept


def build_cleaned(preamble: str, kept: list[str]) -> str:
    """Rebuild the full description exactly like write_finding does: preamble
    (if any) plus each kept finding block, joined with a blank line."""
    sections = ([preamble] if preamble else []) + kept
    return "\n\n".join(sections)


def print_blocks(blocks: list[str]) -> None:
    for i, block in enumerate(blocks, 1):
        print(f"    --- BLOCK {i} ---")
        print(f"    {block}")
        print(f"    ---------------")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the cleaned description back to DataHub (steps 5-6). "
        "Without this flag the script is a dry run and stops at step 4.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(BACKEND_DIR))

    from app.agent.datahub_client import DataHubClient, DataHubMCPError

    env = load_env(BACKEND_DIR / ".env")
    gms_url = env.get("DATAHUB_GMS_URL", "http://localhost:8080")
    token = env.get("DATAHUB_TOKEN", "")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"regional_survey_data_description_backup_{timestamp}.txt"

    print(f"[0] Connecting to DataHub GMS at {gms_url}")
    client = DataHubClient(gms_url=gms_url, token=token)
    try:
        # ---- Step 1: read current description and back it up BEFORE any write.
        metadata = client.get_dataset_metadata(DATASET)
        description = metadata.description or ""
        backup_path.write_text(description, encoding="utf-8")
        print(f"[1] BACKUP SAVED -> {backup_path} ({len(description)} chars)")

        # ---- Step 2: parse and print EVERY finding block found.
        preamble, blocks = parse_findings(description)
        print(f"[2] Parsed {len(blocks)} finding block(s) from the description.")
        if preamble:
            print(f"    PREAMBLE ({len(preamble)} chars):")
            print(f"    {preamble}")
        print("    ALL BLOCKS FOUND:")
        print_blocks(blocks)

        # ---- Step 3: classify WOULD REMOVE / WOULD KEEP.
        removed, kept = classify(blocks)
        print(f"[3] Classification (exact region match): {len(removed)} to remove, {len(kept)} to keep.")
        print("    WOULD REMOVE:")
        print_blocks(removed)
        print("    WOULD KEEP:")
        print_blocks(kept)

        # ---- Step 4: STOP unless --apply was explicitly requested.
        if not args.apply:
            print("[4] DRY RUN - stopping here. No write performed.")
            print(f"    Backup file: {backup_path}")
            print(f"    WOULD REMOVE: {len(removed)} block(s)")
            print(f"    WOULD KEEP:   {len(kept)} block(s)")
            return 0

        # ---- Step 5: write the cleaned description back via the same
        # ---- update_description call write_finding() uses.
        urn = client._resolve_urn(DATASET)
        entities = client._call_tool("get_entities", {"urns": [urn]})
        entity = client._extract_entity(entities, urn)
        current = (entity.get("editableProperties") or {}).get("description") or ""
        if current != description:
            print("[5] ABORT: description changed between backup and write; not writing.")
            return 2

        cleaned = build_cleaned(preamble, kept)
        print(f"[5] Writing cleaned description ({len(cleaned)} chars) via update_description (operation=replace)")
        result = client._call_tool(
            "update_description",
            {"entity_urn": urn, "operation": "replace", "description": cleaned},
        )
        if not (result or {}).get("success"):
            raise DataHubMCPError(
                f"update_description for {urn} did not report success: {result}"
            )
        print("[5] update_description reported success.")

        # ---- Step 6: read back what's actually stored and print it.
        readback = client.get_dataset_metadata(DATASET)
        print("[6] READBACK (current stored description):")
        print("    " + (readback.description or ""))
        if readback.description == cleaned:
            print("[6] VERIFIED: readback matches intended cleaned description.")
        else:
            print("[6] WARNING: readback does NOT match intended description - inspect above.")
            return 3
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

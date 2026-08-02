"""Stub for ingesting the synthetic CSVs into DataHub via the MCP server.

Real ingestion is deferred until a local DataHub instance + MCP server are
running. This file documents the expected DataHub ingestion calls so they can be
filled in quickly:

Expected DataHub ingestion calls:
1. For each CSV (regional_survey_data, hospital_admissions, resource_allocation),
   create/upsert a dataset entity in DataHub, e.g. via the DataHub ingestion
   framework (DataHub CLI / Python SDK ``MetadataChangeProposal``) or an MCP tool
   such as ``create_dataset(name=..., description=...)``.
2. Attach freshness metadata to each dataset entity so the agent's staleness
   check can query it — e.g. set ``customProperties.last_updated`` from the CSV's
   max date, or emit an ``assertion``/``datasetProfile`` with lastModified.
3. Load the CSV rows as structured data attached to each dataset entity (or via
   an MCP tool like ``ingest_dataset_rows(dataset=..., rows=[...])``).

Run from the repo root:

    python data/ingestion/load_to_datahub.py [data/synthetic]
"""

from __future__ import annotations

import sys
from pathlib import Path


def ingest_to_datahub(synthetic_dir: Path) -> None:
    """Upload the three CSVs in ``synthetic_dir`` into DataHub as dataset entities.

    See the module docstring for the expected MCP calls. Implement this once the
    DataHub MCP server is available.
    """
    raise NotImplementedError(
        "DataHub ingestion is stubbed pending a local DataHub instance + MCP "
        "server. See the module docstring for the expected ingestion calls."
    )


def main() -> None:
    synthetic_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/synthetic")
    ingest_to_datahub(synthetic_dir)


if __name__ == "__main__":
    main()

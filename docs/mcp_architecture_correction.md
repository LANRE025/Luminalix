# Architecture Correction: DataHub MCP Capability Boundaries

## What changed and why

The original `datahub_client.py` assumed DataHub's MCP server could return
per-region data (freshness, values, annotations) as if "region" were a
DataHub entity. It isn't — DataHub's MCP tools (`search`, `get_entities`,
`list_schema_fields`, `get_lineage`, `get_dataset_queries`,
`get_lineage_paths_between`, `draft_sql_for_tables`) operate at the
dataset (whole table) level only. Region is a column value inside a
dataset, invisible to DataHub as its own object. None of DataHub's MCP
tools execute queries or return row-level data — `draft_sql_for_tables`
drafts SQL grounded in schema context, it doesn't run it.

## The corrected architecture

- **data_access.py** — real SQLite queries for everything region-specific:
  survey staleness, admissions trend, resource levels. This plays the role
  a real warehouse client (Snowflake/BigQuery connector) would play in a
  production DataHub deployment.
- **datahub_client.py** — scoped to what MCP actually supports: dataset-level
  metadata (`get_dataset_metadata`, `get_lineage`) and write-back
  (`write_finding`, via `update_description`). Genuinely goes through
  DataHub MCP, just doesn't pretend to do things DataHub can't do.
- **orchestrator.py** — combines both correctly: loops over regions using
  real data, calls Gemini for reasoning, writes findings back through
  DataHub MCP as dataset-level, region-tagged notes.

## Still TODO (real MCP wiring, not stubs anymore)

`datahub_client.py`'s two methods (`get_dataset_metadata`, `write_finding`)
still raise `NotImplementedError` — but now with the CORRECT tool calls
documented in each docstring (`get_entities`, `list_schema_fields`,
`update_description`), ready to fill in against a live `mcp` SDK session.
Everything else (data access, reasoning, orchestrator loop) is real,
tested, working code — verified end-to-end against the actual SQLite
database built from your combined/synthetic CSVs.

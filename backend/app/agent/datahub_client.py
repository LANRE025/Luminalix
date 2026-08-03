"""
datahub_client.py

DataHub MCP client, scoped strictly to what DataHub's MCP server actually
exposes: dataset-level (table-level) metadata — schema, freshness/lastModified,
lineage — plus write-back via update_description / add_structured_properties.

What this deliberately does NOT do, and why:
    - No per-region freshness, values, or annotations. Region is a column
      value inside a dataset, not a DataHub entity — there is no
      get_dataset_freshness(entity=region) or equivalent, because DataHub
      has no concept of a "region entity" to attach that to.
    - No row-level data retrieval of any kind. DataHub's MCP tools
      (search, get_entities, list_schema_fields, get_lineage,
      get_dataset_queries, get_lineage_paths_between, draft_sql_for_tables)
      are all metadata/schema/lineage operations. None of them execute a
      query or return cell values. Real region-level values (staleness,
      admissions trend, resource levels) come from data_access.py, which
      queries the actual data directly — the same architectural split
      a production DataHub deployment would have with a real warehouse
      client sitting alongside DataHub.

What this DOES do, for real:
    - get_dataset_metadata(dataset): schema + last-modified timestamp for
      one of the three whole tables (regional_survey_data,
      hospital_admissions, resource_allocation), via get_entities.
    - write_finding(...): appends a human-readable, region-tagged finding
      to the regional_survey_data dataset's description via
      update_description — this is the real "write back to DataHub"
      step. It's dataset-level text, not a per-region structured field
      (because per-region structured fields aren't a thing DataHub
      supports), but it's genuinely discoverable by anyone who opens that
      dataset in DataHub afterward, which is what the hackathon's
      "contributes back to the graph" criterion is actually asking for.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class DatasetMetadata:
    dataset: str
    last_modified: datetime | None
    schema_fields: list[str]
    description: str | None


class DataHubClient:
    """
    Wraps calls to DataHub's MCP server. The actual MCP session/transport
    setup depends on the `mcp` SDK's client API and your DataHub Cloud/
    local GMS connection details (see backend/.env: DATAHUB_GMS_URL,
    DATAHUB_TOKEN) — fill in `self._session` in __init__ once you're
    wiring this against a live MCP session object.
    """

    def __init__(self, gms_url: str, token: str):
        self.gms_url = gms_url
        self.token = token
        # TODO: initialize the real MCP client session here, e.g.:
        # from mcp import ClientSession
        # self._session = ClientSession(...)

    # ------------------------------------------------------------------
    # Reads — dataset (table)-level only
    # ------------------------------------------------------------------

    def get_dataset_metadata(self, dataset: str) -> DatasetMetadata:
        """
        Calls DataHub's get_entities / list_schema_fields tools for the
        given dataset (e.g. "regional_survey_data"). Returns table-level
        freshness and schema — NOT anything region-specific.

        Real MCP tool calls this should make (fill in against the live
        `mcp` SDK client):
            entity = self._session.call_tool("get_entities", {"urns": [dataset_urn]})
            fields = self._session.call_tool("list_schema_fields", {"urn": dataset_urn})
        """
        raise NotImplementedError(
            "Wire this against the real MCP session — see docstring for the "
            "actual tool calls (get_entities, list_schema_fields)."
        )

    def get_lineage(self, dataset: str) -> dict[str, Any]:
        """Optional, for demo polish: shows upstream/downstream of a
        dataset via get_lineage / get_lineage_paths_between. Not required
        for the core agent loop, but a nice thing to surface in the UI
        to show real DataHub context is being used."""
        raise NotImplementedError("Wire against get_lineage MCP tool if used.")

    # ------------------------------------------------------------------
    # Writes — dataset-level description, tagged by region in the text
    # ------------------------------------------------------------------

    def write_finding(
        self,
        dataset: str,
        region: str,
        vulnerability_level: str,
        justification: str,
        confidence: str,
        key_signals: list[str],
    ) -> bool:
        """
        Appends a region-tagged finding to the dataset's description via
        DataHub's update_description tool. This is dataset-level (not a
        per-region structured field, since that doesn't exist in DataHub's
        model) but it's real, persistent, and discoverable by anyone who
        opens `dataset` in DataHub afterward — which is what satisfies
        the hackathon's write-back / "contributes to the graph" criterion.

        Real MCP tool call this should make:
            note = self._format_finding_note(region, vulnerability_level, ...)
            self._session.call_tool("update_description", {
                "urn": dataset_urn,
                "description": existing_description + "\\n\\n" + note,
            })

        Note: since update_description likely REPLACES the description
        rather than appending, you'll need to first read the current
        description (via get_entities), append your note to it, and
        write the full result back — otherwise each new finding will
        overwrite the last one.
        """
        note = self._format_finding_note(
            region, vulnerability_level, justification, confidence, key_signals
        )
        raise NotImplementedError(
            "Wire against get_entities (read current description) + "
            "update_description (write back current + new note). "
            f"Formatted note ready to use:\n{note}"
        )

    @staticmethod
    def _format_finding_note(
        region: str, level: str, justification: str, confidence: str, signals: list[str]
    ) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"**[Luminalix Finding — {timestamp}]**\n"
            f"Region: {region} | Vulnerability: {level} | Confidence: {confidence}\n"
            f"{justification}\n"
            f"Key signals: {', '.join(signals)}"
        )

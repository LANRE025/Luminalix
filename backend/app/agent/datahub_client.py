"""
datahub_client.py

Real DataHub MCP client, wired against the live MCP server that ships with
DataHub (``mcp-server-datahub``, installed in this repo's ``datahub-venv``).
It connects over stdio using the `mcp` Python SDK and drives the dataset-level
tools this deployment actually exposes.

Tool names/schemas were confirmed by live introspection of THIS instance
(DataHub GMS v1.7.0 + mcp-server-datahub 0.6.0). Nothing is assumed from
docs:

    search(query, filter, num_results, ...)       resolve dataset name -> URN
    get_entities(urns=[...])                      entity metadata + current
                                                  editable description
    list_schema_fields(urn, limit, offset)        schema fields
    update_description(entity_urn, operation,     write the description back
        description, column_path)                 NOTE: arg is `entity_urn`,
                                                  not `urn` (confirmed live)
    get_lineage(urn, upstream, max_hops, ...)     optional demo polish

This is scoped strictly to dataset-level (table-level) metadata — schema,
freshness/lastModified, lineage — plus write-back via update_description.
It deliberately does NOT do per-region freshness/values/annotations: region
is a column value inside a dataset, not a DataHub entity, and none of
DataHub's MCP tools execute queries or return row-level data. Real
region-level values come from data_access.py, which queries the actual
SQLite database directly — the same architectural split a production
DataHub deployment would have with a warehouse client sitting alongside
DataHub.

What this DOES do, for real:
    - get_dataset_metadata(dataset): schema + last-modified timestamp for
      one of the three whole tables (regional_survey_data,
      hospital_admissions, resource_allocation).
    - write_finding(...): appends a human-readable, region-tagged finding
      to the regional_survey_data dataset's description via
      update_description — the real "write back to DataHub" step, capped at
      the 10 most recent findings.
"""

import asyncio
import json
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.util import find_spec
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MAX_FINDINGS = 10
FINDING_MARKER = "**[Luminalix Finding — "


class DatasetNotFoundError(Exception):
    """Raised when a dataset name cannot be resolved to a DataHub entity."""


class DataHubMCPError(Exception):
    """Raised when the MCP server or one of its tool calls fails."""


@dataclass
class DatasetMetadata:
    dataset: str
    last_modified: datetime | None
    schema_fields: list[str]
    description: str | None


class DataHubClient:
    """
    Wraps calls to DataHub's MCP server. The `mcp` SDK session is async, but
    this client is consumed from synchronous code (the orchestrator runs in a
    worker thread, tests use it directly). To bridge that, a dedicated
    daemon thread owns a long-lived asyncio event loop and a single MCP
    ClientSession; every tool call is dispatched to that loop via
    ``asyncio.run_coroutine_threadsafe`` and blocks on the result.

    The MCP server runs as a stdio subprocess launched with
    ``DATAHUB_GMS_URL`` / ``DATAHUB_GMS_TOKEN`` / ``TOOLS_IS_MUTATION_ENABLED``
    set, which is how the self-hosted ``mcp-server-datahub`` is configured.
    """

    def __init__(
        self,
        gms_url: str,
        token: str,
        *,
        timeout: float = 60.0,
    ):
        self.gms_url = gms_url
        self.token = token
        self._timeout = timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stdio: Any = None
        self._session: ClientSession | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._urn_cache: dict[str, str] = {}

        if not find_spec("mcp_server_datahub"):
            raise DataHubMCPError(
                "mcp-server-datahub is not installed. Install it into the backend "
                "environment (pip install mcp-server-datahub) before wiring DataHub."
            )

        self._thread = threading.Thread(
            target=self._run_loop, name="datahub-mcp", daemon=True
        )
        self._thread.start()

        if not self._ready.wait(timeout=timeout):
            raise DataHubMCPError(
                f"DataHub MCP server did not become ready within {timeout:.0f}s"
                + (f": {self._startup_error}" if self._startup_error else "")
            )
        if self._startup_error is not None:
            raise DataHubMCPError(f"Failed to start DataHub MCP server: {self._startup_error}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._connect())
            self._ready.set()
            loop.run_forever()
        except BaseException as exc:  # noqa: BLE001 - surfaced via _startup_error
            self._startup_error = exc
            self._ready.set()
        finally:
            try:
                if self._session is not None:
                    loop.run_until_complete(self._session.__aexit__(None, None, None))
            except Exception:  # noqa: BLE001
                pass
            self._session = None
            self._stdio = None
            loop.close()

    async def _connect(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "DATAHUB_GMS_URL": self.gms_url,
                "DATAHUB_GMS_TOKEN": self.token,
                "TOOLS_IS_MUTATION_ENABLED": "true",
            }
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server_datahub.__main__"],
            env=env,
        )
        self._stdio = stdio_client(params)
        read, write = await self._stdio.__aenter__()
        self._session = await ClientSession(read, write).__aenter__()
        await self._session.initialize()

    def close(self) -> None:
        """Shut down the MCP session and the underlying subprocess."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        async def _shutdown() -> None:
            if self._session is not None:
                await self._session.__aexit__(None, None, None)
                self._session = None
            if self._stdio is not None:
                await self._stdio.__aexit__(None, None, None)
                self._stdio = None

        try:
            asyncio.run_coroutine_threadsafe(_shutdown(), loop).result(timeout=self._timeout)
        except Exception:  # noqa: BLE001
            pass
        finally:
            loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=10)

    def __enter__(self) -> "DataHubClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # MCP plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _result_text(result: Any) -> str:
        parts = []
        for block in getattr(result, "content", None) or []:
            if getattr(block, "type", "") == "text":
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts)

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._loop is None or self._session is None:
            raise DataHubMCPError("DataHub MCP session is not connected")
        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments), self._loop
        )
        result = future.result(timeout=self._timeout)

        if getattr(result, "isError", False):
            raise DataHubMCPError(
                f"DataHub MCP tool '{name}' failed: {self._result_text(result)}"
            )

        structured = getattr(result, "structuredContent", None)
        text = self._result_text(result)
        if text:
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                return text
        return structured if structured is not None else text

    @staticmethod
    def _extract_entity(payload: Any, urn: str) -> dict:
        """get_entities may return a single dict or a list of dicts (one of
        which can be an error entry for a missing entity)."""
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            if "error" in item:
                continue
            if item.get("urn") == urn:
                return item
        # No clean match — surface the first error we saw, if any.
        for item in items:
            if isinstance(item, dict) and "error" in item:
                raise DatasetNotFoundError(str(item["error"]))
        raise DataHubMCPError(f"get_entities returned an unexpected shape for {urn}: {payload}")

    # ------------------------------------------------------------------
    # Name -> URN resolution (via the search tool)
    # ------------------------------------------------------------------

    def _resolve_urn(self, dataset: str) -> str:
        cached = self._urn_cache.get(dataset)
        if cached:
            return cached

        payload = self._call_tool(
            "search",
            {"query": dataset, "filter": "entity_type = dataset", "num_results": 20},
        )
        results = (payload or {}).get("searchResults", [])
        match_urn = None
        for item in results:
            entity = item.get("entity", {})
            name = (entity.get("properties") or {}).get("name")
            if name and name.lower() == dataset.lower():
                match_urn = entity.get("urn")
                break

        if not match_urn:
            raise DatasetNotFoundError(
                f"Dataset '{dataset}' was not found in DataHub (GMS {self.gms_url}). "
                "Check the dataset was ingested — see data/ingestion/load_to_datahub.yml."
            )

        self._urn_cache[dataset] = match_urn
        return match_urn

    @staticmethod
    def _extract_last_modified(entity: dict) -> datetime | None:
        """DataHub doesn't expose a real last-modified timestamp for this
        dataset (GMS reports lastModified.time=0 / schema createdAt=null), so
        this returns None unless a timestamp is actually present."""
        ts: Any = None
        properties = entity.get("properties") or {}
        last_modified = properties.get("lastModified")
        if isinstance(last_modified, dict):
            ts = last_modified.get("time")
        if ts in (None, 0, ""):
            ts = (entity.get("schemaMetadata") or {}).get("createdAt")
        if ts in (None, 0, ""):
            return None
        if isinstance(ts, datetime):
            return ts
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            return None
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)

    # ------------------------------------------------------------------
    # Reads — dataset (table)-level only
    # ------------------------------------------------------------------

    def get_dataset_metadata(self, dataset: str) -> DatasetMetadata:
        """Calls DataHub's search -> get_entities -> list_schema_fields for the
        given dataset name (e.g. "regional_survey_data"). Returns table-level
        schema, current description, and last-modified (None when DataHub has
        no timestamp recorded for the dataset). NOT anything region-specific.
        """
        urn = self._resolve_urn(dataset)
        entities = self._call_tool("get_entities", {"urns": [urn]})
        entity = self._extract_entity(entities, urn)

        schema = self._call_tool("list_schema_fields", {"urn": urn, "limit": 500})
        fields = [
            f.get("fieldPath")
            for f in (schema or {}).get("fields", [])
            if f.get("fieldPath")
        ]

        editable = (entity.get("editableProperties") or {}).get("description")
        properties = (entity.get("properties") or {}).get("description")
        description = editable or properties

        return DatasetMetadata(
            dataset=dataset,
            last_modified=self._extract_last_modified(entity),
            schema_fields=fields,
            description=description,
        )

    def get_lineage(self, dataset: str) -> dict[str, Any]:
        """Shows upstream/downstream of a dataset via get_lineage. For demo
        polish only — the core agent loop does not depend on it."""
        urn = self._resolve_urn(dataset)
        return self._call_tool(
            "get_lineage", {"urn": urn, "upstream": True, "max_hops": 1, "max_results": 20}
        )

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
        """Appends a region-tagged finding to the dataset's description via
        DataHub's update_description tool.

        Because update_description replaces the description (unless given
        operation="append", which can't enforce a cap), this reads the current
        description first (via get_entities), appends the new note, keeps only
        the most recent MAX_FINDINGS (10) findings, and writes the full result
        back with operation="replace".
        """
        note = self._format_finding_note(
            region, vulnerability_level, justification, confidence, key_signals
        )
        urn = self._resolve_urn(dataset)

        entities = self._call_tool("get_entities", {"urns": [urn]})
        entity = self._extract_entity(entities, urn)
        current = (entity.get("editableProperties") or {}).get("description") or ""

        combined = self._append_finding(current, note)

        result = self._call_tool(
            "update_description",
            {"entity_urn": urn, "operation": "replace", "description": combined},
        )
        if not (result or {}).get("success"):
            raise DataHubMCPError(
                f"update_description for {urn} did not report success: {result}"
            )
        return True

    @classmethod
    def _append_finding(cls, current: str, note: str) -> str:
        """Returns the new full description: the original preamble (everything
        before the first finding marker) plus the last MAX_FINDINGS findings
        including the newly appended one. Parts are stored without the marker
        and re-prefixed on join so existing findings never lose it."""
        start = current.find(FINDING_MARKER)
        if start == -1:
            preamble, findings = current.strip(), []
        else:
            preamble = current[:start].strip()
            body = current[start:]
            findings = [
                part.strip() for part in body.split(FINDING_MARKER) if part.strip()
            ]

        # Drop the oldest finding(s) so that, together with the new note,
        # we never keep more than MAX_FINDINGS. note already starts with the
        # marker, so strip it and re-prefix below for a consistent format.
        if len(findings) >= MAX_FINDINGS:
            findings = findings[-(MAX_FINDINGS - 1):]
        findings.append(note[len(FINDING_MARKER):])

        sections = ([preamble] if preamble else []) + [
            FINDING_MARKER + part for part in findings
        ]
        return "\n\n".join(sections)

    @staticmethod
    def _format_finding_note(
        region: str, level: str, justification: str, confidence: str, signals: list[str]
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"{FINDING_MARKER}{timestamp}]**\n"
            f"Region: {region} | Vulnerability: {level} | Confidence: {confidence}\n"
            f"{justification}\n"
            f"Key signals: {', '.join(signals)}"
        )

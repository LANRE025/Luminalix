"""DataHub MCP client wrapper.

The MCP server is NOT wired up yet, so every method is a stub that raises
``NotImplementedError``. Each docstring describes the exact MCP call the method
should make once a local DataHub instance + MCP server are available — fill
these in as your first step after standing up DataHub.
"""

from __future__ import annotations

from app.models.schemas import RegionAssessment, RegionFreshness, RegionInfo


class DataHubClient:
    """Thin wrapper over the DataHub MCP server (read + write operations)."""

    def get_regions(self, dataset: str) -> list[RegionInfo]:
        """Return every region present in ``dataset``.

        Expected MCP call: list the entities/rows of ``dataset`` and map each
        one to a ``RegionInfo`` (region id + country). For example an MCP tool
        such as ``get_dataset_entities(dataset="regional_survey_data")``
        returning the entities owned by that dataset, with the country derived
        from entity properties or the URN naming convention.
        """
        raise NotImplementedError(
            "DataHub MCP integration is stubbed. Implement get_regions once the "
            "MCP server is available (see docstring for the expected MCP call)."
        )

    def get_freshness(self, region: str, dataset: str) -> RegionFreshness:
        """Return freshness metadata for ``region`` in ``dataset``.

        Expected MCP call: read the dataset entity's last-updated timestamp,
        e.g. via ``get_dataset_freshness(dataset=dataset, entity=region)`` or by
        reading ``customProperties.last_updated`` from the entity, then compute
        ``days_stale`` as ``now - last_updated``.
        """
        raise NotImplementedError(
            "DataHub MCP integration is stubbed. Implement get_freshness once "
            "the MCP server is available (see docstring for the expected MCP call)."
        )

    def get_recent_values(self, region: str, dataset: str, lookback_days: int) -> list[float]:
        """Return the most recent numeric values for ``region`` in ``dataset``.

        Expected MCP call: query the time series of ``dataset`` for ``region``
        filtered to the last ``lookback_days`` (oldest → newest), e.g. via an
        MCP tool like ``get_time_series(dataset=dataset, entity=region, days=lookback_days)``.
        Used for the hospital admissions proxy signal.
        """
        raise NotImplementedError(
            "DataHub MCP integration is stubbed. Implement get_recent_values "
            "once the MCP server is available (see docstring for the expected MCP call)."
        )

    def get_values(self, region: str, dataset: str) -> dict[str, float]:
        """Return the current values for ``region`` in ``dataset``.

        Expected MCP call: read the entity's property bag / columns, e.g. via
        ``get_entity_properties(dataset=dataset, entity=region)`` returning
        key → numeric value. Used for resource allocation (funding, staff,
        vaccine stock).
        """
        raise NotImplementedError(
            "DataHub MCP integration is stubbed. Implement get_values once the "
            "MCP server is available (see docstring for the expected MCP call)."
        )

    def write_annotation(self, region: str, dataset: str, assessment: RegionAssessment) -> None:
        """Write a vulnerability assessment back to DataHub as an annotation.

        Expected MCP call: attach a structured note/annotation to the ``dataset``
        entity for ``region``, e.g. via ``add_annotation(dataset=dataset, entity=region,
        annotation=assessment.model_dump(mode="json"))``. The annotation should be
        discoverable by anyone who later opens that dataset in DataHub.
        """
        raise NotImplementedError(
            "DataHub MCP integration is stubbed. Implement write_annotation once "
            "the MCP server is available (see docstring for the expected MCP call)."
        )

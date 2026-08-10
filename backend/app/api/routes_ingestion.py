"""Ingestion routes: list sources, trigger a re-ingestion, poll its status.

Everything here is user-triggered — a re-ingestion starts only when this
endpoint is called (directly, or via the frontend "Reingest" button). No
scheduled or background processes exist anywhere in this feature.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.agent.ingestion_sources import INGESTION_SOURCES
from app.agent.reingestion import run_reingestion
from app.models.schemas import (
    IngestionRunStatus,
    IngestionRunStatusValue,
    IngestionSourceInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/sources", response_model=list[IngestionSourceInfo])
async def list_sources(request: Request) -> list[IngestionSourceInfo]:
    """Return the registry of ingestable sources plus their last-known status."""
    store = request.app.state.ingestion_status_store
    sources: list[IngestionSourceInfo] = []
    for source in INGESTION_SOURCES.values():
        info = IngestionSourceInfo(
            name=source.name,
            display_name=source.display_name,
            input_type=source.input_type,
            description=source.description,
        )
        last = store.load(source.name)
        if last:
            info.last_status = IngestionRunStatusValue(last["status"])
            if last.get("completed_at"):
                info.last_completed_at = datetime.fromisoformat(last["completed_at"])
        sources.append(info)
    return sources


@router.post("/run/{source_name}", response_model=IngestionRunStatus, status_code=202)
async def run_ingestion(
    source_name: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> IngestionRunStatus:
    """Trigger a re-ingestion of one named source as a background task."""
    if source_name not in INGESTION_SOURCES:
        raise HTTPException(
            status_code=404, detail=f"Unknown ingestion source: {source_name!r}"
        )

    store = request.app.state.ingestion_status_store
    current = store.load(source_name)
    if current and current.get("status") == IngestionRunStatusValue.RUNNING:
        # Already running — report the in-flight status instead of re-triggering.
        return IngestionRunStatus.model_validate(current)

    status = IngestionRunStatus(
        source=source_name,
        status=IngestionRunStatusValue.RUNNING,
        started_at=_now(),
    )
    store.save(source_name, status.model_dump(mode="json"))
    background_tasks.add_task(_execute_ingestion, request.app.state, source_name)
    return status


async def _execute_ingestion(state, source_name: str) -> None:
    """Run the blocking re-ingestion in a worker thread and persist the outcome."""
    try:
        result = await asyncio.to_thread(
            run_reingestion,
            source_name,
            datahub_token=state.settings.datahub_token,
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure as a run error
        logger.exception("Re-ingestion of '%s' raised", source_name)
        result = {
            "source": source_name,
            "status": IngestionRunStatusValue.ERROR,
            "rows_ingested": 0,
            "started_at": _now().isoformat(),
            "completed_at": _now().isoformat(),
            "error_message": str(exc),
        }
    state.ingestion_status_store.save(source_name, result)


@router.get("/status/{source_name}", response_model=IngestionRunStatus)
async def get_ingestion_status(source_name: str, request: Request) -> IngestionRunStatus:
    """Return the most recent re-ingestion result for a source (idle if never run)."""
    if source_name not in INGESTION_SOURCES:
        raise HTTPException(
            status_code=404, detail=f"Unknown ingestion source: {source_name!r}"
        )
    store = request.app.state.ingestion_status_store
    last = store.load(source_name)
    if last is None:
        return IngestionRunStatus(source=source_name)
    return IngestionRunStatus.model_validate(last)

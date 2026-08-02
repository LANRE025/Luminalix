"""Agent lifecycle routes: trigger a run and poll its status."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Request

from app.models.schemas import AgentRunStatus, AgentRunStatusValue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/run", response_model=AgentRunStatus, status_code=202)
async def run_agent(request: Request, background_tasks: BackgroundTasks) -> AgentRunStatus:
    """Trigger the agent loop as a background task (no Celery/queues needed)."""
    state = request.app.state
    if state.run_status.status == AgentRunStatusValue.RUNNING:
        return state.run_status

    state.run_status.status = AgentRunStatusValue.RUNNING
    state.run_status.started_at = _now()
    state.run_status.completed_at = None
    state.run_status.error_message = None

    background_tasks.add_task(_execute_run, state)
    return state.run_status


async def _execute_run(state) -> None:
    """Run the blocking orchestrator in a worker thread and record the outcome."""
    try:
        report = await asyncio.to_thread(state.orchestrator.run)
        state.run_status.status = AgentRunStatusValue.COMPLETE
        state.run_status.completed_at = _now()
        logger.info("Agent run completed: %d of %d regions flagged", report.total_flagged, report.total_regions_evaluated)
    except Exception as exc:  # noqa: BLE001 - surface any failure as a run error
        logger.exception("Agent run failed")
        state.run_status.status = AgentRunStatusValue.ERROR
        state.run_status.completed_at = _now()
        state.run_status.error_message = str(exc)


@router.get("/status", response_model=AgentRunStatus)
async def get_status(request: Request) -> AgentRunStatus:
    """Return the current status of the most recent (or running) agent run."""
    return request.app.state.run_status

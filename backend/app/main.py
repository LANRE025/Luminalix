"""FastAPI application entrypoint.

Run from the ``backend/`` directory:

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.data_access import DataAccess
from app.agent.datahub_client import DataHubClient
from app.api.routes_agent import router as agent_router
from app.api.routes_regions import router as regions_router
from app.config import get_settings
from app.models.schemas import AgentRunStatus
from app.storage.report_store import ReportStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the app's singletons and stash them on ``app.state``."""
    settings = get_settings()
    app.state.settings = settings
    app.state.data_access = DataAccess()
    app.state.datahub_client = DataHubClient(
        gms_url=settings.datahub_gms_url,
        token=settings.datahub_token,
    )
    app.state.report_store = ReportStore(settings.report_file_path)
    app.state.run_status = AgentRunStatus()
    logger.info("Outbreak Vulnerability Sentinel backend ready")
    yield
    # Tear down the MCP subprocess cleanly on shutdown.
    try:
        app.state.datahub_client.close()
    except Exception:  # noqa: BLE001
        logger.warning("Failed to close DataHub MCP client on shutdown", exc_info=True)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Outbreak Vulnerability Sentinel API",
        description=(
            "Detects blind spots in global disease surveillance by cross-referencing "
            "survey staleness, hospital admissions trends, and resource allocation "
            "per region."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(agent_router)
    app.include_router(regions_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

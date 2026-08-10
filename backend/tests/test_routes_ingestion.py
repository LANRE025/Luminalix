"""Route tests for /ingestion endpoints (minimal app, no DataHub/MCP side effects)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_ingestion


def _make_app(tmp_path) -> FastAPI:
    from app.api.routes_ingestion import router
    from app.storage.ingestion_status_store import IngestionStatusStore

    app = FastAPI()
    app.include_router(router)
    app.state.settings = SimpleNamespace(datahub_token="test-token")
    app.state.ingestion_status_store = IngestionStatusStore(tmp_path / "status")
    return app


def test_list_sources(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/ingestion/sources")
    assert resp.status_code == 200
    sources = resp.json()
    assert [s["name"] for s in sources] == ["covid", "tb", "malaria", "influenza"]
    assert all(s["last_status"] is None for s in sources)


def test_status_never_run_is_idle(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/ingestion/status/covid")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "idle"
    assert body["completed_at"] is None


def test_status_unknown_source_404(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.get("/ingestion/status/ebola")
    assert resp.status_code == 404


def test_run_unknown_source_404(tmp_path):
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        resp = client.post("/ingestion/run/ebola")
    assert resp.status_code == 404


def test_run_ingestion_end_to_end(tmp_path, monkeypatch):
    """POST starts a run; the background task persists the final result."""
    fake = lambda source_name, *, datahub_token="": {  # noqa: E731
        "source": source_name,
        "status": "complete",
        "rows_ingested": 99,
        "started_at": "2026-08-10T00:00:00+00:00",
        "completed_at": "2026-08-10T00:00:01+00:00",
        "error_message": None,
    }
    monkeypatch.setattr(routes_ingestion, "run_reingestion", fake)

    app = _make_app(tmp_path)
    with TestClient(app) as client:
        post_resp = client.post("/ingestion/run/covid")
        assert post_resp.status_code == 202
        assert post_resp.json()["status"] == "running"

        status_resp = client.get("/ingestion/status/covid")
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["status"] == "complete"
        assert body["rows_ingested"] == 99

        sources_resp = client.get("/ingestion/sources")
        covid = next(
            s for s in sources_resp.json() if s["name"] == "covid"
        )
        assert covid["last_status"] == "complete"


def test_run_ingestion_already_running_not_retriggered(tmp_path, monkeypatch):
    store = None
    calls = []

    def fake(source_name, *, datahub_token=""):
        calls.append(source_name)
        return {
            "source": source_name,
            "status": "complete",
            "rows_ingested": 1,
            "started_at": "2026-08-10T00:00:00+00:00",
            "completed_at": "2026-08-10T00:00:01+00:00",
            "error_message": None,
        }

    monkeypatch.setattr(routes_ingestion, "run_reingestion", fake)

    app = _make_app(tmp_path)
    with TestClient(app) as client:
        # Pre-seed a running status (as if a run just started).
        store = app.state.ingestion_status_store
        store.save(
            "covid",
            {
                "source": "covid",
                "status": "running",
                "rows_ingested": 0,
                "started_at": "2026-08-10T00:00:00+00:00",
                "completed_at": None,
                "error_message": None,
            },
        )
        resp = client.post("/ingestion/run/covid")

    assert resp.status_code == 202
    assert resp.json()["status"] == "running"
    assert calls == []  # no new run spawned while already running

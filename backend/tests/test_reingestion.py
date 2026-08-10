"""Unit tests for run_reingestion() (no real subprocesses / network / GMS)."""

from __future__ import annotations

from unittest.mock import Mock

from app.agent import reingestion
from app.agent.ingestion_sources import DATAHUB_RECIPE, IngestionSource


def _patch_reingestion_helpers(monkeypatch, *, survey_rows=0):
    """Stub every external side effect run_reingestion() touches."""
    downloads = []
    monkeypatch.setattr(reingestion, "_download", lambda url, dest: downloads.append((url, str(dest))))
    run_calls = []
    monkeypatch.setattr(reingestion, "_run", lambda *args, **kwargs: run_calls.append((args, kwargs)))
    swaps = []
    monkeypatch.setattr(
        reingestion,
        "_build_db",
        lambda script, tmp, final: swaps.append((script, str(tmp), str(final))),
    )
    monkeypatch.setattr(reingestion, "_count_survey_rows", lambda _db: survey_rows)
    monkeypatch.setattr(reingestion, "_resolve_datahub_cli", lambda: "datahub-test")
    return downloads, run_calls, swaps


def test_run_reingestion_covid_success(monkeypatch):
    downloads, run_calls, swaps = _patch_reingestion_helpers(monkeypatch, survey_rows=321)

    result = reingestion.run_reingestion("covid", datahub_token="tok-123")

    assert result["source"] == "covid"
    assert result["status"] == "complete"
    assert result["rows_ingested"] == 321
    assert result["completed_at"] is not None
    assert result["error_message"] is None

    # Input downloaded from the live OWID URL into data/raw.
    assert len(downloads) == 1
    url, dest = downloads[0]
    assert url == reingestion.INGESTION_SOURCES["covid"].input
    assert dest.endswith("owid-covid-data.csv")

    # Process step + 4 shared tail steps + the DataHub CLI ingestion.
    cmds = [args[0] for args, _ in run_calls]
    assert len(cmds) == 6
    assert str(cmds[0][-1]).endswith("process_covid.py")
    assert [str(c[-1]).split("\\")[-1].split("/")[-1] for c in cmds[1:5]] == [
        "combine_regional_survey_data.py",
        "generate_synthetic_diseases.py",
        "generate_hospital_admissions.py",
        "generate_resource_allocation.py",
    ]

    # Both SQLite DBs rebuilt via temp file + swap.
    assert len(swaps) == 2
    assert str(swaps[0][1]) == str(reingestion._AGENT_DB.with_suffix(".tmp"))
    assert str(swaps[0][2]) == str(reingestion._AGENT_DB)
    assert str(swaps[1][1]) == str(reingestion._DATAHUB_DB.with_suffix(".tmp"))
    assert str(swaps[1][2]) == str(reingestion._DATAHUB_DB)

    # DataHub CLI invoked with the shared recipe and the token in env.
    ingest_call = next(
        (
            (args[0], env)
            for args, env in run_calls
            if any(str(a) == "ingest" for a in args[0])
        ),
        None,
    )
    assert ingest_call is not None
    ingest_cmd, ingest_env = ingest_call
    assert str(ingest_cmd[0]) == "datahub-test"
    assert "ingest" in [str(a) for a in ingest_cmd][:3]
    assert any(str(a) == "-c" for a in ingest_cmd)
    assert any(str(a).replace("\\", "/").endswith(DATAHUB_RECIPE) for a in ingest_cmd)
    assert ingest_env["env"]["DATAHUB_TOKEN"] == "tok-123"


def test_run_reingestion_unknown_source(monkeypatch):
    downloads, _, _ = _patch_reingestion_helpers(monkeypatch)

    result = reingestion.run_reingestion("ebola")

    assert result["status"] == "error"
    assert "Unknown ingestion source" in result["error_message"]
    assert result["completed_at"] is not None
    assert downloads == []  # nothing attempted


def test_run_reingestion_missing_local_file(monkeypatch):
    monkeypatch.setattr(
        reingestion,
        "INGESTION_SOURCES",
        {
            "fake": IngestionSource(
                name="fake",
                display_name="Fake",
                input_type="file",
                input="data/raw/does_not_exist.csv",
                process_script="data/ingestion/process_covid.py",
            )
        },
    )

    result = reingestion.run_reingestion("fake")

    assert result["status"] == "error"
    assert "Input file not found" in result["error_message"]


def test_run_reingestion_subprocess_failure_returns_error(monkeypatch):
    _, run_calls, _ = _patch_reingestion_helpers(monkeypatch)

    def boom(*args, **kwargs):
        run_calls.append((args, kwargs))
        raise RuntimeError("combine script exploded")

    monkeypatch.setattr(reingestion, "_run", boom)

    result = reingestion.run_reingestion("covid")

    assert result["status"] == "error"
    assert "combine script exploded" in result["error_message"]
    assert result["completed_at"] is not None


def test_run_reingestion_cleans_up_temp_dbs_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(reingestion, "_count_survey_rows", lambda _db: 10)
    monkeypatch.setattr(reingestion, "_resolve_datahub_cli", lambda: "datahub-test")
    monkeypatch.setattr(reingestion, "_run", Mock())
    # Point the DB targets into a temp dir so we can inspect the swap cleanup.
    agent_db = tmp_path / "luminalix.db"
    datahub_db = tmp_path / "combined" / "luminalix.db"
    monkeypatch.setattr(reingestion, "_AGENT_DB", agent_db)
    monkeypatch.setattr(reingestion, "_DATAHUB_DB", datahub_db)

    def fake_build(script, tmp_path_, final):
        # Simulate the real build writing the temp DB before the swap.
        tmp_path_.parent.mkdir(parents=True, exist_ok=True)
        tmp_path_.write_bytes(b"sqlite-db")

    monkeypatch.setattr(reingestion, "_build_db", fake_build)

    result = reingestion.run_reingestion("covid")

    assert result["status"] == "complete"
    assert not (tmp_path / "luminalix.tmp").exists()
    assert not (tmp_path / "combined" / "luminalix.tmp").exists()

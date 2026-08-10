"""Unit tests for the ingestion source registry."""

from __future__ import annotations

from app.agent.ingestion_sources import (
    DATAHUB_RECIPE,
    INGESTION_SOURCES,
    REPO_ROOT,
)


def test_registry_defines_all_four_sources():
    assert list(INGESTION_SOURCES) == ["covid", "tb", "malaria", "influenza"]


def test_covid_is_a_live_url_source():
    source = INGESTION_SOURCES["covid"]
    assert source.input_type == "url"
    assert source.input.startswith("https://raw.githubusercontent.com/owid/")
    assert source.process_script == "data/ingestion/process_covid.py"
    assert source.process_arg is None


def test_tb_malaria_influenza_are_local_file_sources():
    for name in ("tb", "malaria", "influenza"):
        source = INGESTION_SOURCES[name]
        assert source.input_type == "file"
        assert source.input_path is not None
        assert source.input_path.suffix == ".csv"
        assert source.process_script == "data/ingestion/process_who_datasets.py"
        assert source.process_arg == name


def test_file_source_paths_exist_in_repo():
    for name in ("tb", "malaria", "influenza"):
        assert INGESTION_SOURCES[name].input_path.exists(), (
            f"missing manual download: {INGESTION_SOURCES[name].input_path}"
        )


def test_all_sources_share_the_sqlite_all_recipe():
    assert DATAHUB_RECIPE == "data/ingestion/recipe_sqlite_all_datasets.yml"


def test_repo_root_is_anchored():
    assert (REPO_ROOT / "data" / "ingestion").is_dir()

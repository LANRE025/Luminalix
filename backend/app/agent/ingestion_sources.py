"""ingestion_sources.py

Fixed, explicit registry of data sources that Luminalix can re-ingest.

This is a registry of what a user may choose to re-ingest — nothing here is
automatic. Every re-ingestion is triggered by an explicit user action: either
the POST /ingestion/run/{source} API endpoint or the "Reingest" button in the
frontend. There is no scheduler, no cron, no background timer anywhere in this
feature.

Each source maps to:
  * an input (a live URL to download, or an existing local file),
  * a process step that turns that input into data/processed/*.csv,
  * a DataHub CLI recipe to run afterwards (shared: recipe_sqlite_all_datasets.yml).

The shared "tail" pipeline that runs after every source's process step is
defined in reingestion.py and reuses the existing scripts in data/ingestion/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Anchor to the repo root (<repo>/backend/app/agent -> <repo>).
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class IngestionSource:
    """One user-triggerable ingestion source."""

    name: str
    display_name: str
    input_type: str  # "url" (downloaded) or "file" (existing local file)
    input: str  # URL, or path relative to the repo root
    process_script: str  # python script, relative to the repo root
    process_arg: str | None = None  # optional arg passed to the script (e.g. "tb")
    description: str = ""

    @property
    def input_path(self) -> Path | None:
        """Repo-root-anchored path for file-based sources (None for URLs)."""
        if self.input_type == "file":
            return REPO_ROOT / self.input
        return None

    @property
    def raw_filename(self) -> str:
        """Filename to use under data/raw when downloading a URL source."""
        return Path(self.input).name


INGESTION_SOURCES: dict[str, IngestionSource] = {
    "covid": IngestionSource(
        name="covid",
        display_name="COVID-19 (OWID)",
        input_type="url",
        input="https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv",
        process_script="data/ingestion/process_covid.py",
        description=(
            "OWID COVID-19 dataset (CC BY 4.0). Downloaded live from OWID's "
            "GitHub repository into data/raw/."
        ),
    ),
    "tb": IngestionSource(
        name="tb",
        display_name="Tuberculosis (OWID)",
        input_type="file",
        input="data/raw/tuberculosis_owid.csv",
        process_script="data/ingestion/process_who_datasets.py",
        process_arg="tb",
        description=(
            "WHO Global TB Report data via OWID (CC BY 4.0). Manual download "
            "required: https://ourworldindata.org/grapher/number-of-tuberculosis-cases"
        ),
    ),
    "malaria": IngestionSource(
        name="malaria",
        display_name="Malaria (OWID)",
        input_type="file",
        input="data/raw/malaria_owid.csv",
        process_script="data/ingestion/process_who_datasets.py",
        process_arg="malaria",
        description=(
            "WHO/OWID malaria case-count indicator only (CC BY 4.0). Manual "
            "download required: https://ourworldindata.org/grapher/incidence-of-malaria"
        ),
    ),
    "influenza": IngestionSource(
        name="influenza",
        display_name="Influenza (WHO FluNet)",
        input_type="file",
        input="data/raw/influenza_flunet.csv",
        process_script="data/ingestion/process_who_datasets.py",
        process_arg="influenza",
        description=(
            "WHO FluNet data (WHO sharing policy). Manual download required: "
            "https://www.who.int/tools/flunet"
        ),
    ),
}

# Shared DataHub CLI recipe every source re-ingests into after processing.
DATAHUB_RECIPE = "data/ingestion/recipe_sqlite_all_datasets.yml"

"""
combine_regional_survey_data.py

Merges all processed real datasets (COVID, and TB/Malaria/Influenza if you've
run process_who_datasets.py after manually downloading them) plus the
synthetic HIV/Ebola/Lassa fever data into one unified regional_survey_data
table — ready for loading into DataHub.

Run this AFTER:
    - data/ingestion/process_covid.py
    - data/ingestion/process_who_datasets.py (optional — skips gracefully if files missing)
    - data/ingestion/generate_synthetic_diseases.py

Output: data/combined/regional_survey_data.csv
"""

import pandas as pd
from pathlib import Path

PROCESSED_DIR = Path("data/processed")
SYNTHETIC_DIR = Path("data/synthetic")
OUT_PATH = Path("data/combined/regional_survey_data.csv")

EXPECTED_COLUMNS = ["region", "country", "disease", "last_survey_date", "reported_case_rate", "data_source"]


def load_if_exists(path: Path) -> pd.DataFrame:
    if path.exists():
        print(f"[include] {path}")
        return pd.read_csv(path)
    print(f"[skip] {path} not found")
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def main():
    frames = [
        load_if_exists(PROCESSED_DIR / "covid_survey_data.csv"),
        load_if_exists(PROCESSED_DIR / "tb_survey_data.csv"),
        load_if_exists(PROCESSED_DIR / "malaria_survey_data.csv"),
        load_if_exists(PROCESSED_DIR / "influenza_survey_data.csv"),
        load_if_exists(SYNTHETIC_DIR / "hiv_ebola_lassa_survey_data.csv"),
    ]

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[EXPECTED_COLUMNS]
    combined["last_survey_date"] = pd.to_datetime(combined["last_survey_date"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUT_PATH, index=False)

    print(f"\nWrote {len(combined)} total rows to {OUT_PATH}")
    print(f"Diseases included: {sorted(combined['disease'].unique().tolist())}")
    print(f"Countries included: {combined['country'].nunique()}")
    print(f"Real vs synthetic: {combined['data_source'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()

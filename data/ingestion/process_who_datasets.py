"""
process_who_datasets.py

Handles Tuberculosis, Influenza (FluNet), and Malaria — the three remaining
real datasets. Unlike COVID (mirrored on GitHub), these live only on
ourworldindata.org / who.int, which you'll need to download from directly
(this cannot be automated from a restricted sandbox, but works fine from
your own machine/browser).

============================================================
MANUAL DOWNLOAD STEPS (do this once, on your own machine)
============================================================

1. TUBERCULOSIS
   Go to: https://ourworldindata.org/grapher/number-of-tuberculosis-cases
   Click "Download" -> "Full Data (CSV)"
   Save as: data/raw/tuberculosis_owid.csv

2. MALARIA (case-count indicator ONLY — do not use the deaths/incidence
   indicators, which are IHME-sourced and NOT redistributable)
   Go to: https://ourworldindata.org/grapher/incidence-of-malaria
   Click "Download" -> "Full Data (CSV)"
   Save as: data/raw/malaria_owid.csv

3. INFLUENZA (FluNet)
   Go to: https://www.who.int/tools/flunet
   Use the FluNet data export tool (select "Global" or specific countries,
   export as CSV)
   Save as: data/raw/influenza_flunet.csv

   NOTE: FluNet's export format has changed over the years — inspect the
   downloaded file's columns before running this script, and adjust the
   COLUMN_MAP below if the column names don't match.

============================================================

Once all three files are in data/raw/, run this script:
    python3 data/ingestion/process_who_datasets.py

Output: data/processed/tb_survey_data.csv
        data/processed/malaria_survey_data.csv
        data/processed/influenza_survey_data.csv
"""

import pandas as pd
from pathlib import Path

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")

COUNTRIES_OF_INTEREST = [
    "Nigeria", "Kenya", "South Africa", "Democratic Republic of Congo",
    "Egypt", "India", "Indonesia", "Brazil", "Mexico", "United States",
    "United Kingdom", "France", "Philippines", "Bangladesh", "Ethiopia",
    "Uganda", "Ghana", "Pakistan", "Vietnam", "Peru",
]


def process_owid_standard_csv(filepath: Path, disease: str, value_col_hint: str) -> pd.DataFrame:
    """
    OWID's standard CSV export format uses columns: Entity, Code, Year, <indicator>.
    This handles that shape generically — value_col_hint is a substring to
    find the actual indicator column, since OWID's exact column name varies
    per dataset (e.g. "Tuberculosis (WHO estimated cases)" vs similar).
    """
    df = pd.read_csv(filepath)

    value_col = next((c for c in df.columns if value_col_hint.lower() in c.lower()), None)
    if value_col is None:
        raise ValueError(
            f"Could not find a column matching '{value_col_hint}' in {filepath}. "
            f"Available columns: {list(df.columns)}. Update value_col_hint accordingly."
        )

    df = df.rename(columns={"Entity": "region", "Year": "year"})
    df = df[df["region"].isin(COUNTRIES_OF_INTEREST)]
    df = df.dropna(subset=[value_col])

    latest = df.sort_values("year").groupby("region").tail(1)
    latest["country"] = latest["region"]
    latest["disease"] = disease
    latest["last_survey_date"] = pd.to_datetime(latest["year"].astype(str) + "-12-31")
    latest["reported_case_rate"] = latest[value_col]
    latest["data_source"] = "real"

    return latest[["region", "country", "disease", "last_survey_date", "reported_case_rate", "data_source"]]


def process_tb():
    path = RAW_DIR / "tuberculosis_owid.csv"
    if not path.exists():
        print(f"[skip] {path} not found — see download instructions at top of this file.")
        return
    result = process_owid_standard_csv(path, disease="Tuberculosis", value_col_hint="tuberculosis")
    out = OUT_DIR / "tb_survey_data.csv"
    result.to_csv(out, index=False)
    print(f"Wrote {len(result)} rows to {out}")


def process_malaria():
    path = RAW_DIR / "malaria_owid.csv"
    if not path.exists():
        print(f"[skip] {path} not found — see download instructions at top of this file.")
        return
    result = process_owid_standard_csv(path, disease="Malaria", value_col_hint="malaria")
    out = OUT_DIR / "malaria_survey_data.csv"
    result.to_csv(out, index=False)
    print(f"Wrote {len(result)} rows to {out}")


def process_influenza():
    path = RAW_DIR / "influenza_flunet.csv"
    if not path.exists():
        print(f"[skip] {path} not found — see download instructions at top of this file.")
        return
    # FluNet's export format varies; inspect columns and adjust here.
    df = pd.read_csv(path)
    print("FluNet columns found:", list(df.columns))
    print("Inspect the columns above and extend process_influenza() to map them "
          "to region/date/case-rate before this will produce output.")
    # Intentionally left as a manual step — FluNet's schema needs eyeballing
    # once you actually have the file, rather than guessing blindly here.


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    process_tb()
    process_malaria()
    process_influenza()

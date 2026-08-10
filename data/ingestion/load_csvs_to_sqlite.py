"""
load_csvs_to_sqlite.py

Loads the three combined/synthetic CSV datasets into a single SQLite
database file, so DataHub's sqlalchemy source can ingest them with
automatic schema inference.

Run from the project root:
    python data/ingestion/load_csvs_to_sqlite.py [--db <path>]

Produces:
    data/combined/luminalix.db
"""

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

# (csv path, table name)
DATASETS = [
    ("data/combined/regional_survey_data.csv", "regional_survey_data"),
    ("data/synthetic/hospital_admissions.csv", "hospital_admissions"),
    ("data/synthetic/resource_allocation.csv", "resource_allocation"),
]

DB_PATH = "data/combined/luminalix.db"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=DB_PATH,
        help="Output database path (default: data/combined/luminalix.db). Used by "
        "the manual re-ingestion flow to build into a temp file before an atomic swap.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)

    for csv_path, table_name in DATASETS:
        path = Path(csv_path)
        if not path.exists():
            print(f"[SKIP] {csv_path} not found — run the generator script for this dataset first.")
            continue

        df = pd.read_csv(path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"[OK] Loaded {len(df)} rows x {len(df.columns)} cols into table '{table_name}'")

    conn.close()
    print(f"\nDone. SQLite DB written to: {db_path.resolve()}")


if __name__ == "__main__":
    main()

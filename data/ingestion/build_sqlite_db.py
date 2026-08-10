"""
build_sqlite_db.py

Loads the three combined/synthetic CSVs into a local SQLite database.
This becomes the actual data layer the agent queries for region-level
values — DataHub's MCP server cannot serve row-level data (see
docs/mcp_capability_notes.md), so this fills that gap directly, the same
way a real DataHub deployment would point at an underlying warehouse.

Run after data/ingestion/run_pipeline.py.

Usage:
    python data/ingestion/build_sqlite_db.py [--db <path>]

Output: data/luminalix.db
"""

import argparse
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path("data/luminalix.db")

TABLES = {
    "regional_survey_data": "data/combined/regional_survey_data.csv",
    "hospital_admissions": "data/synthetic/hospital_admissions.csv",
    "resource_allocation": "data/synthetic/resource_allocation.csv",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=DB_PATH,
        help="Output database path (default: data/luminalix.db). Used by the "
        "manual re-ingestion flow to build into a temp file before an atomic swap.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    for table_name, csv_path in TABLES.items():
        path = Path(csv_path)
        if not path.exists():
            print(f"[skip] {csv_path} not found — run data/ingestion/run_pipeline.py first")
            continue
        df = pd.read_csv(path)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        print(f"[loaded] {table_name}: {len(df)} rows from {csv_path}")

    conn.close()
    print(f"\nDatabase ready at {db_path}")


if __name__ == "__main__":
    main()

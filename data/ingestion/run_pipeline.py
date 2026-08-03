"""
run_pipeline.py

Runs the full Luminalix data pipeline in the correct order. Safe to re-run —
each step either regenerates its output or skips gracefully if inputs are
missing (e.g. TB/malaria/influenza before you've done the manual downloads).

Usage:
    python3 data/ingestion/run_pipeline.py
"""

import subprocess
import sys
from pathlib import Path

STEPS = [
    "data/ingestion/process_covid.py",
    "data/ingestion/process_who_datasets.py",
    "data/ingestion/generate_synthetic_diseases.py",
    "data/ingestion/combine_regional_survey_data.py",
    "data/ingestion/generate_hospital_admissions.py",
    "data/ingestion/generate_resource_allocation.py",
]


def main():
    for step in STEPS:
        print(f"\n{'=' * 70}\nRunning: {step}\n{'=' * 70}")
        result = subprocess.run([sys.executable, step])
        if result.returncode != 0:
            print(f"\n[!] {step} failed with exit code {result.returncode}. Stopping.")
            sys.exit(result.returncode)

    print(f"\n{'=' * 70}\nPipeline complete. Outputs in data/combined/ and data/synthetic/\n{'=' * 70}")
    print("Next step: run the DataHub ingestion recipe(s) — see data/ingestion/load_to_datahub.yml")


if __name__ == "__main__":
    main()

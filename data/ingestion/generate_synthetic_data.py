"""Generate synthetic CSVs for the three datasets consumed by the agent.

Standalone script — no DataHub or network access needed. Run from the repo root:

    python data/ingestion/generate_synthetic_data.py [--output-dir data/synthetic]

Expected output schema (three files written under ``data/synthetic/``):

1. ``regional_survey_data.csv`` — official, authoritative but slow
   columns: region, country, last_survey_date (ISO date), disease_prevalence_per_100k (float), source

2. ``hospital_admissions.csv`` — fast-moving proxy signal
   columns: region, country, date (ISO date), admissions (int)

3. ``resource_allocation.csv`` — funding / staff / vaccine stock context
   columns: region, country, funding_usd (float), staff_count (int), vaccine_stock_doses (int)

Every region in ``hospital_admissions.csv`` and ``resource_allocation.csv`` also
appears in ``regional_survey_data.csv`` so ``region`` is a consistent join key
across all three datasets (requirement F3 of the PRD).

The generator models a realistic "blind spot": a couple of regions whose last
survey is long past, whose admissions are trending upward, and whose resource
allocation sits below the regional average.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SURVEY_FILE = "regional_survey_data.csv"
ADMISSIONS_FILE = "hospital_admissions.csv"
RESOURCES_FILE = "resource_allocation.csv"

# (region, country, survey_age_days, admissions_rise_factor, resource_factor)
# resource_factor < 1.0 means below the regional average.
REGIONS: list[tuple[str, str, int, float, float]] = [
    ("Region-West-Kenya", "Kenya", 42, 1.38, 0.80),
    ("Region-North-Nigeria", "Nigeria", 55, 1.45, 0.72),
    ("Region-Central-India", "India", 18, 1.05, 1.05),
    ("Region-South-Brazil", "Brazil", 25, 1.12, 1.00),
    ("Region-Luzon-Philippines", "Philippines", 47, 1.30, 0.88),
    ("Region-Sumatra-Indonesia", "Indonesia", 12, 1.02, 1.02),
    ("Region-Oromia-Ethiopia", "Ethiopia", 60, 1.50, 0.65),
    ("Region-Andean-Colombia", "Colombia", 20, 1.08, 1.10),
    ("Region-Delta-Vietnam", "Vietnam", 15, 1.03, 1.00),
    ("Region-North-Ghana", "Ghana", 39, 1.22, 0.90),
]

LOOKBACK_DAYS = 90  # admissions series length
BASE_ADMISSIONS = 120  # baseline daily admissions


def _write_survey(path: Path, today: date) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["region", "country", "last_survey_date", "disease_prevalence_per_100k", "source"])
        for region, country, survey_age, _, _ in REGIONS:
            survey_date = today - timedelta(days=survey_age)
            writer.writerow(
                [
                    region,
                    country,
                    survey_date.isoformat(),
                    round(random.uniform(10.0, 80.0), 2),
                    "ministry_of_health_survey",
                ]
            )


def _write_admissions(path: Path, today: date) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["region", "country", "date", "admissions"])
        for region, country, _, rise_factor, _ in REGIONS:
            for day in range(LOOKBACK_DAYS):
                progress = day / (LOOKBACK_DAYS - 1)
                level = BASE_ADMISSIONS * (1 + (rise_factor - 1) * progress)
                admissions = max(1, round(level + random.uniform(-8, 8)))
                writer.writerow([region, country, (today - timedelta(days=LOOKBACK_DAYS - 1 - day)).isoformat(), admissions])


def _write_resources(path: Path) -> None:
    avg_funding = 2_000_000.0
    avg_staff = 150
    avg_vaccine = 40_000
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["region", "country", "funding_usd", "staff_count", "vaccine_stock_doses"])
        for region, country, _, _, resource_factor in REGIONS:
            writer.writerow(
                [
                    region,
                    country,
                    round(avg_funding * resource_factor * random.uniform(0.95, 1.05), 0),
                    int(avg_staff * resource_factor),
                    int(avg_vaccine * resource_factor),
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic surveillance datasets.")
    parser.add_argument("--output-dir", default="data/synthetic", help="Directory to write CSVs into.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()

    _write_survey(output_dir / SURVEY_FILE, today)
    _write_admissions(output_dir / ADMISSIONS_FILE, today)
    _write_resources(output_dir / RESOURCES_FILE)

    print(f"Wrote synthetic data to {output_dir.resolve()}:")
    for name in (SURVEY_FILE, ADMISSIONS_FILE, RESOURCES_FILE):
        print(f"  - {name}")


if __name__ == "__main__":
    main()

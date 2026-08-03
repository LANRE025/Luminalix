"""
generate_resource_allocation.py

Generates the synthetic resource_allocation dataset — funding level, staff
count, and vaccine/supply stock per region, relative to a regional average.

Design intent: a subset of regions are deliberately UNDER-resourced despite
being in the "rising admissions trend" group from generate_hospital_admissions.py
— these are the ones that should end up classified as HIGH vulnerability
(stale survey + rising admissions + inadequate resources all aligning).

Input:  data/combined/regional_survey_data.csv
Output: data/synthetic/resource_allocation.csv
"""

import random
import pandas as pd
from pathlib import Path

random.seed(13)

IN_PATH = Path("data/combined/regional_survey_data.csv")
OUT_PATH = Path("data/synthetic/resource_allocation.csv")

# Regions deliberately under-resourced (funding/staff below regional average)
# — chosen to overlap with the rising-admissions regions so the full
# "stale + rising + under-resourced" story lines up for at least a few
# clear High-vulnerability cases in the demo.
UNDER_RESOURCED_REGIONS = {
    "North Kivu, DRC", "Ituri, DRC", "Ondo, Nigeria", "Bauchi, Nigeria",
}

# Regions with adequate resources despite a rising trend — these should
# land as Moderate rather than High, showing the model isn't just
# "rising trend = High" but genuinely weighs resource adequacy too.
ADEQUATELY_RESOURCED_DESPITE_RISING = {
    "United States", "South Africa", "Edo, Nigeria",
}


def generate_row(region: str, country: str) -> dict:
    if region in UNDER_RESOURCED_REGIONS:
        funding_level = random.uniform(20, 45)   # % of regional average
        staff_count = random.randint(15, 40)
        vaccine_stock = random.randint(50, 300)
    elif region in ADEQUATELY_RESOURCED_DESPITE_RISING:
        funding_level = random.uniform(90, 140)
        staff_count = random.randint(80, 200)
        vaccine_stock = random.randint(2000, 8000)
    else:
        funding_level = random.uniform(60, 110)
        staff_count = random.randint(40, 120)
        vaccine_stock = random.randint(500, 3000)

    return {
        "region": region,
        "country": country,
        "funding_level_pct_of_avg": round(funding_level, 1),
        "staff_count": staff_count,
        "vaccine_stock_units": vaccine_stock,
    }


def main():
    survey = pd.read_csv(IN_PATH)
    regions = survey[["region", "country"]].drop_duplicates()

    rows = [generate_row(r["region"], r["country"]) for _, r in regions.iterrows()]
    df = pd.DataFrame(rows)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df)} rows to {OUT_PATH}")
    print(df.sort_values("funding_level_pct_of_avg").to_string(index=False))


if __name__ == "__main__":
    main()

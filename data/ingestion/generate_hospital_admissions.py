"""
generate_hospital_admissions.py

Generates the synthetic hospital_admissions dataset — the "fast proxy
signal" in Luminalix's model. For each region present in the combined
regional_survey_data, this generates a 14-day daily admissions trend.

Design intent: a handful of regions are deliberately given a RISING trend
despite stale survey data, to demonstrate the core blind-spot scenario.
Everyone else gets a flat/normal trend as a baseline contrast.

Input:  data/combined/regional_survey_data.csv (run combine_regional_survey_data.py first)
Output: data/synthetic/hospital_admissions.csv
"""

import random
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path

random.seed(7)

IN_PATH = Path("data/combined/regional_survey_data.csv")
OUT_PATH = Path("data/synthetic/hospital_admissions.csv")
TODAY = datetime(2026, 8, 3)
LOOKBACK_DAYS = 14

# Regions to deliberately show a RISING admissions trend — these are the
# ones your agent should flag as high-vulnerability blind spots, regardless
# of what their survey data currently shows.
RISING_TREND_REGIONS = {
    "North Kivu, DRC", "Ituri, DRC", "Ondo, Nigeria", "Bauchi, Nigeria",
    "Edo, Nigeria", "United States", "South Africa",
}


def generate_trend(region: str, baseline: int) -> list[dict]:
    rows = []
    rising = region in RISING_TREND_REGIONS
    value = baseline

    for i in range(LOOKBACK_DAYS, 0, -1):
        date = TODAY - timedelta(days=i)
        if rising:
            # Roughly 3-6% compounding daily growth, plus noise
            value *= random.uniform(1.03, 1.06)
        else:
            # Flat with mild random noise
            value *= random.uniform(0.97, 1.03)

        rows.append({
            "region": region,
            "date": date.strftime("%Y-%m-%d"),
            "admission_count": max(0, round(value)),
        })

    return rows


def main():
    survey = pd.read_csv(IN_PATH)
    regions = survey[["region", "country"]].drop_duplicates()

    all_rows = []
    for _, row in regions.iterrows():
        baseline = random.randint(20, 200)
        all_rows.extend(generate_trend(row["region"], baseline))

    df = pd.DataFrame(all_rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df)} rows ({regions.shape[0]} regions x {LOOKBACK_DAYS} days) to {OUT_PATH}")

    # Quick sanity check: show trend direction per region
    summary = df.groupby("region").agg(
        first_value=("admission_count", "first"),
        last_value=("admission_count", "last"),
    )
    summary["pct_change"] = ((summary["last_value"] - summary["first_value"]) / summary["first_value"] * 100).round(1)
    print(summary.sort_values("pct_change", ascending=False).to_string())


if __name__ == "__main__":
    main()

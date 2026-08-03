"""
generate_synthetic_diseases.py

Generates fully synthetic regional_survey_data rows for HIV, Ebola, and
Lassa fever. These are synthetic BY DESIGN (not scraped/redistributed from
any real dataset) — chosen because reliable, redistributable structured
data wasn't available for these three (see Lesson 1 notes / licensing
research). Values are modeled on real, publicly-reported 2026 patterns for
narrative plausibility, not copied from any single source.

Output: data/synthetic/hiv_ebola_lassa_survey_data.csv
"""

import random
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path

random.seed(42)  # reproducible synthetic data

OUT_PATH = Path("data/synthetic/hiv_ebola_lassa_survey_data.csv")

TODAY = datetime(2026, 8, 3)


def days_ago(n: int) -> datetime:
    return TODAY - timedelta(days=n)


# ---------------------------------------------------------------------------
# HIV — synthetic, modeled loosely on real global distribution patterns
# (sub-Saharan Africa carries disproportionate burden; survey cycles for
# HIV prevalence surveys are typically annual-to-multi-year in many countries)
# ---------------------------------------------------------------------------
HIV_REGIONS = [
    ("South Africa", "South Africa", 12.5, 20),
    ("Kenya", "Kenya", 4.2, 45),
    ("Nigeria", "Nigeria", 1.3, 95),
    ("Uganda", "Uganda", 5.4, 60),
    ("Mozambique", "Mozambique", 11.8, 130),
    ("India", "India", 0.2, 200),
    ("Brazil", "Brazil", 0.5, 75),
    ("United States", "United States", 0.4, 15),
]

# ---------------------------------------------------------------------------
# Ebola — synthetic, modeled on the real 2026 Bundibugyo virus outbreak
# pattern in DRC/Uganda (declared PHEIC May 2026)
# ---------------------------------------------------------------------------
EBOLA_REGIONS = [
    ("North Kivu, DRC", "Democratic Republic of Congo", 340.0, 8),
    ("Ituri, DRC", "Democratic Republic of Congo", 210.0, 12),
    ("Kampala, Uganda", "Uganda", 45.0, 10),
    ("Kinshasa, DRC", "Democratic Republic of Congo", 5.0, 40),
]

# ---------------------------------------------------------------------------
# Lassa fever — synthetic, modeled on real 2026 NCDC-reported hotspot states
# (Ondo, Bauchi, Edo, Taraba accounted for ~85% of confirmed cases in 2026)
# ---------------------------------------------------------------------------
LASSA_REGIONS = [
    ("Ondo, Nigeria", "Nigeria", 28.0, 14),
    ("Bauchi, Nigeria", "Nigeria", 19.0, 21),
    ("Edo, Nigeria", "Nigeria", 22.0, 18),
    ("Taraba, Nigeria", "Nigeria", 15.0, 35),
    ("Benue, Nigeria", "Nigeria", 9.0, 50),
]


def build_rows():
    rows = []

    for region, country, rate, stale_days in HIV_REGIONS:
        rows.append({
            "region": region, "country": country, "disease": "HIV",
            "last_survey_date": days_ago(stale_days), "reported_case_rate": rate,
            "data_source": "synthetic",
        })

    for region, country, rate, stale_days in EBOLA_REGIONS:
        rows.append({
            "region": region, "country": country, "disease": "Ebola",
            "last_survey_date": days_ago(stale_days), "reported_case_rate": rate,
            "data_source": "synthetic",
        })

    for region, country, rate, stale_days in LASSA_REGIONS:
        rows.append({
            "region": region, "country": country, "disease": "Lassa fever",
            "last_survey_date": days_ago(stale_days), "reported_case_rate": rate,
            "data_source": "synthetic",
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = build_rows()
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df)} synthetic rows to {OUT_PATH}")
    print(df.to_string(index=False))

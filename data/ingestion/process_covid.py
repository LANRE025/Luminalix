"""
process_covid.py

Transforms the raw OWID COVID-19 CSV into Luminalix's regional_survey_data
schema: region, country, disease, last_survey_date, reported_case_rate,
data_source.

Input:  data/raw/owid-covid-data.csv
        (download from https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv)
Output: data/processed/covid_survey_data.csv

Attribution (include in your final data/raw/ATTRIBUTION.md):
Edouard Mathieu, Hannah Ritchie, Lucas Rodés-Guirao, Cameron Appel, Daniel Gavrilov,
Charlie Giattino, Joe Hasell, Bobbie Macdonald, Saloni Dattani, Diana Beltekian,
Esteban Ortiz-Ospina, and Max Roser (2020) - "COVID-19 Pandemic". Data adapted from
World Health Organization. Retrieved from Our World in Data
[https://ourworldindata.org/coronavirus]. Licensed under CC BY 4.0.
"""

import pandas as pd
from pathlib import Path

RAW_PATH = Path("data/raw/owid-covid-data.csv")
OUT_PATH = Path("data/processed/covid_survey_data.csv")

# A representative set of countries across regions/continents, so the demo
# shows global spread rather than just one part of the world.
COUNTRIES_OF_INTEREST = [
    "Nigeria", "Kenya", "South Africa", "Democratic Republic of Congo",
    "Egypt", "India", "Indonesia", "Brazil", "Mexico", "United States",
    "United Kingdom", "France", "Philippines", "Bangladesh", "Ethiopia",
    "Uganda", "Ghana", "Pakistan", "Vietnam", "Peru",
]


def process() -> pd.DataFrame:
    df = pd.read_csv(RAW_PATH, usecols=["location", "date", "new_cases_smoothed_per_million"])
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["location"].isin(COUNTRIES_OF_INTEREST)]
    df = df.dropna(subset=["new_cases_smoothed_per_million"])

    # Take the most recent reported data point per country as the
    # "survey" snapshot (this becomes last_survey_date / reported_case_rate).
    latest = (
        df.sort_values("date")
        .groupby("location")
        .tail(1)
        .rename(columns={
            "location": "region",
            "date": "last_survey_date",
            "new_cases_smoothed_per_million": "reported_case_rate",
        })
    )
    latest["country"] = latest["region"]
    latest["disease"] = "COVID-19"
    latest["data_source"] = "real"

    return latest[["region", "country", "disease", "last_survey_date", "reported_case_rate", "data_source"]]


if __name__ == "__main__":
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result = process()
    result.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(result)} rows to {OUT_PATH}")
    print(result.head(10).to_string(index=False))

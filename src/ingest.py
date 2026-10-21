"""Stream US_Accidents_March23.csv and keep only what fits on disk.

Outputs (data/processed/):
  national_sample.parquet  - 10% uniform random sample of all rows (national baselines)
  metro.parquet            - every row in the candidate metros (city-scale GeoAI)
  city_counts.csv          - accident counts per (State, City), for metro selection

Source: Kaggle sobhanmoosavi/us-accidents (March 2023 release). Streamed from a
byte-identical Hugging Face mirror because Kaggle needs credentials and the full
CSV (3.06 GB) does not fit on this machine.
# ponytail: set GEOCRASH_CSV=/path/to/US_Accidents_March23.csv to read a local Kaggle download instead.
"""
import os
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

URL = "https://huggingface.co/datasets/Sanjana7787/us-accidents-2016-2023/resolve/main/US_Accidents_March23.csv"
OUT = Path("data/processed")
SAMPLE_FRAC = 0.10
SEED = 878
CHUNK = 250_000
# Candidate metros from the project plan: Lincoln + Omaha first, larger metros as fallbacks.
METROS = [("NE", "Omaha"), ("NE", "Lincoln"), ("NE", "Bellevue"), ("NE", "Papillion"),
          ("NE", "La Vista"), ("IA", "Council Bluffs"), ("TX", "Dallas"), ("IL", "Chicago")]
DROP = ["Description", "Street", "Zipcode", "Country", "Airport_Code", "Weather_Timestamp",
        "End_Lat", "End_Lng", "Turning_Loop"]  # free text / constant / unused downstream


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    # pandas buffers a URL fully in RAM; an open urllib response streams instead.
    src = os.environ.get("GEOCRASH_CSV") or urllib.request.urlopen(URL)
    samples, metro, counts, n = [], [], [], 0
    for chunk in pd.read_csv(src, chunksize=CHUNK, low_memory=False):
        chunk = chunk.drop(columns=[c for c in DROP if c in chunk])
        n += len(chunk)
        counts.append(chunk.groupby(["State", "City"]).size())
        samples.append(chunk[rng.random(len(chunk)) < SAMPLE_FRAC])
        keys = pd.MultiIndex.from_arrays([chunk["State"], chunk["City"]])
        metro.append(chunk[keys.isin(METROS)])
        print(f"rows read: {n:,}", flush=True)

    pd.concat(samples).to_parquet(OUT / "national_sample.parquet", index=False)
    pd.concat(metro).to_parquet(OUT / "metro.parquet", index=False)
    (pd.concat(counts).groupby(level=[0, 1]).sum().sort_values(ascending=False)
       .rename("n").to_csv(OUT / "city_counts.csv"))
    print(f"done: {n:,} rows total")


if __name__ == "__main__":
    main()

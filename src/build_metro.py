"""Build the city-scale multimodal table: cleaned accidents + OSM GIS + NAIP imagery + neighborhood.

Reads data/processed/metro.parquet, writes data/processed/{gis,imagery,metro_features}.parquet.
GIS and imagery stages are cached; delete their parquet to recompute.
"""
from pathlib import Path

import pandas as pd

from src.features import clean, neighborhood
from src.gis import gis_features, locations
from src.imagery import image_features

DATA = Path("data/processed")
# Omaha–Council Bluffs metro + Lincoln (the project plan's first-choice study area).
STUDY = {("NE", "Omaha"): "Omaha", ("NE", "Bellevue"): "Omaha", ("NE", "Papillion"): "Omaha",
         ("NE", "La Vista"): "Omaha", ("IA", "Council Bluffs"): "Omaha", ("NE", "Lincoln"): "Lincoln"}


def cached(path: Path, build):
    if not path.exists():
        build().to_parquet(path, index=False)
    return pd.read_parquet(path)


def main():
    raw = pd.read_parquet(DATA / "metro.parquet")
    raw["area"] = [STUDY.get(k) for k in zip(raw["State"], raw["City"])]
    df = clean(raw.dropna(subset=["area"]))
    locs, df["loc_id"] = locations(df)
    area = df.groupby("loc_id")["area"].first().reindex(locs["loc_id"]).to_numpy()
    print(f"{len(df):,} accidents at {len(locs):,} unique locations", flush=True)

    gis = cached(DATA / "gis.parquet", lambda: gis_features(locs, pd.Series(area, index=locs.index)))
    img = cached(DATA / "imagery.parquet", lambda: image_features(locs))
    nb = neighborhood(df)
    out = (pd.concat([df, nb], axis=1)
             .merge(locs, on="loc_id").merge(gis, on="loc_id", how="left").merge(img, on="loc_id", how="left")
             .sort_values("Start_Time").reset_index(drop=True))
    out.to_parquet(DATA / "metro_features.parquet", index=False)
    print(f"metro_features: {out.shape}, with imagery: {out['naip_year'].notna().mean():.1%}")


if __name__ == "__main__":
    main()

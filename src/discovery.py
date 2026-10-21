"""RQ3/RQ4: unsupervised regimes, spatial hotspots, spatial outcome anomalies, imagery regimes, GIS map.

Writes outputs/tables/{regimes,hotspots,anomalies,image_regimes}.csv and outputs/maps/geocrashai_map.html.
"""
from pathlib import Path

import folium
import numpy as np
import pandas as pd
from folium.plugins import HeatMap
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, silhouette_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

from src.features import CATEGORICAL, TABULAR
from src.gis import GIS_COLUMNS
from src.imagery import IMG_SCALARS
from src.models import EMB, GRID_DEG, SEED, design

DATA, OUT = Path("data/processed"), Path("outputs")
K_RANGE = range(3, 9)
SIL_SAMPLE = 5000
HOTSPOT_MIN = 40
ANOMALY_Z, ANOMALY_MIN_N = 3.0, 15
CELL_DEG = {"500m": 0.0045, "1km": 0.009}
REGIME_COLS = (["road_km_per_km2_250", "intersections_per_km2_250", "building_frac_250", "parking_frac_250",
                "green_frac_250", "commercial_frac_250", "residential_frac_250", "road_class", "dist_highway_m",
                "hour", "is_night", "is_rush_hour", "is_weekend", "Visibility(mi)", "Precipitation(in)"]
               + IMG_SCALARS)


def standardized(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return StandardScaler().fit_transform(SimpleImputer(strategy="median").fit_transform(df[cols]))


def best_kmeans(X: np.ndarray) -> tuple[KMeans, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(X), min(SIL_SAMPLE, len(X)), replace=False)
    fits = {k: KMeans(k, n_init=10, random_state=SEED).fit(X) for k in K_RANGE}
    sil = pd.DataFrame({"k": list(fits), "silhouette": [silhouette_score(X[sample], f.labels_[sample]) for f in fits.values()]})
    return fits[int(sil.loc[sil.silhouette.idxmax(), "k"])], sil


def profile(df: pd.DataFrame, label: str, cols: list[str]) -> pd.DataFrame:
    g = df.groupby(label)
    return pd.concat([g.size().rename("n"), g["Severity"].mean().rename("mean_severity"),
                      g["is_severe"].mean().rename("severe_rate"), g["duration_min"].median().rename("median_duration_min"),
                      g[cols].mean()], axis=1).round(3)


def regimes(df):
    """RQ3: cluster tabular + GIS + imagery context (severity NOT used), then profile outcomes."""
    X = np.hstack([standardized(df, REGIME_COLS), PCA(8, random_state=SEED).fit_transform(standardized(df.fillna({c: 0 for c in EMB}), EMB))])
    km, sil = best_kmeans(X)
    df["regime"] = km.labels_
    sil.to_csv(OUT / "tables/regime_silhouette.csv", index=False)
    profile(df, "regime", REGIME_COLS).to_csv(OUT / "tables/regimes.csv")
    print(f"regimes: k={km.n_clusters}", flush=True)


def image_regimes(df):
    """Task 6: cluster imagery embeddings of unique locations only, then overlay outcomes."""
    locs = df.dropna(subset=["naip_year"]).drop_duplicates("loc_id")
    X = PCA(16, random_state=SEED).fit_transform(StandardScaler().fit_transform(locs[EMB]))
    km, sil = best_kmeans(X)
    df["image_regime"] = df["loc_id"].map(dict(zip(locs.loc_id, km.labels_)))
    sil.to_csv(OUT / "tables/image_regime_silhouette.csv", index=False)
    profile(df.dropna(subset=["image_regime"]), "image_regime", IMG_SCALARS + ["building_frac_250", "road_class"]).to_csv(
        OUT / "tables/image_regimes.csv")
    print(f"image regimes: k={km.n_clusters}", flush=True)


def hotspots(df):
    """Task 4: HDBSCAN on coordinates; separate 'frequent' from 'unusually severe'."""
    labels = HDBSCAN(min_cluster_size=HOTSPOT_MIN, metric="haversine").fit_predict(np.radians(df[["lat", "lng"]]))
    df["hotspot"] = labels
    h = df[df.hotspot >= 0].groupby("hotspot").agg(n=("ID", "size"), lat=("lat", "mean"), lng=("lng", "mean"),
                                                   mean_severity=("Severity", "mean"), severe_rate=("is_severe", "mean"))
    base = df.is_severe.mean()
    frequent, severe = h.n >= h.n.median(), h.severe_rate > base
    h["type"] = np.select([frequent & severe, frequent & ~severe, ~frequent & severe],
                          ["frequent+severe", "frequent, mostly minor", "infrequent but severe"], "neither")
    h.round(4).to_csv(OUT / "tables/hotspots.csv")
    print(f"hotspots: {len(h)} ({(df.hotspot >= 0).mean():.0%} of accidents)", flush=True)
    return h


def expected_severe(df) -> np.ndarray:
    """Out-of-fold P(severe) from context only (tabular+GIS+imagery; no location, no neighborhood history).

    Spatial-block CV, so a location's own outcomes never inform its expectation.
    """
    d = df.assign(**{f"img_pca_{k}": v for k, v in enumerate(
        PCA(16, random_state=SEED).fit_transform(df[EMB].fillna(0)).T)})
    X = design(d, TABULAR + GIS_COLUMNS + IMG_SCALARS + [f"img_pca_{k}" for k in range(16)])
    cell = (df.lat // GRID_DEG).astype(int).astype(str) + "_" + (df.lng // GRID_DEG).astype(int).astype(str)
    p = cross_val_predict(HistGradientBoostingClassifier(max_iter=300, random_state=SEED), X, df.is_severe,
                          groups=cell, cv=GroupKFold(5), method="predict_proba")[:, 1]
    print(f"expected-severity model OOF AUC: {roc_auc_score(df.is_severe, p):.3f}", flush=True)
    return p


def anomalies(df) -> pd.DataFrame:
    """Task 5: grid cells whose observed severe count exceeds context-expected count (Poisson-binomial z)."""
    df["p_severe"] = expected_severe(df)
    tables = []
    for name, deg in CELL_DEG.items():
        cell = (df.lat // deg).astype(int).astype(str) + "_" + (df.lng // deg).astype(int).astype(str)
        g = df.assign(cell=cell, var=df.p_severe * (1 - df.p_severe)).groupby("cell")
        t = pd.DataFrame({"n": g.size(), "observed": g.is_severe.sum(), "expected": g.p_severe.sum(),
                          "var": g["var"].sum(), "lat": g.lat.mean(), "lng": g.lng.mean()})
        t["z"] = (t.observed - t.expected) / np.sqrt(t["var"].clip(lower=1e-6))
        t["anomaly"] = (t.z >= ANOMALY_Z) & (t.n >= ANOMALY_MIN_N)
        tables.append(t.assign(scale=name).reset_index())
    out = pd.concat(tables)
    # Sensitivity: how many 500 m anomalies sit inside a 1 km cell that is also anomalous?
    a500, a1k = out[(out.scale == "500m") & out.anomaly], out[(out.scale == "1km") & out.anomaly]
    parent = (a500.lat // CELL_DEG["1km"]).astype(int).astype(str) + "_" + (a500.lng // CELL_DEG["1km"]).astype(int).astype(str)
    agree = parent.isin(a1k["cell"]).mean() if len(a500) else float("nan")
    print(f"anomalies: {len(a500)} @500m, {len(a1k)} @1km, 500m-in-1km agreement {agree:.0%}", flush=True)
    out.round(4).sort_values("z", ascending=False).to_csv(OUT / "tables/anomalies.csv", index=False)
    return out


def make_map(df, h, anom):
    m = folium.Map(location=[df.lat.median(), df.lng.median()], zoom_start=11,
                   tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", attr="Tiles © Esri")
    HeatMap(df[["lat", "lng"]].to_numpy().tolist(), radius=8, name="Accident density").add_to(m)
    sev = folium.FeatureGroup("Severe accidents (sev ≥ 3)", show=False).add_to(m)
    for r in df[df.is_severe == 1].itertuples():
        folium.CircleMarker([r.lat, r.lng], radius=2, color="#b2182b", fill=True, weight=0).add_to(sev)
    colors = {"frequent+severe": "#b2182b", "infrequent but severe": "#ef8a62",
              "frequent, mostly minor": "#67a9cf", "neither": "#999999"}
    hs = folium.FeatureGroup("Hotspots (HDBSCAN)").add_to(m)
    for i, r in h.iterrows():
        folium.CircleMarker([r.lat, r.lng], radius=4 + np.sqrt(r.n) / 2, color=colors[r.type], fill=True, fill_opacity=0.6,
                            tooltip=f"hotspot {i}: n={r.n}, severe rate {r.severe_rate:.0%} ({r.type})").add_to(hs)
    an = folium.FeatureGroup("Outcome anomalies (500 m, z ≥ 3)").add_to(m)
    deg = CELL_DEG["500m"]
    for r in anom[(anom.scale == "500m") & anom.anomaly].itertuples():
        la, lo = (int(v) * deg for v in r.cell.split("_"))
        folium.Rectangle([[la, lo], [la + deg, lo + deg]], color="#762a83", fill=True, fill_opacity=0.35,
                         tooltip=f"n={r.n}, observed severe {r.observed:.0f} vs expected {r.expected:.1f} (z={r.z:.1f})").add_to(an)
    rg = folium.FeatureGroup("Accident regimes (KMeans)", show=False).add_to(m)
    palette = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d", "#666666"]
    for r in df.sample(min(4000, len(df)), random_state=SEED).itertuples():
        folium.CircleMarker([r.lat, r.lng], radius=2, color=palette[r.regime % 8], fill=True, weight=0,
                            tooltip=f"regime {r.regime}").add_to(rg)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(OUT / "maps/geocrashai_map.html")


def main():
    for sub in ("tables", "maps"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA / "metro_features.parquet")
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    regimes(df)
    image_regimes(df)
    h = hotspots(df)
    anom = anomalies(df)
    make_map(df, h, anom)


if __name__ == "__main__":
    main()

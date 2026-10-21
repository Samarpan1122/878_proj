"""RQ1/RQ2/RQ5: severity classification + duration regression.

1. National baselines (10% sample, tabular only): logistic/ridge, random forest, gradient boosting.
2. Metro multimodal ablation A..E (+ GIS buffer-scale variants) under two protocols:
   - temporal holdout (train on earliest 80%, test on latest 20%)
   - spatial block CV (5 folds grouped by ~2 km grid cells) to control spatial autocorrelation
Writes outputs/tables/*.csv and outputs/figures/confusion_*.png.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import (HistGradientBoostingClassifier, HistGradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, balanced_accuracy_score, f1_score,
                             mean_absolute_error, r2_score, root_mean_squared_error)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features import CATEGORICAL, NEIGHBORHOOD, TABULAR, clean, temporal_split
from src.gis import BUFFERS_M, GIS_COLUMNS
from src.imagery import IMG_SCALARS

DATA, OUT = Path("data/processed"), Path("outputs")
SEED = 878
N_EMB_PCA = 32
GRID_DEG = 0.02  # ~2 km spatial CV blocks
EMB = [f"emb_{k}" for k in range(512)]


def design(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """One-hot categoricals; numeric stays as-is (NaN allowed for tree models)."""
    cats = [c for c in cols if c in CATEGORICAL or c == "State"]
    return pd.get_dummies(df[cols], columns=cats, dtype=float).astype(float)


def classifiers():
    return {
        "logistic": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                  LogisticRegression(max_iter=300, class_weight="balanced")),
        "random_forest": RandomForestClassifier(n_estimators=150, min_samples_leaf=5, max_samples=0.3,
                                                class_weight="balanced_subsample", n_jobs=-1, random_state=SEED),
        "grad_boost": HistGradientBoostingClassifier(class_weight="balanced", max_iter=300, random_state=SEED),
    }


def regressors():
    return {
        "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge()),
        "random_forest": RandomForestRegressor(n_estimators=150, min_samples_leaf=5, max_samples=0.3,
                                               n_jobs=-1, random_state=SEED),
        "grad_boost": HistGradientBoostingRegressor(max_iter=300, random_state=SEED),
    }


def cls_metrics(y, p) -> dict:
    return {"accuracy": accuracy_score(y, p), "balanced_accuracy": balanced_accuracy_score(y, p),
            "macro_f1": f1_score(y, p, average="macro")}


def reg_metrics(y_log, p_log) -> dict:
    y, p = np.expm1(y_log), np.expm1(p_log)
    return {"MAE_min": mean_absolute_error(y, p), "RMSE_min": root_mean_squared_error(y, p),
            "R2_log": r2_score(y_log, p_log)}


def national():
    df = clean(pd.read_parquet(DATA / "national_sample.parquet"))
    df["State"] = df["State"].astype("category")
    tr, te = temporal_split(df)
    rows = []
    X = design(df, TABULAR + ["State"])
    for name, m in classifiers().items():
        p = m.fit(X[tr], df.Severity[tr]).predict(X[te])
        rows.append({"task": "severity", "model": name, **cls_metrics(df.Severity[te], p)})
        print("national", rows[-1], flush=True)
        if name == "grad_boost":
            ConfusionMatrixDisplay.from_predictions(df.Severity[te], p, normalize="true", values_format=".2f")
            plt.title("National severity (grad boost, temporal test)")
            plt.savefig(OUT / "figures/confusion_national.png", dpi=120, bbox_inches="tight")
            plt.close()
    X = design(df, TABULAR + ["State", "Severity"])
    for name, m in regressors().items():
        p = m.fit(X[tr], df.log_duration[tr]).predict(X[te])
        rows.append({"task": "duration", "model": name, **reg_metrics(df.log_duration[te], p)})
        print("national", rows[-1], flush=True)
    pd.DataFrame(rows).assign(n_train=tr.sum(), n_test=te.sum()).to_csv(OUT / "tables/national_baselines.csv", index=False)


def with_emb_pca(df: pd.DataFrame, fit_mask: np.ndarray) -> pd.DataFrame:
    """Add img_pca_* columns; PCA fitted only on training rows that have imagery."""
    has = df["naip_year"].notna().to_numpy()
    pca = PCA(N_EMB_PCA, random_state=SEED).fit(df.loc[fit_mask & has, EMB])
    comp = np.full((len(df), N_EMB_PCA), np.nan)
    comp[has] = pca.transform(df.loc[has, EMB])
    return df.assign(**{f"img_pca_{k}": comp[:, k] for k in range(N_EMB_PCA)})


def feature_sets() -> dict[str, list[str]]:
    img = IMG_SCALARS + [f"img_pca_{k}" for k in range(N_EMB_PCA)]
    sets = {"A_tabular": TABULAR,
            "B_tabular+gis": TABULAR + GIS_COLUMNS,
            "C_imagery": img,
            "D_tabular+gis+imagery": TABULAR + GIS_COLUMNS + img,
            "E_D+neighborhood": TABULAR + GIS_COLUMNS + img + NEIGHBORHOOD}
    road = ["road_class", "maxspeed", "lanes", "dist_highway_m", "is_highway"]
    for r in BUFFERS_M:  # which spatial scale carries the GIS signal?
        sets[f"B_{r}m_only"] = TABULAR + [c for c in GIS_COLUMNS if c.endswith(f"_{r}")] + road
    return sets


def run_protocol(df, folds, target, make_model, metrics, extra=()):
    """Evaluate every feature set on the given (train_mask, test_mask) folds; mean over folds."""
    rows = []
    for name, cols in feature_sets().items():
        scores = []
        for tr, te in folds:
            d = with_emb_pca(df, tr)
            X = design(d, list(cols) + list(extra))
            p = make_model().fit(X[tr], d[target][tr]).predict(X[te])
            scores.append(metrics(d[target][te], p))
        rows.append({"features": name, **pd.DataFrame(scores).mean().to_dict()})
        print(target, rows[-1], flush=True)
    return pd.DataFrame(rows)


def metro():
    df = pd.read_parquet(DATA / "metro_features.parquet")
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    temporal = [temporal_split(df)]
    cell = (df.lat // GRID_DEG).astype(int).astype(str) + "_" + (df.lng // GRID_DEG).astype(int).astype(str)
    spatial = [(np.isin(np.arange(len(df)), a), np.isin(np.arange(len(df)), b))
               for a, b in GroupKFold(5).split(df, groups=cell)]
    clf = lambda: HistGradientBoostingClassifier(class_weight="balanced", max_iter=300, random_state=SEED)
    reg = lambda: HistGradientBoostingRegressor(max_iter=300, random_state=SEED)
    tables = []
    for proto, folds in [("temporal", temporal), ("spatial_cv", spatial)]:
        tables.append(run_protocol(df, folds, "Severity", clf, cls_metrics).assign(task="severity", protocol=proto))
        tables.append(run_protocol(df, folds, "log_duration", reg, reg_metrics, extra=["Severity"])
                      .assign(task="duration", protocol=proto))
    pd.concat(tables).to_csv(OUT / "tables/metro_ablation.csv", index=False)

    tr, te = temporal[0]
    d = with_emb_pca(df, tr)
    X = design(d, feature_sets()["E_D+neighborhood"])
    p = clf().fit(X[tr], d.Severity[tr]).predict(X[te])
    ConfusionMatrixDisplay.from_predictions(d.Severity[te], p, normalize="true", values_format=".2f")
    plt.title("Omaha metro severity (model E, temporal test)")
    plt.savefig(OUT / "figures/confusion_metro_E.png", dpi=120, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    for sub in ("tables", "figures"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    national()
    metro()

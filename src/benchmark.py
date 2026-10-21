"""Model leaderboard: every task x several models x full metric set, under two split protocols.

  future  - train on earliest 80% of crashes, test on latest 20% (honest: data drifts over time)
  random  - random 80/20 split (the usual Kaggle-style number; optimistic)
Writes outputs/tables/leaderboard.json (read by the website's Model scores page).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (HistGradientBoostingClassifier, HistGradientBoostingRegressor, RandomForestClassifier,
                              RandomForestRegressor)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score, calinski_harabasz_score,
                             davies_bouldin_score, f1_score, log_loss, mean_absolute_error, median_absolute_error,
                             r2_score, roc_auc_score, silhouette_score)
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import src.engine as E

OUT = Path("outputs/tables")
SEED, N_SAMPLE, N_CLUSTER, N_SIL = 878, 300_000, 60_000, 8_000
BASE = [c for c in E.SEV_FEATURES if not c.startswith(("src_", "enc_"))]


def splits(df):
    tr_f, te_f = E.temporal_split(df)
    r = np.random.default_rng(SEED).random(len(df)) < 0.8
    return {"future": (tr_f, te_f), "random": (r, ~r)}


def cls_models():
    return {
        "Majority class (baseline)": (DummyClassifier(strategy="most_frequent"), BASE),
        "Logistic regression": (make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=400)), BASE),
        "Random forest": (RandomForestClassifier(200, min_samples_leaf=5, max_samples=0.3, n_jobs=-1, random_state=SEED), BASE),
        "Gradient boosting": (HistGradientBoostingClassifier(max_iter=400, learning_rate=0.08, random_state=SEED), BASE),
        "Gradient boosting + feed + location history": (HistGradientBoostingClassifier(max_iter=400, learning_rate=0.08, random_state=SEED), E.SEV_FEATURES),
    }


def reg_models():
    return {
        "Median (baseline)": (None, BASE),
        "Ridge regression": (make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge()), BASE),
        "Random forest": (RandomForestRegressor(200, min_samples_leaf=5, max_samples=0.3, n_jobs=-1, random_state=SEED), BASE),
        "Gradient boosting": (HistGradientBoostingRegressor(max_iter=400, random_state=SEED), BASE),
        "Gradient boosting + feed + location history": (HistGradientBoostingRegressor(max_iter=400, random_state=SEED), E.SEV_FEATURES),
    }


def severity(df, X, tr, te):
    rows, y = [], df.Severity.to_numpy()
    for name, (m, cols) in cls_models().items():
        m.fit(X.loc[tr, cols], y[tr])
        proba = m.predict_proba(X.loc[te, cols])
        full = np.zeros((te.sum(), 4))
        for j, c in enumerate(m.classes_):
            full[:, int(c) - 1] = proba[:, j]
        p = full.argmax(1) + 1
        ps = full[:, 2:].sum(1)
        rows.append({"model": name, "Accuracy": accuracy_score(y[te], p), "Balanced accuracy": balanced_accuracy_score(y[te], p),
                     "Macro F1": f1_score(y[te], p, average="macro"), "Weighted F1": f1_score(y[te], p, average="weighted"),
                     "ROC-AUC (severe)": roc_auc_score(y[te] >= 3, ps), "PR-AUC (severe)": average_precision_score(y[te] >= 3, ps),
                     "Log loss": log_loss(y[te], np.clip(full, 1e-6, 1), labels=[1, 2, 3, 4])})
        print("  severity", rows[-1], flush=True)
    return rows


def duration(df, X, tr, te):
    rows, y, mins = [], df.log_duration.to_numpy(), df.duration_min.to_numpy()
    for name, (m, cols) in reg_models().items():
        Xs = X[cols].assign(Severity=df.Severity)
        p = np.full(te.sum(), np.median(y[tr])) if m is None else m.fit(Xs[tr], y[tr]).predict(Xs[te])
        pm = np.expm1(p)
        rows.append({"model": name, "MAE (min)": mean_absolute_error(mins[te], pm), "RMSE (min)": float(np.sqrt(np.mean((mins[te] - pm) ** 2))),
                     "Median AE (min)": median_absolute_error(mins[te], pm), "R² (log minutes)": r2_score(y[te], p),
                     "R² (minutes)": r2_score(mins[te], pm)})
        print("  duration", rows[-1], flush=True)
    return rows


def clustering(df, X):
    R = E.regime_frame(df, X)
    Z = StandardScaler().fit_transform(R)[np.random.default_rng(SEED).choice(len(R), N_CLUSTER, replace=False)]
    s = np.random.default_rng(SEED + 1).choice(len(Z), N_SIL, replace=False)
    rows = []
    for k in E.REGIME_K:
        for name, lab in (("KMeans", KMeans(k, n_init=5, random_state=SEED).fit_predict(Z)),
                          ("Gaussian mixture", GaussianMixture(k, covariance_type="diag", random_state=SEED).fit(Z).predict(Z))):
            rows.append({"model": f"{name} (k={k})", "Silhouette ↑": silhouette_score(Z[s], lab[s]),
                         "Davies–Bouldin ↓": davies_bouldin_score(Z, lab), "Calinski–Harabasz ↑": calinski_harabasz_score(Z, lab)})
    print("  clustering done", flush=True)
    return rows


def forecast(df):
    _, m = E.forecast(df)
    rows = [{"model": "Last month's value (baseline)", "MAE": m["MAE_last_value"]},
            {"model": "Same month last year (seasonal naive)", "MAE": m["MAE_seasonal_naive"], "R²": m["R2_seasonal_naive"], "WAPE": m["WAPE_seasonal_naive"]},
            {"model": "Gradient boosting (lags + seasonality)", "MAE": m["MAE_gbm"], "RMSE": m["RMSE_gbm"], "R²": m["R2_gbm"], "WAPE": m["WAPE_gbm"]}]
    return rows, m["cells"]


def main():
    full = E.rows()
    df = full.sample(N_SAMPLE, random_state=SEED).sort_values("Start_Time").reset_index(drop=True)
    board = {"n_rows": int(N_SAMPLE), "tasks": {}}
    for proto, (tr, te) in splits(df).items():
        print(proto, flush=True)
        X = E.matrix(df.join(E.oof_encode(df, tr)))
        board["tasks"].setdefault("severity", {})[proto] = severity(df, X, tr, te)
        board["tasks"].setdefault("duration", {})[proto] = duration(df, X, tr, te)
    board["tasks"]["clustering"] = clustering(df, E.matrix(df.join(E.oof_encode(df, np.ones(len(df), bool)))))
    fc, cells = forecast(full)
    board["tasks"]["forecast"] = {"future": fc, "cells": cells}
    metro = OUT / "metro_ablation.csv"
    if metro.exists():
        board["tasks"]["metro_ablation"] = pd.read_csv(metro).round(4).to_dict("records")
    (OUT / "leaderboard.json").write_text(json.dumps(board, indent=1, default=float))
    print("leaderboard written", flush=True)


if __name__ == "__main__":
    main()

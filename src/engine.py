"""National ML engine behind the web explorer. Trains, evaluates and saves:

  severity  - HistGradientBoosting classifier, P(severity 1..4) from location + time + weather + road context
  duration  - HistGradientBoosting regressor on log(minutes) + 10/90% quantile models for intervals
  regimes   - KMeans accident regimes (k by silhouette), auto-named from centroid deviations
  forecast  - global monthly count forecaster on a 0.25-degree grid panel (lags/seasonality),
              benchmarked against seasonal-naive and last-value baselines, with 10/90% quantile models
  oof       - out-of-fold P(severe) for every row (spatial-block CV) -> observed/expected risk index

Outputs: models/engine.joblib, data/processed/engine_rows.parquet, outputs/tables/engine_*.csv
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score, mean_absolute_error,
                             r2_score, roc_auc_score)
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

from src.features import ROAD_FLAGS, SEVERE, clean, temporal_split

DATA, OUT, MODELS = Path("data/processed"), Path("outputs/tables"), Path("models")
SEED, SAMPLE_WEIGHT = 878, 10
WEATHER = ["clear", "cloudy", "rain", "snow", "fog", "thunder", "other", "unknown"]
NUM = ["Start_Lat", "Start_Lng", "year", "month", "hour", "dow", "is_night", "is_weekend", "is_rush_hour",
       "Temperature(F)", "Visibility(mi)", "Precipitation(in)", "Wind_Speed(mph)", "Humidity(%)"]
SOURCES = ["Source1", "Source2", "Source3"]
ENC = ["enc_log_n", "enc_severe", "enc_log_duration"]
SEV_FEATURES = NUM + ROAD_FLAGS + [f"wx_{w}" for w in WEATHER] + [f"src_{x}" for x in SOURCES] + ENC
ENC_CELL_DEG = 0.05   # ~5 km location-history cells
ENC_PRIOR_N = 20      # shrink small cells toward the global rate
ENC_FOLDS = 5
GRID_DEG, FC_LAGS, FC_HORIZON = 0.25, (1, 2, 3, 6, 12), 12
REGIME_K = range(4, 9)
REGIME_FIT_N, SIL_N = 200_000, 8_000


def rows() -> pd.DataFrame:
    """National 10% sample (weight 10) + all rows of fully-kept metros (weight 1), cleaned."""
    nat, metro = pd.read_parquet(DATA / "national_sample.parquet"), pd.read_parquet(DATA / "metro.parquet")
    full = set(zip(metro.State, metro.City))
    nat = nat[[k not in full for k in zip(nat.State, nat.City)]].assign(w=SAMPLE_WEIGHT)
    df = clean(pd.concat([nat, metro.assign(w=1)], ignore_index=True))
    return df


def _cell(df: pd.DataFrame) -> pd.Series:
    return (df.Start_Lat // ENC_CELL_DEG).astype(int) * 100000 + (df.Start_Lng // ENC_CELL_DEG).astype(int)


def cell_stats(df: pd.DataFrame) -> dict:
    """Location history per ~5 km cell: volume, smoothed severe rate, smoothed mean log duration."""
    w = df.w
    g = pd.DataFrame({"cell": _cell(df), "w": w, "ws": w * df.is_severe, "wd": w * df.log_duration}).groupby("cell").sum()
    prior_s, prior_d = float(g.ws.sum() / g.w.sum()), float(g.wd.sum() / g.w.sum())
    return {"n": np.log1p(g.w).to_dict(), "severe": ((g.ws + ENC_PRIOR_N * prior_s) / (g.w + ENC_PRIOR_N)).to_dict(),
            "dur": ((g.wd + ENC_PRIOR_N * prior_d) / (g.w + ENC_PRIOR_N)).to_dict(), "prior_s": prior_s, "prior_d": prior_d}


def encode(df: pd.DataFrame, stats: dict) -> pd.DataFrame:
    c = _cell(df)
    return pd.DataFrame({"enc_log_n": c.map(stats["n"]).fillna(0.0), "enc_severe": c.map(stats["severe"]).fillna(stats["prior_s"]),
                         "enc_log_duration": c.map(stats["dur"]).fillna(stats["prior_d"])}, index=df.index)


def oof_encode(df: pd.DataFrame, mask: np.ndarray, seed: int = 878) -> pd.DataFrame:
    """Encodings for rows in `mask` computed out-of-fold (a row never sees its own label); others from all of `mask`."""
    out = pd.DataFrame(index=df.index, columns=ENC, dtype=float)
    idx = np.flatnonzero(mask)
    folds = np.random.default_rng(seed).integers(0, ENC_FOLDS, len(idx))
    for k in range(ENC_FOLDS):
        fit, apply = idx[folds != k], idx[folds == k]
        out.iloc[apply] = encode(df.iloc[apply], cell_stats(df.iloc[fit])).to_numpy()
    rest = np.flatnonzero(~mask)
    if len(rest):
        out.iloc[rest] = encode(df.iloc[rest], cell_stats(df.iloc[idx])).to_numpy()
    return out


def matrix(df: pd.DataFrame, stats: dict | None = None) -> pd.DataFrame:
    """Model matrix. Encodings come from df's enc_* columns, or from `stats` for new points (what-if rows)."""
    X = df.reindex(columns=NUM + ROAD_FLAGS).astype(float)
    for w in WEATHER:
        X[f"wx_{w}"] = (df["weather_group"].astype(str) == w).astype(float)
    src = df["Source"].astype(str) if "Source" in df else pd.Series("Source1", index=df.index)
    for x in SOURCES:
        X[f"src_{x}"] = (src == x).astype(float)
    enc = df[ENC] if all(c in df for c in ENC) else encode(df, stats)
    return pd.concat([X, enc.astype(float)], axis=1)[SEV_FEATURES]


def clf():
    return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.08, random_state=SEED)


def eval_matrix(df) -> tuple:
    """Temporal split; encodings for train rows out-of-fold, for test rows from train only (no leakage)."""
    tr, te = temporal_split(df)
    return tr, te, matrix(df.drop(columns=ENC, errors="ignore").join(oof_encode(df, tr)))


def severity(df, X) -> tuple:
    tr, te, X = eval_matrix(df)
    m = clf().fit(X[tr], df.Severity[tr], sample_weight=df.w[tr])
    p = m.predict(X[te])
    proba = m.predict_proba(X[te])
    sev_cols = list(m.classes_).index(3), list(m.classes_).index(4)
    from sklearn.metrics import average_precision_score, log_loss
    metrics = {"model": "severity_classifier", "accuracy": accuracy_score(df.Severity[te], p, sample_weight=df.w[te]),
               "weighted_f1": f1_score(df.Severity[te], p, average="weighted", sample_weight=df.w[te]),
               "log_loss": log_loss(df.Severity[te], proba, labels=m.classes_, sample_weight=df.w[te]),
               "pr_auc_severe": average_precision_score(df.is_severe[te], proba[:, sev_cols].sum(1), sample_weight=df.w[te]),
               "balanced_accuracy": balanced_accuracy_score(df.Severity[te], p, sample_weight=df.w[te]),
               "macro_f1": f1_score(df.Severity[te], p, average="macro", sample_weight=df.w[te]),
               "auc_severe": roc_auc_score(df.is_severe[te], proba[:, sev_cols].sum(1), sample_weight=df.w[te])}
    print(metrics, flush=True)
    final = clf().fit(matrix(df), df.Severity, sample_weight=df.w)
    return final, metrics


def duration(df, X) -> tuple:
    tr, te, Xe = eval_matrix(df)
    Xd = Xe.assign(Severity=df.Severity)
    reg = lambda **kw: HistGradientBoostingRegressor(max_iter=400, random_state=SEED, **kw)
    m = reg().fit(Xd[tr], df.log_duration[tr], sample_weight=df.w[tr])
    p = m.predict(Xd[te])
    metrics = {"model": "duration_regressor", "MAE_min": mean_absolute_error(df.duration_min[te], np.expm1(p)),
               "R2_log": r2_score(df.log_duration[te], p), "RMSE_min": float(np.sqrt(np.mean((df.duration_min[te] - np.expm1(p)) ** 2))),
               "MedAE_min": float(np.median(np.abs(df.duration_min[te] - np.expm1(p)))),
               "baseline_MAE_min": mean_absolute_error(df.duration_min[te], np.full(te.sum(), df.duration_min[tr].median()))}
    print(metrics, flush=True)
    Xf = X.assign(Severity=df.Severity)
    models = {q: reg(loss="quantile", quantile=q).fit(Xf, df.log_duration, sample_weight=df.w) for q in (0.1, 0.9)}
    models[0.5] = reg().fit(Xf, df.log_duration, sample_weight=df.w)
    return models, metrics


def oof_severe(df, X) -> np.ndarray:
    """Out-of-fold P(severe) with 1-degree spatial blocks: expectation never sees its own area's labels."""
    groups = (df.Start_Lat // 1).astype(int) * 1000 + (df.Start_Lng // 1).astype(int)
    X = X.drop(columns=ENC)  # context-only expectation: must not absorb the location's own history
    p = np.zeros(len(df))
    y = df.is_severe
    for tr, te in GroupKFold(3).split(X, groups=groups):
        m = HistGradientBoostingClassifier(max_iter=300, random_state=SEED).fit(X.iloc[tr], y.iloc[tr], sample_weight=df.w.iloc[tr])
        p[te] = m.predict_proba(X.iloc[te])[:, 1]
    print(f"OOF P(severe) AUC {roc_auc_score(y, p, sample_weight=df.w):.3f}", flush=True)
    return p


REGIME_COLS = ["hour_sin", "hour_cos", "is_night", "is_weekend", "Visibility(mi)", "Precipitation(in)",
               "Junction", "Traffic_Signal", "Crossing", "Stop", "log_duration", "Severity",
               "wx_rain", "wx_snow", "wx_fog", "wx_clear", "wx_cloudy"]
REGIME_LABELS = {"is_night": "night", "is_weekend": "weekend", "Junction": "junction", "Traffic_Signal": "signalized",
                 "Crossing": "crossing", "Stop": "stop-sign", "log_duration": "long-disruption", "Severity": "severe",
                 "wx_rain": "rain", "wx_snow": "snow", "wx_fog": "fog", "wx_clear": "clear-weather",
                 "wx_cloudy": "cloudy", "Precipitation(in)": "heavy-precip"}


def regime_frame(df, X) -> pd.DataFrame:
    R = X[[c for c in REGIME_COLS if c in X]].copy()
    R["hour_sin"], R["hour_cos"] = np.sin(2 * np.pi * df.hour / 24), np.cos(2 * np.pi * df.hour / 24)
    R["log_duration"], R["Severity"] = df.log_duration, df.Severity
    return R[REGIME_COLS].fillna(R[REGIME_COLS].median())


def regimes(df, X) -> tuple:
    from sklearn.metrics import silhouette_score
    R = regime_frame(df, X)
    scaler = StandardScaler().fit(R)
    Z = scaler.transform(R)
    rng = np.random.default_rng(SEED)
    fit_idx = rng.choice(len(Z), min(REGIME_FIT_N, len(Z)), replace=False)
    sil_idx = fit_idx[:SIL_N]
    fits = {k: KMeans(k, n_init=5, random_state=SEED).fit(Z[fit_idx]) for k in REGIME_K}
    sil = {k: silhouette_score(Z[sil_idx], f.predict(Z[sil_idx])) for k, f in fits.items()}
    k = max(sil, key=sil.get)
    km = fits[k]
    labels = km.predict(Z)
    names = []
    for c in km.cluster_centers_:
        top = [REGIME_COLS[i] for i in np.argsort(-c) if c[i] > 0.5 and REGIME_COLS[i] in REGIME_LABELS][:3]
        hour = (np.degrees(np.arctan2(c[0], c[1])) / 15) % 24 if np.hypot(c[0], c[1]) > 0.4 else None
        tag = [REGIME_LABELS[t] for t in top] or ["typical daytime"]
        names.append(" · ".join(tag + ([f"~{int(hour):02d}h"] if hour is not None else [])))
    prof = (df.assign(regime=labels).groupby("regime")
              .apply(lambda g: pd.Series({"share": g.w.sum() / df.w.sum(), "severe_rate": np.average(g.is_severe, weights=g.w),
                                          "median_duration_min": g.duration_min.median(), "night_share": np.average(g.is_night, weights=g.w)}),
                     include_groups=False))
    prof["name"] = names
    prof.round(4).to_csv(OUT / "engine_regimes.csv")
    pd.Series(sil, name="silhouette").to_csv(OUT / "engine_regime_silhouette.csv")
    print(f"regimes k={k}: {names}", flush=True)
    return {"scaler": scaler, "kmeans": km, "names": names}, labels


def fc_features(series: np.ndarray, month: np.ndarray) -> np.ndarray:
    """Row t uses only values up to t-1: log-lags, rolling means, calendar month."""
    s = np.log1p(series)
    cols = [np.r_[np.full(l, np.nan), s[:-l]] for l in FC_LAGS]
    for w in (3, 12):
        cols.append(pd.Series(s).shift(1).rolling(w, min_periods=1).mean().to_numpy())
    cols += [np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)]
    return np.column_stack(cols)


def forecast(df) -> tuple:
    months = pd.period_range("2016-03", "2023-02", freq="M")
    cell = (df.Start_Lat // GRID_DEG).astype(int).astype(str) + "_" + (df.Start_Lng // GRID_DEG).astype(int).astype(str)
    panel = (df.assign(cell=cell, m=df.Start_Time.dt.to_period("M")).groupby(["cell", "m"]).w.sum()
               .unstack(fill_value=0).reindex(columns=months, fill_value=0))
    panel = panel[panel.sum(1) >= 100]  # skip near-empty cells
    mon = months.month.to_numpy()
    X, y, is_test, lag1, lag12 = [], [], [], [], []
    for _, s in panel.iterrows():
        v = s.to_numpy(float)
        F = fc_features(v, mon)
        X.append(F[12:]); y.append(v[12:]); is_test.append(np.arange(12, len(v)) >= len(v) - FC_HORIZON)
        lag1.append(v[11:-1]); lag12.append(v[:-12])
    X, y, is_test = np.vstack(X), np.concatenate(y), np.concatenate(is_test)
    lag1, lag12 = np.concatenate(lag1), np.concatenate(lag12)
    reg = lambda **kw: HistGradientBoostingRegressor(max_iter=300, random_state=SEED, **kw)
    m = reg().fit(X[~is_test], np.log1p(y[~is_test]))
    pred = np.expm1(m.predict(X[is_test]))  # one-step-ahead on the held-out last 12 months
    yt = y[is_test]
    metrics = {"model": "monthly_forecaster", "cells": len(panel), "MAE_gbm": mean_absolute_error(yt, pred),
               "MAE_seasonal_naive": mean_absolute_error(yt, lag12[is_test]),
               "MAE_last_value": mean_absolute_error(yt, lag1[is_test]), "RMSE_gbm": float(np.sqrt(np.mean((yt - pred) ** 2))),
               "R2_gbm": r2_score(yt, pred), "R2_seasonal_naive": r2_score(yt, lag12[is_test]),
               "WAPE_gbm": float(np.abs(yt - pred).sum() / yt.sum()), "WAPE_seasonal_naive": float(np.abs(yt - lag12[is_test]).sum() / yt.sum())}
    print(metrics, flush=True)
    models = {0.5: reg().fit(X, np.log1p(y))}
    models.update({q: reg(loss="quantile", quantile=q).fit(X, np.log1p(y)) for q in (0.1, 0.9)})
    return models, metrics


def main():
    MODELS.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    df = rows()
    df = df.join(oof_encode(df, np.ones(len(df), bool)))
    X = matrix(df)
    print(f"engine rows: {len(df):,}", flush=True)
    sev_model, m1 = severity(df, X)
    dur_models, m2 = duration(df, X)
    fc_models, m3 = forecast(df)
    reg_model, labels = regimes(df, X)
    df["regime"] = labels
    df["p_severe"] = oof_severe(df, X)
    pd.DataFrame([m1, m2, m3]).round(4).to_csv(OUT / "engine_metrics.csv", index=False)
    joblib.dump({"cell_stats": cell_stats(df), "severity": sev_model, "duration": dur_models, "forecast": fc_models, "regimes": reg_model,
                 "metrics": [m1, m2, m3]}, MODELS / "engine.joblib", compress=3)
    keep = ["Start_Lat", "Start_Lng", "Start_Time", "Severity", "is_severe", "duration_min", "is_night", "is_rush_hour",
            "hour", "dow", "month", "year", "weather_group", "City", "State", "w", "regime", "p_severe", "log_duration",
            "Temperature(F)", "Visibility(mi)", "Precipitation(in)", "Wind_Speed(mph)", "Humidity(%)", "Source"] + ENC + ROAD_FLAGS
    df[keep].to_parquet(DATA / "engine_rows.parquet", index=False)
    print("engine saved", flush=True)


if __name__ == "__main__":
    main()

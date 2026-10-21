"""Precompute every plot for the Explore-data (EDA) and Model-plots pages.

Writes outputs/tables/eda.json and outputs/tables/model_plots.json. Run after src.engine.
Sample: 300k crashes (national sample weight respected in counts); future split = earliest 80% train / latest 20% test.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import (HistGradientBoostingClassifier, HistGradientBoostingRegressor, IsolationForest,
                              RandomForestClassifier, RandomForestRegressor)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (confusion_matrix, precision_recall_curve, precision_recall_fscore_support, roc_curve,
                             silhouette_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import src.engine as E
from src.features import ROAD_FLAGS

OUT = Path("outputs/tables")
SEED, N, SCATTER_N, CURVE_PTS = 878, 300_000, 2500, 120
NUMERIC = ["Temperature(F)", "Humidity(%)", "Pressure(in)", "Visibility(mi)", "Wind_Speed(mph)", "Precipitation(in)"]
BASE = [c for c in E.SEV_FEATURES if not c.startswith(("src_", "enc_"))]
rng = np.random.default_rng(SEED)


def r(v, d=4):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), d)


def wcount(d, key):
    return {str(k): r(v, 1) for k, v in d.w.groupby(key, observed=True).sum().items()}


def srate(d, key, min_rows=200):
    g = d.groupby(key, observed=True)
    return {str(k): r(np.average(x.is_severe, weights=x.w)) for k, x in g if len(x) >= min_rows}


def hist(v, bins, w=None):
    c, e = np.histogram(v, bins=bins, weights=w)
    return {"edges": [r(x, 3) for x in e], "counts": [r(x, 1) for x in c]}


def sample(d, n=SCATTER_N):
    return d.sample(min(n, len(d)), random_state=SEED)


# ---------------------------------------------------------------- EDA
def eda(full: pd.DataFrame, raw_cols: list[str], missing: dict) -> dict:
    d = full
    s = sample(d)
    num = d[NUMERIC + ["duration_min", "Severity", "hour"]].copy()
    num["log_duration"] = np.log1p(num.pop("duration_min"))
    corr = num.sample(min(200_000, len(num)), random_state=SEED).corr(method="spearman").round(3)
    grid = np.zeros((7, 24))
    np.add.at(grid, (d.dow.to_numpy(), d.hour.to_numpy()), d.w.to_numpy())
    q = d.groupby("Severity").duration_min.quantile([0.1, 0.25, 0.5, 0.75, 0.9]).unstack()
    iqr = lambda x: (x.quantile(0.25) - 1.5 * (x.quantile(0.75) - x.quantile(0.25)), x.quantile(0.75) + 1.5 * (x.quantile(0.75) - x.quantile(0.25)))
    outl = {}
    for c in NUMERIC + ["duration_min"]:
        x = d[c].dropna()
        lo, hi = iqr(x)
        outl[c] = {"n": int(len(x)), "low": int((x < lo).sum()), "high": int((x > hi).sum()), "lo": r(lo, 2), "hi": r(hi, 2),
                   "min": r(x.min(), 2), "p1": r(x.quantile(0.01), 2), "median": r(x.median(), 2), "p99": r(x.quantile(0.99), 2), "max": r(x.max(), 2)}
    iso_cols = ["hour", "Temperature(F)", "Visibility(mi)", "Wind_Speed(mph)", "Precipitation(in)", "log_duration", "Severity"]
    Xi = d[iso_cols].sample(60_000, random_state=SEED)
    Xi = Xi.fillna(Xi.median())
    iso = IsolationForest(contamination=0.01, random_state=SEED).fit(Xi)
    score = -iso.score_samples(Xi)
    top = Xi.assign(score=score).nlargest(12, "score")
    si = Xi.assign(score=score, out=iso.predict(Xi) == -1).sample(2500, random_state=SEED)
    state = d.groupby("State")
    states = pd.DataFrame({"n": state.w.sum(), "severe": state.apply(lambda x: np.average(x.is_severe, weights=x.w), include_groups=False),
                           "dur": state.duration_min.median()}).sort_values("n", ascending=False)
    city = d.groupby(["City", "State"]).w.sum().nlargest(15)
    roads = [{"flag": f.replace("_", " "), "share": r(np.average(d[f], weights=d.w)),
              "severe_with": r(np.average(d.is_severe[d[f] == 1], weights=d.w[d[f] == 1])) if (d[f] == 1).sum() > 100 else None,
              "severe_without": r(np.average(d.is_severe[d[f] == 0], weights=d.w[d[f] == 0]))} for f in ROAD_FLAGS]
    return {
        "overview": {"rows_represented": r(d.w.sum(), 0), "rows_loaded": len(d), "columns": raw_cols, "start": str(d.Start_Time.min())[:10],
                     "end": str(d.Start_Time.max())[:10], "states": int(d.State.nunique()), "cities": int(d.City.nunique()), "missing": missing},
        "severity": wcount(d, d.Severity), "severity_by_source": {src: wcount(x, x.Severity) for src, x in d.groupby("Source", observed=True)},
        "duration_hist": hist(np.log10(d.duration_min), np.linspace(0, 4.1, 42), d.w),
        "duration_by_severity": {str(k): [r(v, 1) for v in row] for k, row in q.iterrows()},
        "by_year": wcount(d, d.year), "severe_by_year": srate(d, d.year), "by_month": wcount(d, d.month), "by_dow": wcount(d, d.dow),
        "by_hour": wcount(d, d.hour), "severe_by_hour": srate(d, d.hour), "hour_dow": grid.round(0).tolist(),
        "weather": wcount(d, d.weather_group), "severe_by_weather": srate(d, d.weather_group),
        "day_night": {"share_night": r(np.average(d.is_night, weights=d.w)), "severe_day": r(np.average(d.is_severe[d.is_night == 0], weights=d.w[d.is_night == 0])),
                      "severe_night": r(np.average(d.is_severe[d.is_night == 1], weights=d.w[d.is_night == 1]))},
        "temp_hist": hist(d["Temperature(F)"].clip(-20, 115).dropna(), np.linspace(-20, 115, 46)),
        "vis_hist": hist(d["Visibility(mi)"].clip(0, 12).dropna(), np.linspace(0, 12, 25)),
        "humidity_hist": hist(d["Humidity(%)"].dropna(), np.linspace(0, 100, 26)),
        "wind_hist": hist(d["Wind_Speed(mph)"].clip(0, 50).dropna(), np.linspace(0, 50, 26)),
        "severe_by_temp": srate(d, pd.cut(d["Temperature(F)"], [-100, 0, 20, 32, 45, 60, 75, 90, 200])),
        "severe_by_vis": srate(d, pd.cut(d["Visibility(mi)"], [-1, 0.5, 1, 2, 5, 9.9, 100])),
        "scatter_temp_humidity": [[r(a, 1), r(b, 1), int(c)] for a, b, c in s[["Temperature(F)", "Humidity(%)", "Severity"]].dropna().to_numpy()],
        "scatter_vis_duration": [[r(a, 2), r(b, 1), int(c)] for a, b, c in s[["Visibility(mi)", "duration_min", "Severity"]].dropna().to_numpy()],
        "scatter_wind_duration": [[r(a, 1), r(b, 1), int(c)] for a, b, c in s[["Wind_Speed(mph)", "duration_min", "Severity"]].dropna().to_numpy()],
        "scatter_hour_duration": [[r(a + rng.uniform(-0.4, 0.4), 2), r(b, 1), int(c)] for a, b, c in s[["hour", "duration_min", "Severity"]].to_numpy()],
        "geo_points": [[r(a, 3), r(b, 3), int(c)] for a, b, c in sample(d, 8000)[["Start_Lat", "Start_Lng", "Severity"]].to_numpy()],
        "corr": {"cols": list(corr.columns), "matrix": corr.to_numpy().tolist()},
        "roads": roads,
        "states": [{"state": k, "n": r(v.n, 0), "severe": r(v.severe), "median_duration": r(v.dur, 1)} for k, v in states.head(20).iterrows()],
        "cities": [{"city": f"{c}, {st}", "n": r(v, 0)} for (c, st), v in city.items()],
        "outliers_iqr": outl,
        "isolation": {"features": iso_cols, "rate": 0.01, "top": top.round(2).to_dict("records"),
                      "scatter": [[r(a, 1), r(b, 3), bool(o)] for a, b, o in si[["Temperature(F)", "log_duration", "out"]].to_numpy()]},
    }


# ---------------------------------------------------------------- model plots
def curve(x, y, n=CURVE_PTS):
    idx = np.unique(np.linspace(0, len(x) - 1, n).astype(int))
    return [[r(x[i]), r(y[i])] for i in idx]


def classification(df, X, tr, te):
    y = df.Severity.to_numpy()
    models = {"Logistic regression": (make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=400)), BASE),
              "Random forest": (RandomForestClassifier(200, min_samples_leaf=5, max_samples=0.3, n_jobs=-1, random_state=SEED), BASE),
              "Gradient boosting": (HistGradientBoostingClassifier(max_iter=400, learning_rate=0.08, random_state=SEED), BASE),
              "Gradient boosting + feed + history": (HistGradientBoostingClassifier(max_iter=400, learning_rate=0.08, random_state=SEED), E.SEV_FEATURES)}
    out = {"roc": {}, "pr": {}, "calibration": {}, "confusion": {}, "per_class": {}}
    ys = (y[te] >= 3).astype(int)
    for name, (m, cols) in models.items():
        m.fit(X.loc[tr, cols], y[tr])
        P = np.zeros((te.sum(), 4))
        for j, c in enumerate(m.classes_):
            P[:, int(c) - 1] = m.predict_proba(X.loc[te, cols])[:, j]
        ps = P[:, 2:].sum(1)
        fpr, tpr, _ = roc_curve(ys, ps)
        pr, rc, _ = precision_recall_curve(ys, ps)
        out["roc"][name] = curve(fpr, tpr)
        out["pr"][name] = curve(rc[::-1], pr[::-1])
        bins = np.quantile(ps, np.linspace(0, 1, 11))
        b = np.clip(np.searchsorted(bins, ps, side="right") - 1, 0, 9)
        out["calibration"][name] = [[r(ps[b == i].mean()), r(ys[b == i].mean())] for i in range(10) if (b == i).any()]
        pred = P.argmax(1) + 1
        cm = confusion_matrix(y[te], pred, labels=[1, 2, 3, 4], normalize="true")
        out["confusion"][name] = np.nan_to_num(cm).round(3).tolist()
        p_, r_, f_, s_ = precision_recall_fscore_support(y[te], pred, labels=[1, 2, 3, 4], zero_division=0)
        out["per_class"][name] = {"precision": p_.round(3).tolist(), "recall": r_.round(3).tolist(), "f1": f_.round(3).tolist(), "support": s_.tolist()}
        print("  cls", name, flush=True)
    return out


def regression(df, X, tr, te):
    y, mins = df.log_duration.to_numpy(), df.duration_min.to_numpy()
    models = {"Ridge regression": (make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge()), BASE),
              "Random forest": (RandomForestRegressor(200, min_samples_leaf=5, max_samples=0.3, n_jobs=-1, random_state=SEED), BASE),
              "Gradient boosting": (HistGradientBoostingRegressor(max_iter=400, random_state=SEED), BASE),
              "Gradient boosting + feed + history": (HistGradientBoostingRegressor(max_iter=400, random_state=SEED), E.SEV_FEATURES)}
    out = {"scatter": {}, "residual_hist": {}, "mae_by_severity": {}}
    idx = rng.choice(np.flatnonzero(te), SCATTER_N, replace=False)
    for name, (m, cols) in models.items():
        Xs = X[cols].assign(Severity=df.Severity)
        m.fit(Xs[tr], y[tr])
        p = m.predict(Xs[te])
        pt = pd.Series(p, index=np.flatnonzero(te))
        out["scatter"][name] = [[r(np.expm1(pt[i]), 1), r(mins[i], 1), int(df.Severity.iat[i])] for i in idx]
        res = y[te] - p
        out["residual_hist"][name] = hist(np.clip(res, -4, 4), np.linspace(-4, 4, 41))
        out["mae_by_severity"][name] = {str(s): r(np.abs(mins[te][df.Severity[te] == s] - np.expm1(p[df.Severity[te].to_numpy() == s])).mean(), 1)
                                        for s in (1, 2, 3, 4) if (df.Severity[te] == s).sum() > 20}
        if name.endswith("history"):
            out["residual_vs_pred"] = [[r(pt[i], 3), r(y[i] - pt[i], 3)] for i in idx]
            q = {a: HistGradientBoostingRegressor(loss="quantile", quantile=a, max_iter=300, random_state=SEED).fit(Xs[tr], y[tr]).predict(Xs[te]) for a in (0.1, 0.9)}
            out["interval_coverage"] = r(((y[te] >= q[0.1]) & (y[te] <= q[0.9])).mean())
            out["interval_width_median_min"] = r(np.median(np.expm1(q[0.9]) - np.expm1(q[0.1])), 1)
        print("  reg", name, flush=True)
    return out


def timeseries(full):
    months = pd.period_range("2016-03", "2023-02", freq="M")
    cell = (full.Start_Lat // E.GRID_DEG).astype(int).astype(str) + "_" + (full.Start_Lng // E.GRID_DEG).astype(int).astype(str)
    panel = (full.assign(cell=cell, m=full.Start_Time.dt.to_period("M")).groupby(["cell", "m"]).w.sum().unstack(fill_value=0)
             .reindex(columns=months, fill_value=0))
    panel = panel[panel.sum(1) >= 100]
    mon = months.month.to_numpy()
    Xs, ys, tests, keys = [], [], [], []
    for k, s in panel.iterrows():
        v = s.to_numpy(float)
        F = E.fc_features(v, mon)
        Xs.append(F[12:]); ys.append(v[12:]); tests.append(np.arange(12, len(v)) >= len(v) - E.FC_HORIZON); keys += [k] * (len(v) - 12)
    X, y, te, keys = np.vstack(Xs), np.concatenate(ys), np.concatenate(tests), np.array(keys)
    m = HistGradientBoostingRegressor(max_iter=300, random_state=SEED).fit(X[~te], np.log1p(y[~te]))
    pred = np.expm1(m.predict(X[te]))
    test_keys, yt = keys[te], y[te]
    lag12 = X[te][:, E.FC_LAGS.index(12)]
    naive = np.expm1(lag12)
    top = panel.sum(1).nlargest(6).index
    lat = lambda k: round((int(k.split("_")[0]) + 0.5) * E.GRID_DEG, 2)
    lng = lambda k: round((int(k.split("_")[1]) + 0.5) * E.GRID_DEG, 2)
    series = []
    for k in top:
        sel = test_keys == k
        series.append({"cell": f"{lat(k)}, {lng(k)}", "months": [str(p) for p in months], "actual": panel.loc[k].round(1).tolist(),
                       "test_months": [str(p) for p in months[-E.FC_HORIZON:]], "gbm": pred[sel].round(1).tolist(), "naive": naive[sel].round(1).tolist()})
    test_months = [str(p) for p in months[-E.FC_HORIZON:]]
    nat_act = [r(yt[np.arange(len(yt)) % E.FC_HORIZON == i].sum(), 0) for i in range(E.FC_HORIZON)]
    nat_gbm = [r(pred[np.arange(len(pred)) % E.FC_HORIZON == i].sum(), 0) for i in range(E.FC_HORIZON)]
    nat_nv = [r(naive[np.arange(len(naive)) % E.FC_HORIZON == i].sum(), 0) for i in range(E.FC_HORIZON)]
    nat_hist = panel.sum(0).round(0).tolist()
    print("  ts done", flush=True)
    return {"series": series, "national": {"months": [str(p) for p in months], "actual": nat_hist, "test_months": test_months,
                                           "test_actual": nat_act, "gbm": nat_gbm, "naive": nat_nv},
            "error_hist": {"gbm": hist(np.clip(pred - yt, -60, 60), np.linspace(-60, 60, 41)), "naive": hist(np.clip(naive - yt, -60, 60), np.linspace(-60, 60, 41))},
            "scatter": [[r(a, 1), r(b, 1)] for a, b in zip(pred[:: max(1, len(pred) // 2500)], yt[:: max(1, len(yt) // 2500)])]}


def clustering(df, X):
    R = E.regime_frame(df, X)
    Z = StandardScaler().fit_transform(R)
    zi = rng.choice(len(Z), 60_000, replace=False)
    Zs = Z[zi]
    sil_idx = rng.choice(len(Zs), 6000, replace=False)
    elbow, fits = [], {}
    for k in range(2, 11):
        km = KMeans(k, n_init=5, random_state=SEED).fit(Zs)
        fits[k] = km
        elbow.append({"k": k, "inertia": r(km.inertia_, 0), "silhouette": r(silhouette_score(Zs[sil_idx], km.labels_[sil_idx]))})
    best = max(range(4, 9), key=lambda k: [e for e in elbow if e["k"] == k][0]["silhouette"])
    km = fits[best]
    pca = PCA(2, random_state=SEED).fit(Zs)
    pts = rng.choice(len(Zs), 3500, replace=False)
    xy = pca.transform(Zs[pts])
    lab = km.labels_
    sub = df.iloc[zi]
    profile = pd.DataFrame(km.cluster_centers_, columns=R.columns).round(2)
    sizes = pd.Series(lab).value_counts(normalize=True).sort_index()
    sev = pd.Series(sub.is_severe.to_numpy()).groupby(lab).mean()
    durm = pd.Series(sub.duration_min.to_numpy()).groupby(lab).median()
    print("  clustering done", flush=True)
    return {"elbow": elbow, "k": best, "pca_scatter": [[r(a, 3), r(b, 3), int(c)] for (a, b), c in zip(xy, lab[pts])],
            "pca_var": [r(v) for v in pca.explained_variance_ratio_], "profile": {"features": list(R.columns), "centers": profile.to_numpy().tolist()},
            "sizes": sizes.round(4).tolist(), "severe_rate": sev.round(4).tolist(), "median_duration": durm.round(1).tolist()}


def main():
    full = E.rows()
    raw = pd.read_parquet("data/processed/national_sample.parquet")
    missing = (raw.isna().mean() * 100).round(2)
    missing = {k: float(v) for k, v in missing[missing > 0].sort_values(ascending=False).items()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eda.json").write_text(json.dumps(eda(full, list(raw.columns), missing), default=float))
    print("eda written", flush=True)
    df = full.sample(N, random_state=SEED).sort_values("Start_Time").reset_index(drop=True)
    tr, te = E.temporal_split(df)
    X = E.matrix(df.join(E.oof_encode(df, tr)))
    plots = {"classification": classification(df, X, tr, te), "regression": regression(df, X, tr, te),
             "clustering": clustering(df, E.matrix(df.join(E.oof_encode(df, np.ones(len(df), bool))))), "timeseries": timeseries(full)}
    (OUT / "model_plots.json").write_text(json.dumps(plots, default=float))
    print("model plots written", flush=True)


if __name__ == "__main__":
    main()

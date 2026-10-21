"""Location report: everything the explorer shows for one (lat, lng, radius).

Sections (each a pure function of the rows inside the radius + the trained engine):
  profile     volume, density percentile vs all US crash cells, severity, state/national comparison
  when        hour x weekday counts and severe share, seasonality, yearly trend
  conditions  weather / visibility / temperature / light / road-feature lift, duration distribution
  danger      model-based: P(severe) per hour x weekday (typical weather) x crash frequency = danger slots;
              partial dependence of severity on weather x light, visibility, temperature at THIS location
  spots       ~110 m grid cells ranked by observed-vs-expected severe z-score and by volume
  outliers    severe crashes the model rated unlikely; extreme disruptions; IsolationForest multivariate outliers
  outlook     12-month forecast with 10-90% band, local backtest vs seasonal naive, expected severe crashes
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.engine import FC_HORIZON, ROAD_FLAGS, SEV_FEATURES, WEATHER, fc_features, matrix

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = pd.period_range("2016-03", "2023-02", freq="M")
SPOT_DEG = 0.001          # ~110 m cells
SPOT_MIN_N = 5
TOP_K = 8
PDP_YEAR = 2019           # severity labels drift by year; pin a stable, well-covered year
WEATHER_SHOWN = ["clear", "cloudy", "rain", "snow", "fog", "thunder"]
VIS_GRID = [0.25, 0.5, 1, 2, 3, 5, 7, 10]
TEMP_GRID = [-10, 0, 10, 20, 32, 40, 50, 60, 70, 80, 90, 100]
DURATION_BINS = [0, 15, 30, 45, 60, 90, 120, 180, 240, 360, 720, 1440, 10080]
ISO_FEATURES = ["hour", "dow", "Severity", "log_duration", "Temperature(F)", "Visibility(mi)", "Precipitation(in)", "is_night"]
ISO_CONTAMINATION = 0.01
STATS = [None]  # engine cell_stats, set by the server at startup (location-history features for new points)


def wavg(x, w) -> float:
    return float(np.average(x, weights=w)) if len(x) else float("nan")


def rate_table(d: pd.DataFrame, key: pd.Series, order=None, min_rows: int = 3) -> list[dict]:
    """Per-group weighted count, share, severe rate and lift vs the local severe rate."""
    base = wavg(d.is_severe, d.w)
    g = d.groupby(key, observed=True)
    out = []
    for k, x in g:
        if len(x) < min_rows:
            continue
        sr = wavg(x.is_severe, x.w)
        out.append({"key": str(k), "n": float(x.w.sum()), "share": float(x.w.sum() / d.w.sum()), "severe_rate": sr,
                    "lift": sr / base if base else None, "median_duration": float(x.duration_min.median())})
    if order:
        rank = {str(k): i for i, k in enumerate(order)}
        out.sort(key=lambda r: rank.get(r["key"], 99))
    return out


def profile(d, ctx) -> dict:
    w = d.w
    n = float(w.sum())
    per_km2 = n / (np.pi * ctx["r"] ** 2)
    state = d.State.mode().iat[0]
    return {
        "n": n, "rows": len(d), "sampled": bool((w > 1).any()), "per_year": n / 7.0, "per_km2": per_km2,
        "density_pct": float((ctx["cell_density"] < per_km2).mean() * 100),
        "severity": {str(k): float(v) for k, v in w.groupby(d.Severity).sum().items()},
        "severe_rate": wavg(d.is_severe, w), "night_share": wavg(d.is_night, w), "rush_share": wavg(d.is_rush_hour, w),
        "median_duration": float(d.duration_min.median()), "p90_duration": float(d.duration_min.quantile(0.9)),
        "state": state, "state_stats": ctx["state_stats"].get(state), "national": ctx["national"],
        "cities": {k: float(v) for k, v in w.groupby(d.City).sum().nlargest(5).items()},
    }


def when(d) -> dict:
    w = d.w
    grid = np.zeros((7, 24))
    sev = np.zeros((7, 24))
    np.add.at(grid, (d.dow.to_numpy(), d.hour.to_numpy()), w.to_numpy())
    np.add.at(sev, (d.dow.to_numpy(), d.hour.to_numpy()), (w * d.is_severe).to_numpy())
    peak = np.unravel_index(grid.argmax(), grid.shape)
    return {"grid": grid.round(1).tolist(), "severe_grid": sev.round(1).tolist(),
            "peak": {"dow": DOW[peak[0]], "hour": int(peak[1])},
            "by_month": {int(k): float(v) for k, v in w.groupby(d.month).sum().items()},
            "by_year": {int(k): float(v) for k, v in w.groupby(d.year).sum().items()},
            "severe_by_year": {int(k): wavg(x.is_severe, x.w) for k, x in d.groupby(d.year)}}


def conditions(d) -> dict:
    vis = pd.cut(d["Visibility(mi)"], [-0.1, 1, 3, 7, 100], labels=["<1 mi", "1–3 mi", "3–7 mi", "7+ mi"])
    temp = pd.cut(d["Temperature(F)"], [-100, 20, 32, 50, 70, 85, 200], labels=["<20°F", "20–32°F", "32–50°F", "50–70°F", "70–85°F", "85°F+"])
    light = d.is_night.map({0: "day", 1: "night"})
    roads = []
    for f in ROAD_FLAGS:
        on = d[d[f] == 1]
        if len(on) >= 5:
            off = d[d[f] == 0]
            roads.append({"key": f.replace("_", " ").lower(), "n": float(on.w.sum()), "share": float(on.w.sum() / d.w.sum()),
                          "severe_rate": wavg(on.is_severe, on.w), "severe_rate_without": wavg(off.is_severe, off.w),
                          "median_duration": float(on.duration_min.median())})
    hist = np.histogram(d.duration_min.clip(upper=DURATION_BINS[-1] - 1), bins=DURATION_BINS, weights=d.w)[0]
    return {"weather": rate_table(d, d.weather_group.astype(str), order=WEATHER),
            "visibility": rate_table(d, vis, order=list(vis.cat.categories)),
            "temperature": rate_table(d, temp, order=list(temp.cat.categories)),
            "light": rate_table(d, light, order=["day", "night"]),
            "roads": sorted(roads, key=lambda r: -r["n"]),
            "duration_hist": {"edges": DURATION_BINS, "counts": hist.round(1).tolist()}}


def _typical_row(d, lat, lng) -> dict:
    row = {c: float(d[c].median()) for c in ["Temperature(F)", "Visibility(mi)", "Wind_Speed(mph)", "Humidity(%)"]}
    row.update({"Start_Lat": lat, "Start_Lng": lng, "year": PDP_YEAR, "month": int(d.month.mode().iat[0]), "hour": 12, "dow": 2,
                "is_night": 0, "is_weekend": 0, "is_rush_hour": 0, "Precipitation(in)": 0.0, "weather_group": "clear"})
    row.update({f: int(round(d[f].mean())) for f in ROAD_FLAGS})  # the spot's typical road features
    if "Source" in d:
        recent = d[d.year >= d.year.max() - 1]
        row["Source"] = str(recent.Source.mode().iat[0])        # the feed currently reporting here
    return row


def _p_severe(model, rows: list[dict]) -> np.ndarray:
    X = matrix(pd.DataFrame(rows), STATS[0])[SEV_FEATURES]
    cls = list(model.classes_)
    p = model.predict_proba(X)
    return p[:, [cls.index(3), cls.index(4)]].sum(1)


def danger(d, ctx, lat, lng) -> dict:
    """Model-based views at THIS location. Relative numbers (vs the spot's typical conditions) are the point."""
    model, base = ctx["engine"]["severity"], _typical_row(d, lat, lng)
    ref = float(_p_severe(model, [base])[0])
    slots = [dict(base, hour=h, dow=k, is_night=int(h < 6 or h >= 20), is_weekend=int(k >= 5),
                  is_rush_hour=int(k < 5 and (7 <= h <= 9 or 16 <= h <= 18))) for k in range(7) for h in range(24)]
    p_slot = _p_severe(model, slots).reshape(7, 24)
    freq = np.zeros((7, 24))
    np.add.at(freq, (d.dow.to_numpy(), d.hour.to_numpy()), d.w.to_numpy())
    freq_week = freq / (7 * 52)  # crashes per specific week-slot per week, averaged over ~7 years
    expected_severe = freq_week * p_slot
    top = np.argsort(expected_severe.ravel())[::-1][:5]
    wx = []
    for wg in WEATHER_SHOWN:
        precip = 0.08 if wg in ("rain", "snow", "thunder") else 0.0
        vis = {"fog": 0.5, "snow": 2.0, "rain": 5.0, "thunder": 4.0}.get(wg, base["Visibility(mi)"])
        p = _p_severe(model, [dict(base, weather_group=wg, **{"Precipitation(in)": precip, "Visibility(mi)": vis}, is_night=n,
                                   hour=[14, 23][n]) for n in (0, 1)])
        wx.append({"weather": wg, "day": float(p[0] / ref), "night": float(p[1] / ref)})
    vis_curve = _p_severe(model, [dict(base, **{"Visibility(mi)": v}) for v in VIS_GRID]) / ref
    temp_curve = _p_severe(model, [dict(base, **{"Temperature(F)": t}) for t in TEMP_GRID]) / ref
    feats = []
    for f in ["Junction", "Traffic_Signal", "Crossing", "Stop", "Railway"]:
        on, off = _p_severe(model, [dict(base, **{f: 1}), dict(base, **{f: 0})])
        feats.append({"feature": f.replace("_", " ").lower(), "ratio": float(on / off), "present_here": bool(base[f])})
    dur_models = ctx["engine"]["duration"]
    dur = {}
    for label, s in (("minor", 2), ("severe", 3)):
        Xd = matrix(pd.DataFrame([base]), STATS[0])[SEV_FEATURES].assign(Severity=s)
        dur[label] = {str(q): float(np.expm1(m.predict(Xd)[0])) for q, m in dur_models.items()}
    return {"reference_p": ref, "p_slot_rel": (p_slot / ref).round(3).tolist(),
            "expected_severe_grid": expected_severe.round(4).tolist(),
            "top_slots": [{"dow": DOW[i // 24], "hour": int(i % 24), "severe_per_year": float(expected_severe.ravel()[i] * 52),
                           "crashes_per_year": float(freq_week.ravel()[i] * 52), "p_rel": float(p_slot.ravel()[i] / ref)} for i in top],
            "weather": wx, "visibility": {"x": VIS_GRID, "y": vis_curve.round(3).tolist()},
            "temperature": {"x": TEMP_GRID, "y": temp_curve.round(3).tolist()}, "features": feats, "duration": dur}


def spots(d) -> dict:
    cell = (d.Start_Lat // SPOT_DEG).astype(int).astype(str) + "_" + (d.Start_Lng // SPOT_DEG).astype(int).astype(str)
    g = d.assign(cell=cell, ws=d.w * d.is_severe, we=d.w * d.p_severe, wv=d.w ** 2 * d.p_severe * (1 - d.p_severe)).groupby("cell")
    t = pd.DataFrame({"n": g.w.sum(), "rows": g.size(), "severe": g.ws.sum(), "expected": g.we.sum(), "var": g.wv.sum(),
                      "lat": g.Start_Lat.mean(), "lng": g.Start_Lng.mean(), "median_duration": g.duration_min.median(),
                      "peak_hour": g.hour.agg(lambda x: int(x.mode().iat[0])), "night_share": g.is_night.mean()})
    t = t[t.rows >= SPOT_MIN_N]
    t["z"] = (t.severe - t.expected) / np.sqrt(t["var"].clip(lower=1e-6))
    t["severe_rate"] = t.severe / t.n
    records = lambda x: x.reset_index(drop=True).round(4).to_dict("records")
    return {"by_risk": records(t[t.severe > 0].nlargest(TOP_K, "z")), "by_volume": records(t.nlargest(TOP_K, "n")),
            "cells": len(t)}


def _crash(r, why: str) -> dict:
    return {"lat": float(r.Start_Lat), "lng": float(r.Start_Lng), "time": r.Start_Time.strftime("%Y-%m-%d %H:%M"),
            "severity": int(r.Severity), "duration_min": float(r.duration_min), "weather": str(r.weather_group),
            "p_severe": float(r.p_severe), "city": str(r.City), "why": why}


def _readable(col: str, v: float) -> str:
    """Isolation-forest reason in human units."""
    if col == "log_duration":
        m = float(np.expm1(v))
        return f"delay {m / 60:.1f} h" if m >= 90 else f"delay {m:.0f} min"
    if col == "hour":
        return f"{int(v):02d}:00"
    if col == "dow":
        return DOW[int(v)]
    if col == "is_night":
        return "night" if v else "daytime"
    unit = {"Temperature(F)": "°F", "Visibility(mi)": " mi visibility", "Precipitation(in)": " in rain"}.get(col, "")
    return f"{col.split('(')[0].lower()} {v:.1f}" if not unit else f"{v:.1f}{unit}"


def outliers(d) -> dict:
    sev = d[d.is_severe == 1].nsmallest(TOP_K, "p_severe")
    surprise = [_crash(r, f"model gave {r.p_severe:.0%} chance of a severe outcome") for r in sev.itertuples()]
    p99 = d.duration_min.quantile(0.99)
    long_ = [_crash(r, f"traffic impact {r.duration_min / 60:.1f} h (local p99 {p99 / 60:.1f} h)")
             for r in d.nlargest(TOP_K, "duration_min").itertuples()]
    multi = []
    X = d[ISO_FEATURES].fillna(d[ISO_FEATURES].median())
    if len(X) >= 50:
        iso = IsolationForest(contamination=ISO_CONTAMINATION, random_state=0).fit(X)
        score = -iso.score_samples(X)
        z = ((X - X.median()) / (X.quantile(0.75) - X.quantile(0.25)).replace(0, 1)).abs()
        for i in np.argsort(score)[::-1][:TOP_K]:
            r = d.iloc[i]
            top = z.iloc[i].nlargest(2).index
            why = ", ".join(_readable(c, X.iloc[i][c]) for c in top)
            multi.append(_crash(r, f"unusual combination: {why}"))
    return {"surprising_severe": surprise, "extreme_duration": long_, "multivariate": multi, "duration_p99": float(p99)}


def outlook(d, ctx) -> dict:
    models = ctx["engine"]["forecast"]
    s = d.w.groupby(d.Start_Time.dt.to_period("M")).sum().reindex(MONTHS, fill_value=0).to_numpy(float)
    mon = MONTHS.month.to_numpy()
    F = fc_features(s, mon)
    last = slice(len(s) - FC_HORIZON, len(s))  # backtest: one-step-ahead over the last 12 observed months
    bt = np.expm1(models[0.5].predict(F[last]))
    backtest = {"mae_model": float(np.abs(bt - s[last]).mean()), "mae_seasonal_naive": float(np.abs(s[last.start - 12:last.stop - 12] - s[last]).mean()),
                "months": [str(p) for p in MONTHS[last]], "actual": s[last].tolist(), "predicted": bt.round(2).tolist()}
    future = pd.period_range(MONTHS[-1] + 1, periods=FC_HORIZON, freq="M")
    hist, out = s.copy(), {q: [] for q in (0.1, 0.5, 0.9)}
    all_months = np.r_[mon, future.month]
    for _ in future:  # recursive multi-step: feed the median back in
        row = fc_features(np.r_[hist, 0.0], all_months[: len(hist) + 1])[-1:]
        for q, m in models.items():
            out[q].append(max(float(np.expm1(m.predict(row)[0])), 0.0))
        hist = np.r_[hist, out[0.5][-1]]
    recent = d[d.year >= 2021]
    sev_rate = wavg(recent.is_severe, recent.w) if len(recent) >= 20 else wavg(d.is_severe, d.w)
    return {"history": {str(k): float(v) for k, v in zip(MONTHS, s)}, "months": [str(p) for p in future],
            "p10": out[0.1], "p50": out[0.5], "p90": out[0.9], "backtest": backtest,
            "expected_severe_12m": float(sum(out[0.5]) * sev_rate), "severe_rate_used": sev_rate}


def build(d: pd.DataFrame, ctx: dict, lat: float, lng: float) -> dict:
    if d.empty:
        return {"n": 0}
    points = d.sample(min(3000, len(d)), random_state=0)
    return {"n": float(d.w.sum()), "profile": profile(d, ctx), "when": when(d), "conditions": conditions(d),
            "danger": danger(d, ctx, lat, lng), "spots": spots(d), "diagnostics": diagnostics(d, ctx), "outliers": outliers(d), "outlook": outlook(d, ctx),
            "points": [[round(a, 5), round(b, 5), int(s), t.strftime("%Y-%m")]
                       for a, b, s, t in zip(points.Start_Lat, points.Start_Lng, points.Severity, points.Start_Time)]}


# ---------------------------------------------------------------- interactive scenario + model diagnostics
SCENARIO_KEYS = {"hour": int, "dow": int, "month": int, "weather": str, "vis": float, "temp": float,
                 "Junction": int, "Traffic_Signal": int, "Crossing": int, "Stop": int, "Railway": int}
SCENARIO_LABELS = {"hour": "time of day", "dow": "day of week", "month": "month", "weather": "weather", "vis": "visibility",
                   "temp": "temperature", "Junction": "junction", "Traffic_Signal": "traffic signal", "Crossing": "crossing",
                   "Stop": "stop sign", "Railway": "railway"}
CALIBRATION_BINS = 8
DURATION_SAMPLE = 4000


def _apply(row: dict, key: str, val) -> dict:
    """Set one scenario attribute, keeping derived fields (night, rush hour, precipitation) consistent."""
    r = dict(row)
    if key == "hour":
        r["hour"] = val
    elif key == "dow":
        r["dow"] = val
    elif key == "month":
        r["month"] = val
    elif key == "weather":
        r["weather_group"] = val
        r["Precipitation(in)"] = 0.08 if val in ("rain", "snow", "thunder") else 0.0
    elif key == "vis":
        r["Visibility(mi)"] = val
    elif key == "temp":
        r["Temperature(F)"] = val
    else:
        r[key] = val
    h, k = r["hour"], r["dow"]
    r.update(is_night=int(h < 6 or h >= 20), is_weekend=int(k >= 5), is_rush_hour=int(k < 5 and (7 <= h <= 9 or 16 <= h <= 18)))
    return r


def _proba(model, rows: list[dict]) -> np.ndarray:
    X = matrix(pd.DataFrame(rows), STATS[0])[SEV_FEATURES]
    p = model.predict_proba(X)
    out = np.zeros((len(rows), 4))
    for j, c in enumerate(model.classes_):
        out[:, int(c) - 1] = p[:, j]
    return out


def scenario(d, ctx, lat, lng, params: dict) -> dict:
    """Scenario vs this spot's typical crash. Contributions = mean of 'add to baseline' and 'remove from scenario' effects."""
    sev, durm = ctx["engine"]["severity"], ctx["engine"]["duration"]
    base = _typical_row(d, lat, lng)
    base_vals = {"hour": 12, "dow": 2, "month": base["month"], "weather": "clear", "vis": base["Visibility(mi)"],
                 "temp": base["Temperature(F)"], **{f: base[f] for f in ["Junction", "Traffic_Signal", "Crossing", "Stop", "Railway"]}}
    scen = base
    changed = [k for k, v in params.items() if v != base_vals.get(k)]
    for k in changed:
        scen = _apply(scen, k, params[k])
    rows = [base, scen]
    for k in changed:
        rows.append(_apply(base, k, params[k]))            # baseline + this change
        without = base
        for j in changed:
            if j != k:
                without = _apply(without, j, params[j])
        rows.append(without)                                 # scenario minus this change
    P = _proba(sev, rows)
    ps = P[:, 2:].sum(1)
    contrib = [{"key": k, "label": SCENARIO_LABELS[k], "pts": float(0.5 * ((ps[2 + 2 * i] - ps[0]) + (ps[1] - ps[3 + 2 * i])) * 100)}
               for i, k in enumerate(changed)]
    dur = {}
    for s in (2, 3):
        Xd = matrix(pd.DataFrame([scen]), STATS[0])[SEV_FEATURES].assign(Severity=s)
        dur[s] = {str(q): float(np.expm1(m.predict(Xd)[0])) for q, m in durm.items()}
    expected_minutes = float(sum(P[1, s - 1] * dur[min(max(s, 2), 3)]["0.5"] for s in (1, 2, 3, 4)))
    return {"proba": P[1].round(4).tolist(), "base_proba": P[0].round(4).tolist(), "p_severe": float(ps[1]), "base_p_severe": float(ps[0]),
            "us_severe_rate": ctx["national"]["severe_rate"], "local_severe_rate": wavg(d.is_severe, d.w),
            "contributions": sorted(contrib, key=lambda c: -abs(c["pts"])), "duration": dur, "expected_minutes": expected_minutes,
            "baseline": base_vals}


def diagnostics(d, ctx) -> dict:
    """How well the models do on the crashes inside this radius."""
    from sklearn.metrics import roc_auc_score
    y, p, w = d.is_severe.to_numpy(), d.p_severe.to_numpy(), d.w.to_numpy()
    out = {"n": int(len(d))}
    q = np.unique(np.quantile(p, np.linspace(0, 1, CALIBRATION_BINS + 1)))
    if len(q) > 2:
        b = np.clip(np.searchsorted(q, p, side="right") - 1, 0, len(q) - 2)
        out["calibration"] = [{"pred": float(np.average(p[b == i], weights=w[b == i])), "obs": float(np.average(y[b == i], weights=w[b == i])),
                               "n": int((b == i).sum())} for i in range(len(q) - 1) if (b == i).any()]
    if 0 < y.mean() < 1:
        out["auc"] = float(roc_auc_score(y, p, sample_weight=w))
    out["brier"] = float(np.average((p - y) ** 2, weights=w))
    out["base_rate"] = float(np.average(y, weights=w))
    s = d.sample(min(DURATION_SAMPLE, len(d)), random_state=0)
    pred = np.expm1(ctx["engine"]["duration"][0.5].predict(matrix(s, STATS[0])[SEV_FEATURES].assign(Severity=s.Severity.to_numpy())))
    act = s.duration_min.to_numpy()
    order = np.argsort(pred)
    bins = np.array_split(order, min(10, max(len(s) // 20, 1)))
    out["duration"] = {"mae_model": float(np.abs(pred - act).mean()), "mae_median": float(np.abs(np.median(act) - act).mean()),
                       "bins": [{"pred": float(np.median(pred[i])), "obs": float(np.median(act[i])), "n": len(i)} for i in bins if len(i)]}
    names = ctx["engine"]["regimes"]["names"]
    share = d.w.groupby(d.regime).sum() / d.w.sum()
    out["regimes"] = sorted([{"name": names[int(k)], "share": float(v), "us": float(ctx["regime_share"].get(int(k), 0)),
                              "severe_rate": wavg(d.is_severe[d.regime == k], d.w[d.regime == k])} for k, v in share.items()],
                            key=lambda r: -r["share"])
    return out


# ---------------------------------------------------------------- live: real current weather + local time -> model predictions
OPEN_METEO = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}"
              "&current=temperature_2m,precipitation,weather_code,visibility,wind_speed_10m"
              "&hourly=temperature_2m,weather_code,visibility&forecast_hours=24"
              "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=auto")
METERS_PER_MILE = 1609.34
LIVE_TIMEOUT_S = 12
WMO = [((0, 1), "clear"), ((2, 3), "cloudy"), ((45, 48), "fog"), ((51, 67), "rain"), ((80, 82), "rain"),
       ((71, 77), "snow"), ((85, 86), "snow"), ((95, 99), "thunder")]


def wmo_group(code) -> str:
    return next((g for (lo, hi), g in WMO if code is not None and lo <= code <= hi), "other")


def _weather_now(lat, lng) -> dict | None:
    import json as _json
    import urllib.request
    try:
        with urllib.request.urlopen(OPEN_METEO.format(lat=lat, lng=lng), timeout=LIVE_TIMEOUT_S) as r:
            return _json.load(r)
    except (OSError, ValueError):
        return None


def live(d, ctx, lat, lng) -> dict:
    """Predictions for the next 24 hours from real current/forecast weather and the location's clock.

    Expected crashes per hour = historical rate for that weekday-hour here x the recent volume level
    (12-month forecast / historical yearly average). P(severe) = severity model under that hour's weather.
    """
    wx = _weather_now(lat, lng)
    if wx is None:
        now = pd.Timestamp.now(tz="UTC")
        hours = [{"time": (now + pd.Timedelta(hours=i)).isoformat(), "code": None, "temp": None, "vis_m": None} for i in range(24)]
        source = "unavailable (typical conditions used)"
    else:
        h = wx["hourly"]
        hours = [{"time": t, "code": c, "temp": tp, "vis_m": v} for t, c, tp, v in zip(h["time"], h["weather_code"], h["temperature_2m"], h["visibility"])]
        hours[0] = {"time": wx["current"]["time"], "code": wx["current"]["weather_code"], "temp": wx["current"]["temperature_2m"],
                    "vis_m": wx["current"]["visibility"]}
        source = "Open-Meteo (live)"
    base = _typical_row(d, lat, lng)
    rows = []
    for hr in hours:
        t = pd.Timestamp(hr["time"])
        g = wmo_group(hr["code"]) if hr["code"] is not None else "clear"
        r = _apply(_apply(_apply(base, "hour", t.hour), "dow", t.dayofweek), "month", t.month)
        r = _apply(r, "weather", g)
        if hr["temp"] is not None:
            r = _apply(r, "temp", float(hr["temp"]))
        if hr["vis_m"] is not None:
            r = _apply(r, "vis", min(float(hr["vis_m"]) / METERS_PER_MILE, 10.0))
        rows.append((t, g, hr, r))
    P = _proba(ctx["engine"]["severity"], [base] + [r for *_, r in rows])
    ps = P[:, 2:].sum(1)
    freq = np.zeros((7, 24))
    np.add.at(freq, (d.dow.to_numpy(), d.hour.to_numpy()), d.w.to_numpy())
    per_slot = freq / (7 * 52)
    fc = outlook(d, ctx)
    level = float(np.clip(sum(fc["p50"]) / max(d.w.sum() / 7.0, 1e-6), 0.05, 3.0))
    next24 = [{"time": t.isoformat(), "hour": int(t.hour), "weather": g, "temp": hr["temp"],
               "vis_mi": None if hr["vis_m"] is None else round(min(hr["vis_m"] / METERS_PER_MILE, 10.0), 1),
               "p_severe": float(ps[i + 1]), "expected": float(per_slot[t.dayofweek, t.hour] * level)}
              for i, (t, g, hr, _) in enumerate(rows)]
    return {"source": source, "now": next24[0], "base_p_severe": float(ps[0]), "level_factor": level,
            "next24": next24, "expected_24h": float(sum(h["expected"] for h in next24))}

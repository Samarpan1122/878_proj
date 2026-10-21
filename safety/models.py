"""Experimental local NB safety performance function and Gamma-Poisson EB.

This is not an HSM calibrated/certified model. Facility classes are unknown.
The shared segment random effect is fitted on period-aggregated counts, so its
dispersion and the EB weight use the same aggregation convention.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import gamma
from sklearn.model_selection import GroupKFold


def _eligible(panel):
    d = panel.loc[panel.model_eligible].copy()
    if d.empty:
        raise ValueError("No eligible segment years")
    if d.duplicated(["segment_id", "year"]).any():
        raise ValueError("Duplicate segment-year observations")
    for col in ["aadt", "length_miles", "days", "fatal_crashes"]:
        if not np.isfinite(d[col]).all():
            raise ValueError(f"Nonfinite {col}")
    if not (d.aadt.gt(0) & d.length_miles.gt(0) & d.days.gt(0) & d.fatal_crashes.ge(0)
            & d.fatal_crashes.eq(np.floor(d.fatal_crashes))).all():
        raise ValueError("Invalid exposures or noninteger counts")
    return d


def fit_spf(panel):
    """Fit NB2: mu = length_miles * days/365.25 * exp(b0+b1*log(AADT/10000)).

    Segment heterogeneity persists across observed years (Gamma mean 1, variance
    alpha); NB likelihood is applied to each segment's summed counts and means.
    """
    d = _eligible(panel)
    if d.segment_id.nunique() < 3 or d.fatal_crashes.sum() == 0:
        raise ValueError("SPF requires >=3 roads and at least one observed fatal crash")
    codes, _ = pd.factorize(d.segment_id)
    y = np.bincount(codes, weights=d.fatal_crashes)
    x = np.log(d.aadt.to_numpy() / 10000)
    offset = d.length_miles.to_numpy() * d.days.to_numpy() / 365.25

    def objective(theta):
        mean = np.bincount(codes, weights=offset * np.exp(np.clip(theta[0] + theta[1] * x, -50, 50)))
        size = np.exp(-theta[2])
        logp = (gammaln(y + size) - gammaln(size) - gammaln(y + 1)
                + size * (np.log(size) - np.log(size + mean))
                + y * (np.log(mean) - np.log(size + mean)))
        return -float(logp.sum())

    initial = [np.log(y.sum() / offset.sum()), 1.0, np.log(0.5)]
    bounds = [(-30, 20), (-3, 4), (-9, 6)]
    fits = [minimize(objective, [initial[0], initial[1], dispersion], method="L-BFGS-B", bounds=bounds)
            for dispersion in [initial[2], -4, 2]]
    good = [fit for fit in fits if fit.success and np.isfinite(fit.fun)]
    if not good:
        raise ValueError("Negative-binomial optimizer did not converge")
    fit = min(good, key=lambda f: f.fun)
    return {"kind": "experimental_local_nb2_spf", "outcome": "fatal_crash",
            "intercept": float(fit.x[0]), "log_aadt_coefficient": float(fit.x[1]),
            "alpha": float(np.exp(fit.x[2])), "negative_log_likelihood": float(fit.fun),
            "training_segments": int(d.segment_id.nunique()), "training_segment_years": len(d),
            "training_years": sorted(d.year.astype(int).unique().tolist()),
            "aadt_proxy_rows": int((~d.aadt_aligned).sum()),
            "boundary_fit": bool(any(abs(value - lo) < 1e-4 or abs(value - hi) < 1e-4
                                     for value, (lo, hi) in zip(fit.x, bounds))),
            "limitation": "Experimental; unknown facility class; not an HSM-calibrated SPF. "
                          "Conditional EB intervals exclude coefficient, matching and AADT uncertainty."}


def predict_spf(panel, model):
    """Expected fatal crash count per supplied segment-year (not fatalities)."""
    return (panel.length_miles.to_numpy() * panel.days.to_numpy() / 365.25
            * np.exp(model["intercept"] + model["log_aadt_coefficient"]
                     * np.log(panel.aadt.to_numpy() / 10000)))


def _metrics(y, pred):
    y, pred = np.asarray(y), np.maximum(np.asarray(pred), 1e-12)
    term = np.zeros_like(pred)
    nonzero = y > 0
    term[nonzero] = y[nonzero] * np.log(y[nonzero] / pred[nonzero])
    return {"rows": len(y), "observed_fatal_crashes": int(y.sum()),
            "predicted_fatal_crashes": float(pred.sum()), "mae": float(np.abs(y - pred).mean()),
            "mean_poisson_deviance": float((2 * (term - y + pred)).mean())}


def _holdout_metrics(train, holdout, model):
    # Reference model estimates one rate from training VMT only. It never uses
    # the held-out count or a full-data prior in its predictions.
    train_vmt = train.aadt * train.length_miles * train.days
    held_vmt = holdout.aadt * holdout.length_miles * holdout.days
    baseline = held_vmt * (train.fatal_crashes.sum() / train_vmt.sum())
    return {**_metrics(holdout.fatal_crashes, predict_spf(holdout, model)),
            "exposure_only_baseline": _metrics(holdout.fatal_crashes, baseline)}


def validate_spf(panel, spatial_block_degrees=0.25):
    """Latest complete year holdout plus disjoint geographic-block folds.

    Refit every fold; no crash-derived predictor or full-data EB estimate enters
    validation. Failures/insufficient coverage are explicit, never scored as zero.
    """
    if not np.isfinite(spatial_block_degrees) or spatial_block_degrees <= 0:
        raise ValueError("Spatial block size must be positive and finite")
    d = _eligible(panel)
    latest = d.year.max()
    result = {"temporal": {"status": "insufficient_years"}, "spatial": {"status": "unavailable"}}
    if d.year.nunique() > 1:
        try:
            train = d[d.year < latest]
            model = fit_spf(train)
            holdout = d[d.year == latest]
            result["temporal"] = {"status": "evaluated", "holdout_year": int(latest),
                                   **_holdout_metrics(train, holdout, model)}
        except ValueError as exc:
            result["temporal"] = {"status": "not_evaluable", "reason": str(exc)}
    if {"lat", "lng"}.issubset(d) and np.isfinite(d[["lat", "lng"]]).all().all():
        groups = ((np.floor(d.lat / spatial_block_degrees)).astype(int).astype(str) + ":"
                  + (np.floor(d.lng / spatial_block_degrees)).astype(int).astype(str))
        if groups.nunique() >= 2:
            folds = []
            for train, test in GroupKFold(n_splits=min(5, groups.nunique())).split(d, groups=groups):
                try:
                    model = fit_spf(d.iloc[train])
                    folds.append({"status": "evaluated", **_holdout_metrics(d.iloc[train], d.iloc[test], model)})
                except ValueError as exc:
                    folds.append({"status": "not_evaluable", "reason": str(exc)})
            result["spatial"] = {"status": "evaluated" if all(f["status"] == "evaluated" for f in folds)
                                 else "partially_evaluable", "block_degrees": spatial_block_degrees,
                                 "blocks": int(groups.nunique()), "folds": folds}
    return result


def screen_network(panel, model):
    """Conditional 95% EB intervals for annualized fatal-crash frequency.

    With period prediction M and count N, w=1/(1+alpha*M); EB=w*M+(1-w)*N.
    Posterior multiplier ~ Gamma(1/alpha+N, rate=1/alpha+M). Dividing
    total expected count by observed calendar-year equivalents gives annual rate.
    """
    d = _eligible(panel)
    alpha = float(model["alpha"])
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("Positive finite NB dispersion required")
    d["predicted"] = predict_spf(d, model)
    if not np.isfinite(d.predicted).all() or not d.predicted.gt(0).all():
        raise ValueError("SPF predictions must be finite and positive")
    d["years_observed"] = d.days / 365.25
    result = d.groupby("segment_id").agg(observed_fatal_crashes=("fatal_crashes", "sum"),
        observed_fatalities=("fatalities", "sum"), predicted_period=("predicted", "sum"),
        years_observed=("years_observed", "sum"), vehicle_miles=("vehicle_miles", "sum"),
        aadt=("aadt", "mean"), length_miles=("length_miles", "first"),
        aadt_aligned=("aadt_aligned", "all")).reset_index()
    for col in ["route", "lat", "lng", "facility_type"]:
        if col in d:
            result = result.merge(d[["segment_id", col]].drop_duplicates("segment_id"), on="segment_id")
    m, n, t = result.predicted_period, result.observed_fatal_crashes, result.years_observed
    shape, rate = 1 / alpha + n, 1 / alpha + m
    result["spf_weight"] = 1 / (1 + alpha * m)
    result["predicted_annual_fatal_crashes"] = m / t
    result["eb_annual_fatal_crashes"] = shape / rate * m / t
    result["eb_annual_lower95"] = gamma.ppf(0.025, shape, scale=1 / rate) * m / t
    result["eb_annual_upper95"] = gamma.ppf(0.975, shape, scale=1 / rate) * m / t
    result["excess_annual_fatal_crashes"] = result.eb_annual_fatal_crashes - m / t
    result["probability_above_spf"] = gamma.sf(1, shape, scale=1 / rate)
    result["observed_fatal_crashes_per_100m_vmt"] = n / result.vehicle_miles * 100_000_000
    result["fatalities_per_crash"] = result.observed_fatalities / n.replace(0, np.nan)
    result["eb_fatal_crashes_per_100m_vmt"] = result.eb_annual_fatal_crashes * t / result.vehicle_miles * 100_000_000
    result["outcome"] = "fatal_crash"
    result["screening_status"] = "experimental_review_required"
    return result.sort_values("excess_annual_fatal_crashes", ascending=False).reset_index(drop=True)

"""Development-only comparison of exposure-aware fatal-crash models.

All outer test outcomes are excluded from fitting, preprocessing, mixture gating
and calibration. The existing 2024 results have already been inspected: this is
a development holdout, not a new independent confirmation. No automatic promotion.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

from safety.models import fit_spf, predict_spf

FEATURES = ["log_aadt", "log_length_miles", "latitude", "longitude"]
CONTEXT_FEATURES = ["sinuosity", "road_vertices_per_mile", "bearing_sin", "bearing_cos",
                    "neighbor_roads_1km", "neighbor_roads_5km", "neighbor_mean_aadt_1km"]
LIMITATIONS = [
    "Development holdouts: the latest year has previously been inspected; require a new independent agency cohort.",
    "Fatal crashes only; excluded ambiguous/distant matches are not modeled or recovered by the model.",
    "Current AADT and road geometry remain historical proxies; no driver behavior or foundation-model claim.",
    "Temporal evaluation is retrospective: current-vintage covariates were not all available at the historical prediction date.",
    "Road neighborhoods use segment midpoints, not verified intersections; geometry features inherit road-vintage uncertainty.",
    "Facility class, speed, lanes, intersection design, historical geometry and contemporaneous weather are missing.",
    "Geographic coordinates describe location; they do not identify behavioral causes or causal treatment effects.",
    "Block-bootstrap intervals describe paired validation uncertainty, not individual predictive intervals.",
    "Bootstrap intervals condition on fitted folds and exclude model-refitting uncertainty; marginal bounds need independent confirmation.",
    "Historical EB forecasts apply only to known roads with strictly earlier crash observations; spatial tests are cold starts.",
    "Any successful challenger remains an unpromoted development artifact requiring manual and independent review.",
]


def _features(panel):
    """Only preexisting road properties; never year, fatalities or crash-selected context."""
    columns = [np.log(panel.aadt), np.log(panel.length_miles), panel.lat, panel.lng]
    columns.extend(pd.to_numeric(panel[name], errors="coerce").replace([np.inf, -np.inf], np.nan)
                   for name in CONTEXT_FEATURES if name in panel)
    return np.column_stack(columns)


def _vmt(panel):
    return panel.aadt.to_numpy() * panel.length_miles.to_numpy() * panel.days.to_numpy()


def _blocks(panel, size=.25):
    return (np.floor(panel.lat / size).astype(int).astype(str) + ":"
            + np.floor(panel.lng / size).astype(int).astype(str)).to_numpy()


def poisson_losses(y, mu):
    """Per-row count deviance; positive reference-minus-challenger is improvement."""
    y, mu = np.asarray(y, dtype=float), np.asarray(mu, dtype=float)
    if y.shape != mu.shape or np.any(~np.isfinite(mu)) or np.any(mu <= 0):
        raise ValueError("Predictions must have the observed shape and be finite and positive")
    term = np.zeros_like(mu)
    nonzero = y > 0
    term[nonzero] = y[nonzero] * np.log(y[nonzero] / mu[nonzero])
    return 2 * (term - y + mu)


def paired_block_interval(y, reference, challenger, groups, replicates=500, confidence=.975, random_state=878):
    """Resample whole geographic blocks, preserving within-road/year dependence.

    Default 97.5% two-sided intervals are Bonferroni-adjusted for two advanced
    cold-start challengers. run_benchmark uses 98.333% for its three challengers.
    """
    if replicates < 20 or not 0 < confidence < 1:
        raise ValueError("Use >=20 bootstrap replicates and confidence between zero and one")
    difference = poisson_losses(y, reference) - poisson_losses(y, challenger)
    codes, labels = pd.factorize(groups)
    if len(codes) != len(difference) or (codes < 0).any() or len(labels) < 2:
        raise ValueError("Paired bootstrap requires >=2 nonmissing geographic groups")
    sums = np.bincount(codes, weights=difference)
    counts = np.bincount(codes)
    rng = np.random.default_rng(random_state)
    samples = np.empty(replicates)
    for iteration in range(replicates):
        selected = rng.integers(0, len(labels), size=len(labels))
        samples[iteration] = sums[selected].sum() / counts[selected].sum()
    tail = (1 - confidence) / 2
    low, high = np.quantile(samples, [tail, 1 - tail])
    base = float(poisson_losses(y, reference).mean())
    return {"mean_deviance_improvement": float(difference.mean()),
            "relative_improvement": float(difference.mean() / base) if base else None,
            "lower": float(low), "upper": float(high), "confidence": confidence,
            "bootstrap_blocks": len(labels), "replicates": replicates,
            "uncertainty_excludes_zero": bool(low > 0), "direction": "positive favors challenger"}


@dataclass
class Experts:
    exposure_rate: float
    nb: dict
    boosting: HistGradientBoostingRegressor
    imputer: SimpleImputer

    def predict(self, panel):
        exposure = _vmt(panel)
        return {"exposure": np.maximum(exposure * self.exposure_rate, 1e-12),
                "negative_binomial": np.maximum(predict_spf(panel, self.nb), 1e-12),
                "poisson_boosting": np.maximum(self.boosting.predict(self.imputer.transform(_features(panel))) * exposure / 1e6, 1e-12)}


def _fit_experts(train, seed):
    exposure = _vmt(train)
    counts = train.fatal_crashes.to_numpy(dtype=float)
    # Weighted Poisson regression of y/exposure is equivalent to count Poisson
    # likelihood with log(exposure) offset. Fixed hyperparameters, no random
    # early-stopping split and no held-out feature/hyperparameter selection.
    boost = HistGradientBoostingRegressor(loss="poisson", learning_rate=.05, max_iter=100,
        max_leaf_nodes=7, min_samples_leaf=max(20, min(200, len(train) // 20)),
        l2_regularization=10., max_bins=64, early_stopping=False, random_state=seed)
    scaled = exposure / 1e6
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    boost.fit(imputer.fit_transform(_features(train)), counts / scaled, sample_weight=scaled)
    return Experts(float(counts.sum() / exposure.sum()), fit_spf(train), boost, imputer)


@dataclass
class GatedMixture:
    experts: Experts
    scaler: StandardScaler
    imputer: SimpleImputer
    coefficients: np.ndarray
    calibration: float
    gate_training_rows: int

    def predict(self, panel):
        predictions = self.experts.predict(panel)
        x = np.column_stack([np.ones(len(panel)), self.scaler.transform(self.imputer.transform(_features(panel)))])
        weight = expit(x @ self.coefficients)
        predictions["gated_mixture"] = self.calibration * (
            weight * predictions["poisson_boosting"] + (1 - weight) * predictions["negative_binomial"])
        return predictions


def _fit_mixture(train, mode, seed):
    """Train gate/calibration on INNER holdouts, then refit experts on outer train."""
    if mode == "temporal":
        latest = train.year.max()
        splits = [(np.flatnonzero(train.year.to_numpy() < latest), np.flatnonzero(train.year.to_numpy() == latest))]
        if not len(splits[0][0]):
            raise ValueError("Temporal mixture requires at least two training years before the outer holdout")
    else:
        groups = _blocks(train)
        if len(np.unique(groups)) < 3:
            raise ValueError("Spatial mixture requires at least three training geographic blocks")
        splits = list(GroupKFold(n_splits=3).split(train, groups=groups))
    pieces, nb_predictions, boost_predictions = [], [], []
    for index, (fit_index, gate_index) in enumerate(splits):
        inner_train, inner_holdout = train.iloc[fit_index], train.iloc[gate_index]
        experts = _fit_experts(inner_train, seed + index)
        predictions = experts.predict(inner_holdout)
        pieces.append(inner_holdout)
        nb_predictions.append(predictions["negative_binomial"])
        boost_predictions.append(predictions["poisson_boosting"])
    gate_data = pd.concat(pieces)
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    gate_features = imputer.fit_transform(_features(gate_data))
    scaler = StandardScaler().fit(gate_features)
    x = np.column_stack([np.ones(len(gate_data)), scaler.transform(gate_features)])
    nb, boost = np.concatenate(nb_predictions), np.concatenate(boost_predictions)
    y = gate_data.fatal_crashes.to_numpy(dtype=float)

    def objective(coefficients):
        weight = expit(x @ coefficients)
        mu = weight * boost + (1 - weight) * nb
        # Regularization protects a four-feature gate trained on sparse counts.
        return float(np.mean(mu - y * np.log(mu)) + .001 * np.sum(coefficients ** 2))

    result = minimize(objective, np.zeros(x.shape[1]), method="L-BFGS-B",
                      bounds=[(-5, 5)] * x.shape[1])
    if not result.success:
        raise ValueError("Mixture gate optimization did not converge")
    weight = expit(x @ result.x)
    denominator = (weight * boost + (1 - weight) * nb).sum()
    calibration = float(y.sum() / denominator)
    if calibration <= 0:
        raise ValueError("Mixture calibration requires observed crashes in inner holdouts")
    return GatedMixture(_fit_experts(train, seed), scaler, imputer, result.x, calibration, len(gate_data))


def historical_eb_prediction(train, holdout, nb):
    """Predict later known-road observations using only strictly prior counts."""
    if train.year.max() >= holdout.year.min():
        raise ValueError("Historical forecast training observations must strictly precede the holdout")
    prior = train.assign(predicted=predict_spf(train, nb)).groupby("segment_id").agg(
        counts=("fatal_crashes", "sum"), expected=("predicted", "sum"))
    lookup = prior.reindex(holdout.segment_id)
    size = 1 / nb["alpha"]
    multiplier = (lookup.counts.fillna(0).to_numpy() + size) / (lookup.expected.fillna(0).to_numpy() + size)
    return predict_spf(holdout, nb) * multiplier


def _metrics(y, prediction):
    y = np.asarray(y)
    top = np.argsort(-np.asarray(prediction), kind="stable")[:max(1, int(np.ceil(len(y) / 10)))]
    return {"rows": len(y), "observed_fatal_crashes": int(y.sum()),
            "predicted_fatal_crashes": float(np.sum(prediction)),
            "mean_poisson_deviance": float(poisson_losses(y, prediction).mean()),
            "mae": float(np.abs(y - prediction).mean()),
            "top_decile_row_crash_capture": float(y[top].sum() / y.sum()) if y.sum() else None}


def _summarize(holdout, predictions, replicates, seed):
    result = {"models": {name: _metrics(holdout.fatal_crashes, p) for name, p in predictions.items()},
              "comparisons": {}}
    for name in ["poisson_boosting", "gated_mixture", "historical_eb"]:
        if name in predictions:
            result["comparisons"][name] = {baseline: paired_block_interval(
                holdout.fatal_crashes, predictions[baseline], predictions[name], _blocks(holdout),
                replicates=replicates, confidence=1 - .05 / 3, random_state=seed)
                for baseline in ["exposure", "negative_binomial"]}
    return result


def _validate_panel(panel):
    required = {"segment_id", "year", "aadt", "length_miles", "days", "lat", "lng", "fatal_crashes",
                "model_eligible", "aadt_aligned", "outcome"}
    if required - set(panel):
        raise ValueError(f"Panel is missing required fields: {sorted(required - set(panel))}")
    d = panel.loc[panel.model_eligible].copy().reset_index(drop=True)
    if d.empty or not d.outcome.eq("fatal_crash").all() or d.duplicated(["segment_id", "year"]).any():
        raise ValueError("Require unique, eligible fatal-crash segment-years")
    if not np.isfinite(d[["year", "aadt", "length_miles", "days", "lat", "lng", "fatal_crashes"]]).all().all():
        raise ValueError("Benchmark requires finite numeric road features and counts")
    if not (d.aadt.gt(0) & d.length_miles.gt(0) & d.days.gt(0) & d.fatal_crashes.ge(0)
            & d.fatal_crashes.eq(np.floor(d.fatal_crashes))).all():
        raise ValueError("Invalid exposure or noninteger crash count")
    if d.year.nunique() < 3 or d.segment_id.nunique() < 12 or d.fatal_crashes.sum() < 10:
        raise ValueError("Benchmark requires >=3 years, >=12 segments, and >=10 fatal crashes")
    # Missing rows cannot silently become no-crash years. Also ensure each road
    # occupies one geographic block; no segment may cross outer train/test folds.
    if not d.groupby("segment_id").year.nunique().eq(d.year.nunique()).all():
        raise ValueError("Benchmark requires a complete zero-inclusive segment-year panel")
    if d.assign(block=_blocks(d)).groupby("segment_id").block.nunique().gt(1).any():
        raise ValueError("A road's geographic block must be consistent across years")
    return d


def run_benchmark(panel, spatial_folds=5, bootstrap_replicates=500, random_state=878, fit_final=False):
    """Return (strict-JSON report, optional *unpromoted* fitted challenger).

    Computational work is sequential. Hyperparameters are frozen, not tuned to
    the outer holdouts. A challenger requires positive adjusted bootstrap lower
    bounds versus BOTH references on temporal AND spatial experiments. Historical
    EB is a separate known-road task and cannot claim cold-start generalization.
    """
    if not 2 <= spatial_folds <= 10 or bootstrap_replicates < 20:
        raise ValueError("Use 2–10 spatial folds and >=20 bootstrap replicates")
    d = _validate_panel(panel)
    blocks = _blocks(d)
    if len(np.unique(blocks)) < max(5, spatial_folds):
        raise ValueError("Insufficient geographic blocks for nested spatial validation")
    latest = d.year.max()
    train, holdout = d[d.year < latest], d[d.year == latest]
    temporal_model = _fit_mixture(train, "temporal", random_state)
    temporal_predictions = temporal_model.predict(holdout)
    temporal_predictions["historical_eb"] = historical_eb_prediction(train, holdout, temporal_model.experts.nb)
    temporal = _summarize(holdout, temporal_predictions, bootstrap_replicates, random_state)
    temporal.update({"holdout_year": int(latest), "training_years": sorted(train.year.astype(int).unique().tolist()),
                     "gate_training_rows": temporal_model.gate_training_rows, "purpose": "known network, later year"})
    oof = {name: np.empty(len(d)) for name in ["exposure", "negative_binomial", "poisson_boosting", "gated_mixture"]}
    folds = []
    for fold, (fit_index, test_index) in enumerate(GroupKFold(n_splits=spatial_folds).split(d, groups=blocks)):
        fit, test = d.iloc[fit_index], d.iloc[test_index]
        model = _fit_mixture(fit, "spatial", random_state + fold + 1)
        prediction = model.predict(test)
        for name in oof:
            oof[name][test_index] = prediction[name]
        folds.append({"fold": fold, "training_segments": int(fit.segment_id.nunique()),
                      "test_segments": int(test.segment_id.nunique()), "test_rows": len(test),
                      "test_fatal_crashes": int(test.fatal_crashes.sum()),
                      "gate_training_rows": model.gate_training_rows})
    spatial = _summarize(d, oof, bootstrap_replicates, random_state)
    spatial.update({"folds": folds, "block_degrees": .25, "purpose": "unseen geographic blocks, no road history"})
    eligible = []
    for name in ["poisson_boosting", "gated_mixture"]:
        if all(result["comparisons"][name][base]["lower"] > 0
               for result in [temporal, spatial] for base in ["exposure", "negative_binomial"]):
            eligible.append(name)
    winner = min(eligible, key=lambda name: temporal["models"][name]["mean_poisson_deviance"]) if eligible else None
    final = None
    if fit_final and winner:
        # This object is returned to the caller only. It is never written over the
        # active NB/EB snapshot or automatically deployed.
        final = _fit_mixture(d, "spatial", random_state) if winner == "gated_mixture" else _fit_experts(d, random_state)
    report = {"schema_version": 1, "status": "development_benchmark", "primary_metric": "mean_poisson_deviance",
        "rows": len(d), "segments": int(d.segment_id.nunique()), "fatal_crashes": int(d.fatal_crashes.sum()),
        "zero_count_fraction": float(d.fatal_crashes.eq(0).mean()),
        "features": FEATURES + [name for name in CONTEXT_FEATURES if name in d],
        "aadt_proxy_fraction": float((~d.aadt_aligned).mean()), "temporal": temporal, "spatial": spatial,
        "decision": {"eligible_challengers": eligible, "best_development_challenger": winner,
            "final_model_fitted": final is not None, "promotion": "manual_review_and_new_independent_cohort_required",
            "rule": "Positive multiplicity-adjusted block-bootstrap lower bounds vs exposure and NB on both tasks"},
        "hyperparameters": {"poisson_boosting": {"max_iter": 100, "max_leaf_nodes": 7,
            "learning_rate": .05, "l2_regularization": 10., "early_stopping": False},
            "mixture": "logistic gate on inner holdout predictions; L2 .001; training-only count calibration"},
        "limitations": LIMITATIONS}
    return report, final

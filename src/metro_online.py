"""Predeclared monthly adaptation experiment on Omaha's original future cases.

This is sequential evaluation with newly matured labels, not a frozen holdout.
No imagery, GIS enrichment, cached neighborhood outcomes or observed Severity is
used as a predictor. It remains a noncommercial retrospective research experiment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, f1_score, mean_absolute_error, r2_score

from src.features import TABULAR

SEED = 878
HALF_LIFE_DAYS = 180
FEATURES = list(TABULAR) + ["Start_Lat", "Start_Lng"]


def mature_history(frame, origin):
    """Every outcome used at a forecast origin must already be complete."""
    return (frame.Start_Time.lt(origin) & frame.End_Time.lt(origin)).to_numpy()


def periods(frame, test_fraction=.2):
    if not 0 < test_fraction < 1 or len(frame) < 50:
        raise ValueError("Require at least 50 incidents and a proper test fraction")
    if not frame.Start_Time.is_monotonic_increasing or frame[["Start_Time", "End_Time"]].isna().any().any():
        raise ValueError("Incidents must have valid times sorted by start")
    if not frame.End_Time.gt(frame.Start_Time).all():
        raise ValueError("Every incident must finish after its start")
    cut = int(len(frame) * (1 - test_fraction))
    test = frame.iloc[cut:]
    groups = test.Start_Time.dt.to_period("M")
    result = []
    for month in sorted(groups.unique()):
        indices = test.index[groups.eq(month)].to_numpy()
        origin = max(month.start_time, test.Start_Time.iloc[0])
        result.append((origin, indices))
    return cut, result


def weights_at_origin(history, origin, half_life_days=HALF_LIFE_DAYS):
    if half_life_days <= 0 or not history.End_Time.lt(origin).all():
        raise ValueError("Only matured labels and a positive half-life are valid")
    age = (origin - history.Start_Time).dt.total_seconds().to_numpy() / 86400
    recency = np.maximum(np.exp2(-age / half_life_days), 1e-8)
    balanced = recency.copy()
    for level in sorted(history.Severity.unique()):
        selected = history.Severity.eq(level).to_numpy()
        balanced[selected] /= recency[selected].sum()
    balanced *= len(balanced) / balanced.sum()
    return balanced, recency * len(recency) / recency.sum()


def fit_at_origin(history, origin, iterations=150):
    from src.metro_challengers import MetroDesign
    if len(history) < 30 or history.Severity.nunique() < 2:
        raise ValueError("Insufficient matured history")
    transform = MetroDesign(FEATURES).fit(history)
    x = transform.transform(history)
    classification_weights, regression_weights = weights_at_origin(history, origin)
    classifier = HistGradientBoostingClassifier(max_iter=iterations, max_leaf_nodes=15,
        min_samples_leaf=40, learning_rate=.05, l2_regularization=10,
        early_stopping=False, random_state=SEED)
    regressor = HistGradientBoostingRegressor(max_iter=iterations, max_leaf_nodes=15,
        min_samples_leaf=40, learning_rate=.05, l2_regularization=10,
        early_stopping=False, random_state=SEED)
    classifier.fit(x, history.Severity.astype(int), sample_weight=classification_weights)
    regressor.fit(x, history.log_duration, sample_weight=regression_weights)
    return {"transform": transform, "classifier": classifier, "regressor": regressor,
            "mean_log": float(np.average(history.log_duration, weights=regression_weights)),
            "origin": str(origin), "training_rows": len(history)}


def predict(bundle, frame):
    x = bundle["transform"].transform(frame)
    return bundle["classifier"].predict(x), np.clip(bundle["regressor"].predict(x), 0, np.log1p(10080))


def metrics(frame, classes, logs):
    y = frame.Severity.astype(int).to_numpy()
    return {"rows": len(y), "balanced_accuracy": float(balanced_accuracy_score(y, classes)),
            "macro_f1": float(f1_score(y, classes, labels=[1, 2, 3, 4], average="macro", zero_division=0)),
            "accuracy": float(accuracy_score(y, classes)),
            "duration_mae_minutes": float(mean_absolute_error(frame.duration_min, np.expm1(logs))),
            "duration_rmse_minutes": float(np.sqrt(np.mean((frame.duration_min.to_numpy() - np.expm1(logs)) ** 2))),
            "duration_r2_log": float(r2_score(frame.log_duration, logs)),
            "per_class": classification_report(y, classes, labels=[1, 2, 3, 4], output_dict=True, zero_division=0)}


def block_intervals(frame, fixed, online, draws=500):
    groups = (np.floor(frame.Start_Lat.to_numpy() / .02).astype(int).astype(str) + np.full(len(frame), ":")
              + np.floor(frame.Start_Lng.to_numpy() / .02).astype(int).astype(str))
    unique = np.unique(groups)
    rng = np.random.default_rng(SEED)
    by_group = [np.flatnonzero(groups == label) for label in unique]
    deltas = []
    for _ in range(draws):
        indices = np.concatenate([by_group[i] for i in rng.integers(0, len(unique), len(unique))])
        y = frame.Severity.to_numpy()[indices]
        recalls = lambda p: np.mean([np.mean(p[indices][y == level] == level) for level in [1, 2, 3, 4] if np.any(y == level)])
        duration = frame.duration_min.to_numpy()[indices]
        deltas.append([recalls(online[0]) - recalls(fixed[0]),
            np.abs(duration - np.expm1(fixed[1][indices])).mean() - np.abs(duration - np.expm1(online[1][indices])).mean()])
    intervals = np.quantile(np.asarray(deltas), [.025, .975], axis=0)
    return {"draws": draws, "geographic_blocks": len(unique),
            "balanced_accuracy_difference95": intervals[:, 0].tolist(),
            "duration_mae_reduction_minutes95": intervals[:, 1].tolist(),
            "interpretation": "Positive favors monthly adaptation; intervals condition on fitted models and recorded test blocks"}


def run(frame, iterations=150, bootstrap_draws=500, fit_function=fit_at_origin):
    frame = frame.copy().reset_index(drop=True)
    for col in ["Start_Time", "End_Time"]:
        frame[col] = pd.to_datetime(frame[col], errors="raise")
    cut, windows = periods(frame)
    if ("ID" not in frame or frame.ID.isna().any() or frame.ID.duplicated().any()
            or not frame.Severity.isin([1, 2, 3, 4]).all()
            or not frame.duration_min.between(1, 10080).all()
            or not np.allclose(frame.log_duration, np.log1p(frame.duration_min))):
        raise ValueError("Require unique IDs and consistent four-class/duration targets")
    first = windows[0][0]
    baseline_history = frame.loc[mature_history(frame, first)]
    fixed_bundle = fit_function(baseline_history, first, iterations)
    held = frame.iloc[cut:].copy()
    fixed = predict(fixed_bundle, held)
    classes = np.empty(len(held), dtype=int)
    logs = np.empty(len(held), dtype=float)
    naive = np.empty(len(held), dtype=float)
    audit = []
    last_bundle = fixed_bundle
    for index, (origin, indices) in enumerate(windows):
        history = frame.loc[mature_history(frame, origin)]
        bundle = fixed_bundle if index == 0 else fit_function(history, origin, iterations)
        labels, durations = predict(bundle, frame.loc[indices])
        classes[indices - cut], logs[indices - cut] = labels, durations
        naive[indices - cut] = bundle["mean_log"]
        if not history.End_Time.max() < origin or frame.loc[indices].Start_Time.min() < origin:
            raise ValueError("Label-availability boundary violated")
        audit.append({"origin": str(origin), "training_rows": len(history), "latest_label_end": str(history.End_Time.max()),
            "test_rows": len(indices), "source_counts": history.Source.astype(str).value_counts().to_dict(),
            "training_class_counts": {str(k): int(v) for k, v in history.Severity.value_counts().items()}})
        last_bundle = bundle
        print(f"Online origin {origin}: {len(history)} mature labels; {len(indices)} evaluations", flush=True)
    result = {"schema_version": 1, "research_only": True, "commercial_eligible": False,
        "status": "complete", "protocol": "sequential_monthly_matured_label_updates",
        "rows": len(frame), "test_rows": len(held), "first_test": str(first), "last_test": str(held.Start_Time.max()),
        "test_id_sha256": hashlib.sha256("\n".join(held.ID.astype(str)).encode()).hexdigest(),
        "hyperparameters": {"iterations": iterations, "recency_half_life_days": HALF_LIFE_DAYS,
            "classification": "recency weights normalized within each training class", "selection": "fixed before this evaluation; no outer-test tuning"},
        "features": FEATURES, "fixed": metrics(held, *fixed), "online": metrics(held, classes, logs),
        "rolling_mean_log_baseline": {"duration_r2_log": float(r2_score(held.log_duration, naive)),
            "duration_mae_minutes": float(mean_absolute_error(held.duration_min, np.expm1(naive)))},
        "periods": audit, "comparison": block_intervals(held, fixed, (classes, logs), bootstrap_draws),
        "limitations": ["Sequential retraining consumes only earlier completed evaluation incidents. It is not a frozen 2019 holdout.",
            "The corpus and original future scores were already inspected; this is a development experiment requiring independent validation.",
            "The same original final 20% incidents are scored, but the information available to monthly models grows.",
            "Duration uses incident context without observed Severity; compare it to its matched fixed baseline, not severity-conditioned ablations.",
            "Recorded weather/road flags lack complete availability audit; this is retrospective, not a demonstrated live forecasting trial.",
            "Reporting-source labels and duration definitions drift; no injury or human-behavior prediction is claimed.",
            "Rare class supports and exploratory block intervals limit conclusions. No model-selection-adjusted significance is claimed.",
            "Geographic bootstrap does not capture temporal dependence or uncertainty from refitting the monthly models.",
            "Research-only noncommercial dataset and weights; not deployed in the independent safety engine."]}
    predictions = pd.DataFrame({"ID": held.ID.to_numpy(), "row_index": held.index, "fixed_class": fixed[0], "online_class": classes,
        "fixed_log_duration": fixed[1], "online_log_duration": logs})
    return result, predictions, last_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/processed/metro_features.parquet")
    parser.add_argument("--output", default="outputs/research/metro/online.json")
    parser.add_argument("--iterations", type=int, default=150)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--bootstrap-draws", type=int, default=500)
    args = parser.parse_args()
    if min(args.iterations, args.threads, args.bootstrap_draws) < 1:
        parser.error("Positive iteration, thread and bootstrap settings required")
    from threadpoolctl import threadpool_limits
    from safety.io import digest, now, write_json
    import joblib
    from src.metro_challengers import load_metro
    started = time.monotonic()
    code_hashes = {"online": digest(__file__), "design_dependency": digest(Path(__file__).with_name("metro_challengers.py"))}
    frame = load_metro(args.input)
    with threadpool_limits(limits=args.threads):
        result, predictions, bundle = run(frame, args.iterations, args.bootstrap_draws)
    result.update({"built_at": now(), "input_sha256": digest(args.input), "code_sha256": code_hashes["online"], "code_hashes": code_hashes,
                   "runtime_seconds": time.monotonic() - started})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(output.with_suffix(".predictions.parquet"), index=False)
    # This trusted local research artifact is never in a production upload list.
    joblib.dump(bundle, output.with_suffix(".joblib"))
    write_json(output, result)
    print(json.dumps({"artifact": str(output), "fixed": result["fixed"], "online": result["online"]}, indent=2))


if __name__ == "__main__":
    main()

"""Frozen Omaha four-class / duration challengers, preserving original test IDs.

This is a retrospective comparison: most NAIP imagery postdates the incidents.
No scores or model files belonging to the original paper or safety engine change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score, log_loss,
                             mean_absolute_error, precision_recall_fscore_support, r2_score)
from sklearn.neighbors import BallTree
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.features import CATEGORICAL, NEIGHBORHOOD, TABULAR

SEED = 878
CLASSES = np.array([1, 2, 3, 4])
EMB = [f"emb_{k}" for k in range(512)]
IMG_SCALARS = ["img_veg_frac", "img_impervious_frac", "img_water_frac", "img_ndvi_mean", "img_ndvi_std", "img_brightness"]
GIS_COLUMNS = [f"{name}_{radius}" for radius in (100, 250, 500)
               for name in ["road_km_per_km2", "intersections_per_km2", "building_frac", "parking_frac", "green_frac",
                            "water_frac", "commercial_frac", "residential_frac", "industrial_frac"]]
GIS_COLUMNS += ["road_class", "maxspeed", "lanes", "dist_highway_m", "is_highway"]
CLASSIFIERS = ("original_balanced_hgb", "regularized_balanced_hgb", "regularized_hgb", "balanced_logistic")
REGRESSORS = ("training_mean", "training_median", "source_mean", "source_median", "recent_source_mean", "recent_source_median",
              "original_squared_hgb", "regularized_squared_hgb", "absolute_hgb", "ridge", "recent_squared_hgb")
TRUSTED_MODEL_ROOT = Path(__file__).resolve().parents[1]/"outputs/research/metro/models"
HISTORY_REFERENCE_COLUMNS = ["ID", "Start_Time", "End_Time", "Start_Lat", "Start_Lng", "Severity", "log_duration", "is_night"]


def feature_sets():
    """Same five named feature ablations as src.models.feature_sets()."""
    image = IMG_SCALARS + [f"img_pca_{k}" for k in range(32)]
    return {"A_tabular": list(TABULAR), "B_tabular+gis": list(TABULAR)+GIS_COLUMNS,
            "C_imagery": image, "D_tabular+gis+imagery": list(TABULAR)+GIS_COLUMNS+image,
            "E_D+neighborhood": list(TABULAR)+GIS_COLUMNS+image+NEIGHBORHOOD}


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            value.update(chunk)
    return value.hexdigest()


def row_hash(frame, mask):
    return hashlib.sha256("\n".join(frame.loc[mask, "ID"].astype(str)).encode()).hexdigest()


def load_metro(path):
    frame = pd.read_parquet(path).reset_index(drop=True)
    for name in ["Start_Time", "End_Time"]:
        frame[name] = pd.to_datetime(frame[name], errors="raise")
    if not frame.Start_Time.is_monotonic_increasing or frame.ID.duplicated().any():
        raise ValueError("Original row order must be chronological with unique IDs; do not silently reorder/drop rows")
    if not frame.Severity.isin(CLASSES).all() or not frame.duration_min.between(1, 10080).all():
        raise ValueError("Unexpected targets in the frozen original metro table")
    if not (frame.End_Time > frame.Start_Time).all():
        raise ValueError("Incident end must follow start")
    if not np.allclose(frame.log_duration, np.log1p(frame.duration_min)):
        raise ValueError("Cached log-duration target is inconsistent")
    if not np.allclose((frame.End_Time-frame.Start_Time).dt.total_seconds()/60, frame.duration_min):
        raise ValueError("Duration and incident end disagree; label-availability embargo cannot be trusted")
    return frame


def frozen_split(frame, protocol="temporal", seed=SEED):
    """Keep the original positional 80/20 test set; embargo unavailable fit labels."""
    if protocol not in {"temporal", "spatial_future"} or len(frame) < 50:
        raise ValueError("Use temporal/spatial_future with at least 50 rows")
    n = len(frame); outer_cut = int(n*.8); inner_cut = int(outer_cut*.8)
    inner_start, outer_start = frame.Start_Time.iloc[inner_cut], frame.Start_Time.iloc[outer_cut]
    position = np.arange(n)
    inner = (position < inner_cut) & (frame.End_Time < inner_start).to_numpy()
    validation = (position >= inner_cut) & (position < outer_cut) & (frame.End_Time < outer_start).to_numpy()
    outer = (position < outer_cut) & (frame.End_Time < outer_start).to_numpy()
    test = position >= outer_cut
    # Tied boundary starts stay in the historic test set; training labels must still end earlier.
    groups = (np.floor(frame.Start_Lat.to_numpy()/.02).astype(int).astype(str)
              + np.char.add(":", np.floor(frame.Start_Lng.to_numpy()/.02).astype(int).astype(str)))
    if protocol == "spatial_future":
        bucket = np.array([int.from_bytes(hashlib.blake2b(f"{seed}:{g}".encode(), digest_size=4).digest(), "big") % 10 for g in groups])
        inner &= bucket < 6; validation &= (bucket >= 6) & (bucket < 8)
        outer &= bucket < 8; test &= bucket >= 8
    masks = {"inner_train": inner, "validation": validation, "outer_train": outer, "test": test}
    if any(m.sum() < 5 for m in masks.values()):
        raise ValueError("Frozen partition has insufficient support")
    metadata = {"original_test_rows": n-outer_cut, "original_test_id_sha256": row_hash(frame, position >= outer_cut),
                "inner_start": str(inner_start), "outer_test_start": str(outer_start),
                "inner_label_embargo": int(((position < inner_cut) & (frame.End_Time >= inner_start).to_numpy()).sum()),
                "outer_label_embargo": int(((position < outer_cut) & (frame.End_Time >= outer_start).to_numpy()).sum()),
                "counts": {key: int(mask.sum()) for key, mask in masks.items()},
                "id_sha256": {key: row_hash(frame, mask) for key, mask in masks.items()},
                "class_support": {key: {str(c): int((frame.Severity[mask] == c).sum()) for c in CLASSES} for key, mask in masks.items()},
                "spatial_cells": {key: len(np.unique(groups[mask])) for key, mask in masks.items()}}
    return masks, groups, metadata


def frozen_neighborhood(frame, fit_mask, radius_km=1.):
    """History from fit rows only and only after each reference incident ended."""
    indices = np.flatnonzero(fit_mask)
    if not len(indices):
        raise ValueError("Neighborhood reference partition is empty")
    coordinates = np.radians(frame[["Start_Lat", "Start_Lng"]].to_numpy())
    tree = BallTree(coordinates[indices], metric="haversine")
    starts, ends = frame.Start_Time.to_numpy(), frame.End_Time.to_numpy()
    severity, duration, night = frame.Severity.to_numpy(), frame.log_duration.to_numpy(), frame.is_night.to_numpy()
    output = np.full((len(frame), len(NEIGHBORHOOD)), np.nan)
    for begin in range(0, len(frame), 1000):
        neighbors = tree.query_radius(coordinates[begin:begin+1000], r=radius_km/6371.)
        for offset, positions in enumerate(neighbors):
            row = begin+offset; reference = indices[positions]
            reference = reference[ends[reference] < starts[row]]
            output[row, 0] = len(reference)
            if len(reference):
                output[row, 1:] = [severity[reference].mean(), (severity[reference] >= 3).mean(), duration[reference].mean(), night[reference].mean()]
    return pd.DataFrame(output, columns=NEIGHBORHOOD, index=frame.index)


class MetroDesign:
    """Train-only category vocabularies and imagery PCA, retaining NaNs for trees."""
    def __init__(self, columns, pca_components=32, seed=SEED):
        self.columns = list(dict.fromkeys(columns)); self.pca_components = pca_components; self.seed = seed

    def fit(self, frame):
        self.categorical = [c for c in self.columns if c in CATEGORICAL or c == "State"]
        self.numeric = [c for c in self.columns if c not in self.categorical]
        self.vocab = {c: sorted(frame[c].astype("string").fillna("unknown").unique().tolist()) for c in self.categorical}
        self.pca = None
        if any(c.startswith("img_pca_") for c in self.columns):
            emb = frame.reindex(columns=EMB).to_numpy(float)
            valid = np.isfinite(emb).all(axis=1) & frame.naip_year.notna().to_numpy()
            components = min(self.pca_components, int(valid.sum()), len(EMB))
            if components:
                self.pca = PCA(components, random_state=self.seed).fit(emb[valid])
        self.feature_names = self.numeric.copy()
        for c in self.categorical:
            self.feature_names.extend([f"{c}={v}" for v in self.vocab[c]]+[f"{c}=<unseen>"])
        return self

    def transform(self, frame):
        values = frame.reindex(columns=self.numeric).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).copy()
        image_columns = [c for c in self.numeric if c.startswith("img_pca_")]
        if image_columns:
            emb = frame.reindex(columns=EMB).to_numpy(float)
            valid = np.isfinite(emb).all(axis=1) & frame.naip_year.notna().to_numpy()
            projected = self.pca.transform(emb[valid]) if self.pca is not None and valid.any() else None
            for c in image_columns:
                k = int(c.rsplit("_", 1)[1]); values[c] = np.nan
                if projected is not None:
                    values.loc[valid, c] = projected[:, k] if k < projected.shape[1] else 0.
        arrays = [values.to_numpy(float)]
        for c in self.categorical:
            labels = frame[c].astype("string").fillna("unknown")
            arrays.append(np.column_stack([(labels == v).to_numpy(bool) for v in self.vocab[c]] + [(~labels.isin(self.vocab[c])).to_numpy(bool)]))
        return np.concatenate(arrays, axis=1)


def classifier(name, seed=SEED):
    if name == "original_balanced_hgb":
        return HistGradientBoostingClassifier(class_weight="balanced", max_iter=300, early_stopping=False, random_state=seed)
    if name == "regularized_balanced_hgb":
        return HistGradientBoostingClassifier(class_weight="balanced", max_iter=200, learning_rate=.04, max_leaf_nodes=15,
                    min_samples_leaf=50, l2_regularization=10., early_stopping=False, random_state=seed)
    if name == "regularized_hgb":
        return HistGradientBoostingClassifier(max_iter=200, learning_rate=.06, max_leaf_nodes=15, min_samples_leaf=50,
                    l2_regularization=10., early_stopping=False, random_state=seed)
    if name == "balanced_logistic":
        return make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(),
                             LogisticRegression(C=.1, class_weight="balanced", max_iter=600, random_state=seed))
    raise ValueError("Unknown fixed classifier recipe")


def probabilities(model, x):
    raw = model.predict_proba(x); p = np.full((len(x), 4), 1e-12)
    for index, label in enumerate(model.classes_):
        p[:, int(label)-1] = raw[:, index]
    return p/p.sum(axis=1, keepdims=True)


def temperature_probability(p, temperature):
    logits = np.log(np.clip(p, 1e-12, 1))/temperature
    logits -= logits.max(axis=1, keepdims=True)
    result = np.exp(logits)
    return result/result.sum(axis=1, keepdims=True)


def class_metrics(y, decision, probability=None):
    precision, recall, f1, support = precision_recall_fscore_support(y, decision, labels=CLASSES, zero_division=0)
    result = {"accuracy": float(accuracy_score(y, decision)), "balanced_accuracy": float(recall[support > 0].mean()),
              "macro_f1": float(f1_score(y, decision, labels=CLASSES, average="macro", zero_division=0)),
              "per_class": {str(label): {"precision": float(precision[i]), "recall": float(recall[i]), "f1": float(f1[i]), "support": int(support[i])}
                            for i, label in enumerate(CLASSES)}}
    if probability is not None:
        result["log_loss"] = float(log_loss(y, probability, labels=CLASSES))
    return result


def class_objective(y, decision):
    _, recall, f1, support = precision_recall_fscore_support(y, decision, labels=CLASSES, zero_division=0)
    return float(.5*(recall[support > 0].mean()+f1.mean()))


def fit_decision(y, probability):
    """Temperature via inner log-loss; decision multipliers via inner BA/macro-F1."""
    objective = lambda t: log_loss(y, temperature_probability(probability, np.exp(t)), labels=CLASSES)
    optimum = minimize_scalar(objective, bounds=(-2.3, 2.3), method="bounded")
    temperature = float(np.exp(optimum.x)) if optimum.success and objective(optimum.x) < objective(0.) else 1.
    p = temperature_probability(probability, temperature)
    weights = np.ones(4); low_support = [int(c) for c in CLASSES if (y == c).sum() < 5]
    score = class_objective(y, CLASSES[np.argmax(p, axis=1)])
    for _ in range(2):
        for c in CLASSES:
            if int(c) in low_support:
                continue
            best, best_score = weights[c-1], score
            for value in (.25, .5, 1., 2., 4.):
                candidate = weights.copy(); candidate[c-1] = value
                candidate_score = class_objective(y, CLASSES[np.argmax(p*candidate, axis=1)])
                if candidate_score > best_score + 1e-12:
                    best, best_score = value, candidate_score
            weights[c-1], score = best, best_score
    return {"temperature": temperature, "class_weights": weights.tolist(), "validation_objective": float(score),
            "low_support_classes_weights_frozen": low_support, "objective": "mean(balanced_accuracy, four_class_macro_f1)"}


def apply_decision(p, settings):
    calibrated = temperature_probability(p, settings["temperature"])
    return CLASSES[np.argmax(calibrated*np.asarray(settings["class_weights"]), axis=1)], calibrated


def fit_regression(name, x, frame, use_source=True, seed=SEED):
    recent = name.startswith("recent_")
    mask = (frame.Start_Time >= frame.Start_Time.max()-pd.Timedelta(days=365)).to_numpy() if recent else np.ones(len(frame), bool)
    if not mask.any():
        raise ValueError("Recent fit window is empty")
    y = frame.log_duration.to_numpy()[mask]; fit_frame = frame.iloc[np.flatnonzero(mask)]
    if name in {"training_mean", "training_median", "source_mean", "source_median", "recent_source_mean", "recent_source_median"}:
        reducer = np.median if "median" in name else np.mean
        by_source = {str(k): float(reducer(v.log_duration)) for k, v in fit_frame.groupby("Source", observed=True)} if use_source and "source" in name else {}
        return {"kind": "constant", "value": float(reducer(y)), "by_source": by_source, "fit_rows": int(mask.sum()), "recipe": name}
    if name == "ridge":
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True), StandardScaler(), Ridge(alpha=100.))
    elif name == "original_squared_hgb":
        model = HistGradientBoostingRegressor(max_iter=300, early_stopping=False, random_state=seed)
    elif name in {"regularized_squared_hgb", "absolute_hgb", "recent_squared_hgb"}:
        model = HistGradientBoostingRegressor(max_iter=200, learning_rate=.04, max_leaf_nodes=15, min_samples_leaf=50,
                    l2_regularization=10., loss="absolute_error" if name == "absolute_hgb" else "squared_error", early_stopping=False, random_state=seed)
    else:
        raise ValueError("Unknown fixed duration recipe")
    model.fit(x[mask], y)
    return {"kind": "learned", "model": model, "fit_rows": int(mask.sum()), "recipe": name}


def predict_regression(model, x, frame):
    if model["kind"] == "constant":
        if not model["by_source"]:
            return np.full(len(frame), model["value"])
        source = frame.get("Source", pd.Series("unknown", index=frame.index))
        return np.array([model["by_source"].get(str(value), model["value"]) for value in source])
    return model["model"].predict(x)


def bounded_duration(p):
    return np.clip(p, 0, np.log1p(10080))


def duration_metrics(y, p):
    prediction = bounded_duration(p)
    error = np.expm1(y)-np.expm1(prediction)
    return {"MAE_min": float(np.mean(np.abs(error))), "RMSE_min": float(np.sqrt(np.mean(error**2))),
            "R2_log": float(r2_score(y, prediction)), "MSE_log": float(np.mean((y-prediction)**2))}


def choose_duration_blend(y, predictions, objective="MSE_log", members=None):
    ordered = sorted(predictions, key=lambda name: duration_metrics(y, predictions[name])[objective])
    a, b = members or ordered[:2]
    weight = min(np.linspace(0, 1, 21), key=lambda w: duration_metrics(y, (1-w)*predictions[a]+w*predictions[b])[objective])
    return {"member_a": a, "member_b": b, "weight_b": float(weight), "objective": objective,
            "validation": duration_metrics(y, (1-weight)*predictions[a]+weight*predictions[b])}


def selection(frame, fit, validation, columns, severity_known=True, seed=SEED):
    design = MetroDesign(columns, seed=seed).fit(frame[fit])
    xfit, xval = design.transform(frame[fit]), design.transform(frame[validation])
    y = frame.Severity.to_numpy(); candidates = []
    for name in CLASSIFIERS:
        model = classifier(name, seed).fit(xfit, y[fit]); p = probabilities(model, xval)
        decision = fit_decision(y[validation], p); predicted, calibrated = apply_decision(p, decision)
        candidates.append({"recipe": name, "decision": decision, "validation": class_metrics(y[validation], predicted, calibrated),
                           "raw_validation": class_metrics(y[validation], CLASSES[p.argmax(axis=1)], p)})
    chosen = max(candidates, key=lambda row: row["decision"]["validation_objective"])["recipe"]
    # The coordinate challenger is labeled separately; it never contaminates pure C imagery ablations.
    location_design = MetroDesign(columns+["Start_Lat", "Start_Lng"], seed=seed).fit(frame[fit])
    location_model = classifier("regularized_balanced_hgb", seed).fit(location_design.transform(frame[fit]), y[fit])
    location_p = probabilities(location_model, location_design.transform(frame[validation])); location_decision = fit_decision(y[validation], location_p)
    location_labels, location_p = apply_decision(location_p, location_decision)
    duration_columns = columns+(["Severity"] if severity_known else [])
    rdesign = MetroDesign(duration_columns, seed=seed).fit(frame[fit]); rfit, rval = rdesign.transform(frame[fit]), rdesign.transform(frame[validation])
    regressions = {}; predictions = {}
    for name in REGRESSORS:
        model = fit_regression(name, rfit, frame[fit], "Source" in columns, seed)
        predictions[name] = predict_regression(model, rval, frame[validation])
        regressions[name] = {"validation": duration_metrics(frame.log_duration.to_numpy()[validation], predictions[name]), "fit_rows": model["fit_rows"]}
    duration_choices = {objective: choose_duration_blend(frame.log_duration.to_numpy()[validation], predictions, objective) for objective in ["MSE_log", "MAE_min"]}
    return {"selection_features": "D_tabular+gis+imagery", "classification_recipe": chosen, "classification_candidates": candidates,
            "coordinate_challenger": {"recipe": "regularized_balanced_hgb", "decision": location_decision, "validation": class_metrics(y[validation], location_labels, location_p)},
            "duration_context": "severity_known" if severity_known else "start_context", "duration_candidates": regressions, "duration_blends": duration_choices}


def paired_intervals(frame, groups, baseline_class, candidate_class, baseline_duration, candidate_duration, draws=200, seed=SEED):
    """Paired geographic-block intervals, exploratory and not selection adjusted."""
    unique, inverse = np.unique(groups, return_inverse=True)
    if len(unique) < 2 or draws < 2:
        return {"status": "insufficient_blocks_or_draws", "blocks": len(unique)}
    y = frame.Severity.to_numpy(); yd = frame.log_duration.to_numpy(); rng = np.random.default_rng(seed)
    samples = []
    for _ in range(draws):
        picks = rng.integers(0, len(unique), len(unique)); counts = np.bincount(picks, minlength=len(unique))
        idx = np.repeat(np.arange(len(frame)), counts[inverse])
        if not len(idx):
            continue
        samples.append([balanced_accuracy_score(y[idx], candidate_class[idx])-balanced_accuracy_score(y[idx], baseline_class[idx]),
                        f1_score(y[idx], candidate_class[idx], labels=CLASSES, average="macro", zero_division=0)-f1_score(y[idx], baseline_class[idx], labels=CLASSES, average="macro", zero_division=0),
                        duration_metrics(yd[idx], baseline_duration[idx])["MAE_min"]-duration_metrics(yd[idx], candidate_duration[idx])["MAE_min"],
                        duration_metrics(yd[idx], candidate_duration[idx])["R2_log"]-duration_metrics(yd[idx], baseline_duration[idx])["R2_log"]])
    ci = np.quantile(samples, [.025, .975], axis=0)
    names = ["balanced_accuracy_gain", "macro_f1_gain", "MAE_minutes_reduction", "R2_log_gain"]
    return {"status": "computed", "blocks": len(unique), "draws": draws,
            "interpretation": "Positive favors challenger; exploratory per-comparison intervals, not familywise/selection-adjusted",
            **{name: {"lower95": float(ci[0, i]), "upper95": float(ci[1, i])} for i, name in enumerate(names)}}


def predict_artifact(frame, artifact_path):
    """Replay a trusted local metro artifact; never load caller-supplied checkpoints.

    Inputs are enriched research rows (including supplied imagery/GIS when used),
    not arbitrary street addresses. Severity is required only for the explicitly
    severity-known duration task. E history is recomputed from a hashed fit-only
    reference sidecar; any supplied cached neighborhood features are discarded.
    """
    path = Path(artifact_path).resolve(); trusted = TRUSTED_MODEL_ROOT.resolve()
    if (path.parent.parent.parent != trusted or path.parent.parent.name not in {"temporal", "spatial_future"}
            or path.parent.name not in {"severity_known", "start_context"} or path.stem not in "ABCDE"
            or len(path.stem) != 1 or path.suffix != ".joblib" or not path.is_file()):
        raise ValueError("Only fixed trusted metro model artifacts are accepted")
    bundle = joblib.load(path)
    if not bundle.get("research_only") or bundle.get("commercial_eligible") is not False:
        raise ValueError("Metro artifact lacks its research-only/noncommercial declaration")
    data = frame.copy().reset_index(drop=True)
    if data.empty:
        raise ValueError("At least one enriched research row is required")
    if bundle["duration_context"] == "severity_known" and ("Severity" not in data or not data.Severity.isin(CLASSES).all()):
        raise ValueError("This matched duration model requires the observed four-class Severity")
    if set(bundle["feature_columns"]) & set(NEIGHBORHOOD):
        reference_path = path.with_suffix(".history.parquet")
        if not reference_path.is_file() or reference_path.resolve().parent != path.parent:
            raise ValueError("Trusted frozen history reference is missing")
        if digest(reference_path) != bundle.get("history_reference_sha256"):
            raise ValueError("Frozen history reference digest mismatch")
        reference = pd.read_parquet(reference_path)
        if row_hash(reference, np.ones(len(reference), bool)) != bundle["fit_id_sha256"]:
            raise ValueError("Frozen history reference IDs disagree with the fit partition")
        queries = data.reindex(columns=HISTORY_REFERENCE_COLUMNS).copy()
        queries["Start_Time"] = pd.to_datetime(queries.Start_Time, errors="raise")
        queries["End_Time"] = queries.Start_Time
        # Query outcome placeholders are never selected by the reference mask.
        for column in ["Severity", "log_duration", "is_night"]:
            queries[column] = 0.
        combined = pd.concat([reference, queries], ignore_index=True)
        mask = np.arange(len(combined)) < len(reference)
        history = frozen_neighborhood(combined, mask).iloc[len(reference):].reset_index(drop=True)
        data = data.drop(columns=NEIGHBORHOOD, errors="ignore").join(history)
    design = MetroDesign(bundle["classification_design"]["columns"])
    design.__dict__.update(bundle["classification_design"])
    labels, p = apply_decision(probabilities(bundle["classification_model"], design.transform(data)), bundle["classification_decision"])
    rd = MetroDesign(bundle["duration_design"]["columns"]); rd.__dict__.update(bundle["duration_design"])
    rx = rd.transform(data)
    predictions = {name: predict_regression(model, rx, data) for name, model in bundle["duration_models"].items()}
    duration = {}
    for objective, settings in bundle["duration_blends"].items():
        logs = bounded_duration((1-settings["weight_b"])*predictions[settings["member_a"]]+settings["weight_b"]*predictions[settings["member_b"]])
        if not np.isfinite(logs).all():
            raise ValueError("Nonfinite duration predictions")
        duration[objective] = {"log_duration": logs.tolist(), "minutes": np.expm1(logs).tolist()}
    if not np.isfinite(p).all():
        raise ValueError("Nonfinite severity probabilities")
    return {"research_only": True, "commercial_eligible": False, "artifact_sha256": digest(path),
            "duration_context": bundle["duration_context"], "snapshot_context": bundle["snapshot_context"],
            "severity_class": labels.tolist(), "severity_probabilities": p.tolist(), "duration_blends": duration,
            "limitations": ["Requires enriched retrospective research features; not a label-free street safety API",
                            "Severity-known duration explicitly conditions on the supplied observed severity",
                            "Source/imagery vintages and noncommercial restrictions are unchanged"]}


def run_protocol(frame, protocol, output_dir, severity_known=True, draws=200, seed=SEED):
    masks, groups, metadata = frozen_split(frame, protocol, seed)
    inner, validation, outer, test = (masks[k] for k in ["inner_train", "validation", "outer_train", "test"])
    fit_frame = frame.drop(columns=NEIGHBORHOOD, errors="ignore").join(frozen_neighborhood(frame, inner))
    outer_frame = frame.drop(columns=NEIGHBORHOOD, errors="ignore").join(frozen_neighborhood(frame, outer))
    selected = selection(fit_frame, inner, validation, feature_sets()["D_tabular+gis+imagery"], severity_known, seed)
    context = selected["duration_context"]; artifact_root = Path(output_dir)/"models"/protocol/context; artifact_root.mkdir(parents=True, exist_ok=True)
    report = {"protocol": protocol, "duration_context": context, "split": metadata, "selection": selected, "ablations": []}
    target = frame.log_duration.to_numpy(); severity = frame.Severity.to_numpy()
    for feature_name, columns in feature_sets().items():
        started = time.monotonic(); print(f"  {protocol} {context} {feature_name}", flush=True)
        inner_design = MetroDesign(columns, seed=seed).fit(fit_frame[inner])
        ix, iv = inner_design.transform(fit_frame[inner]), inner_design.transform(fit_frame[validation])
        selected_inner = classifier(selected["classification_recipe"], seed).fit(ix, severity[inner])
        rule = fit_decision(severity[validation], probabilities(selected_inner, iv))
        design = MetroDesign(columns, seed=seed).fit(outer_frame[outer]); ox, tx = design.transform(outer_frame[outer]), design.transform(outer_frame[test])
        baseline_cls = classifier("original_balanced_hgb", seed).fit(ox, severity[outer])
        best_cls = baseline_cls if selected["classification_recipe"] == "original_balanced_hgb" else classifier(selected["classification_recipe"], seed).fit(ox, severity[outer])
        baseline_p = probabilities(baseline_cls, tx); baseline_labels = CLASSES[baseline_p.argmax(axis=1)]
        chosen_labels, chosen_p = apply_decision(probabilities(best_cls, tx), rule)
        rcolumns = columns+(["Severity"] if severity_known else [])
        rd_inner = MetroDesign(rcolumns, seed=seed).fit(fit_frame[inner]); rix, riv = rd_inner.transform(fit_frame[inner]), rd_inner.transform(fit_frame[validation])
        rd_outer = MetroDesign(rcolumns, seed=seed).fit(outer_frame[outer]); rox, rtx = rd_outer.transform(outer_frame[outer]), rd_outer.transform(outer_frame[test])
        members = {choice[name] for choice in selected["duration_blends"].values() for name in ["member_a", "member_b"]} | {"original_squared_hgb"}
        inner_predictions, outer_predictions, outer_models = {}, {}, {}
        for name in sorted(members):
            inner_model = fit_regression(name, rix, fit_frame[inner], "Source" in columns, seed)
            outer_model = fit_regression(name, rox, outer_frame[outer], "Source" in columns, seed)
            inner_predictions[name] = predict_regression(inner_model, riv, fit_frame[validation])
            outer_predictions[name] = predict_regression(outer_model, rtx, outer_frame[test]); outer_models[name] = outer_model
        blends, blend_predictions = {}, {}
        for objective, initial in selected["duration_blends"].items():
            config = choose_duration_blend(target[validation], inner_predictions, objective, (initial["member_a"], initial["member_b"]))
            prediction = (1-config["weight_b"])*outer_predictions[config["member_a"]]+config["weight_b"]*outer_predictions[config["member_b"]]
            blend_predictions[objective] = prediction; blends[objective] = {**config, "test": duration_metrics(target[test], prediction)}
        artifact = artifact_root/f"{feature_name.split('_')[0]}.joblib"
        reference_hash = None
        if set(columns) & set(NEIGHBORHOOD):
            reference_path = artifact.with_suffix(".history.parquet")
            frame.loc[outer, HISTORY_REFERENCE_COLUMNS].to_parquet(reference_path, index=False)
            reference_hash = digest(reference_path)
        joblib.dump({"research_only": True, "commercial_eligible": False, "classification_recipe": selected["classification_recipe"],
                     "classification_model": best_cls, "classification_design": vars(design), "classification_decision": rule,
                     "duration_design": vars(rd_outer), "duration_models": outer_models, "duration_blends": blends,
                     "duration_context": context, "feature_columns": columns, "snapshot_context": "retrospective_postincident_imagery",
                     "fit_id_sha256": metadata["id_sha256"]["outer_train"], "history_reference_sha256": reference_hash}, artifact)
        row = {"features": feature_name, "artifact": str(artifact), "artifact_sha256": digest(artifact),
               "classification_baseline": class_metrics(severity[test], baseline_labels, baseline_p),
               "classification_challenger": class_metrics(severity[test], chosen_labels, chosen_p), "classification_decision": rule,
               "duration_baseline": duration_metrics(target[test], outer_predictions["original_squared_hgb"]),
               "duration_blends": blends, "duration_members_test": {name: duration_metrics(target[test], p) for name, p in outer_predictions.items()},
               "paired_intervals_mae_blend": paired_intervals(frame[test], groups[test], baseline_labels, chosen_labels,
                      outer_predictions["original_squared_hgb"], blend_predictions["MAE_min"], draws, seed),
               "seconds": time.monotonic()-started}
        # Archive predictions and IDs to make exact replay and paired comparisons reviewable.
        pd.DataFrame({"ID": frame.ID[test].to_numpy(), "severity_true": severity[test], "severity_baseline": baseline_labels,
                      "severity_challenger": chosen_labels, "log_duration_true": target[test],
                      "log_duration_baseline": bounded_duration(outer_predictions["original_squared_hgb"]),
                      "log_duration_mae_blend": bounded_duration(blend_predictions["MAE_min"]),
                      "log_duration_r2_blend": bounded_duration(blend_predictions["MSE_log"])}).to_parquet(artifact.with_suffix(".predictions.parquet"), index=False)
        report["ablations"].append(row)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/processed/metro_features.parquet")
    parser.add_argument("--output", default="outputs/research/metro/benchmark.json")
    parser.add_argument("--protocol", choices=["both", "temporal", "spatial_future"], default="both")
    parser.add_argument("--duration-context", choices=["severity_known", "start_context", "both"], default="severity_known")
    parser.add_argument("--bootstrap-draws", type=int, default=200)
    parser.add_argument("--threads", type=int, default=2); parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.threads < 1 or args.bootstrap_draws < 0:
        parser.error("threads must be positive and bootstrap draws nonnegative")
    from threadpoolctl import threadpool_limits
    frame = load_metro(args.input); output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "status": "running", "research_only": True, "commercial_eligible": False,
              "scope": "Original Omaha multimodal four-class impact severity and duration", "rows": len(frame),
              "input_sha256": digest(args.input), "code_sha256": digest(__file__), "config": vars(args),
              "config_sha256": hashlib.sha256(json.dumps(vars(args), sort_keys=True).encode()).hexdigest(),
              "image_vintage": {"postincident_year_rows": int((frame.naip_year > frame.Start_Time.dt.year).sum()),
                                "missing_year_rows": int(frame.naip_year.isna().sum()), "years": sorted(frame.naip_year.dropna().unique().astype(int).tolist())},
              "selection_policy": "Prespecified candidate recipes selected on inner validation D features; identical selected recipes applied across A–E, with per-ablation inner-only calibration/blend weights; outer refit never uses outer labels",
              "limitations": ["Previously examined corpus; old 80/20 test IDs preserved, not a newly untouched external test",
                  "Latest NAIP/OSM context is retrospective and often postdates incidents; no historical real-time availability claim",
                  "original_* means the matched legacy recipe with early-stopping, fit-boundary, preprocessing and GIS corrections; it does not reproduce the archived score exactly",
                  "Classification retains all four traffic-impact severity classes, not injury severity",
                  "Decision multipliers for inner-validation classes with fewer than five observations stay at one",
                  "Duration severity_known matches original observed-severity conditioning; start_context is a separate task",
                  "Mean/median/source constants operate on log(1+duration); recent recipes use a prespecified trailing 365-day fit window",
                  "Neighborhood outcomes come only from the fit partition and must end before each query start",
                  "Source-aware duration constants fall back to global constants for imagery-only C; no hidden Source predictor",
                  "Probability temperatures/decision rules transfer from inner fit to refitted outer models; no outer-label calibration",
                  "Spatial-forward held-out cells are unbuffered and differ from the paper's all-time five-fold spatial CV",
                  "Exploratory paired intervals are not multiple-comparison/selection adjusted",
                  "Noncommercial research data/models; no safety-stack promotion or causal behavior claims"], "runs": []}
    output.write_text(json.dumps(report, indent=2, allow_nan=False))
    protocols = ["temporal", "spatial_future"] if args.protocol == "both" else [args.protocol]
    contexts = [True, False] if args.duration_context == "both" else [args.duration_context == "severity_known"]
    with threadpool_limits(limits=args.threads):
        for protocol in protocols:
            for context in contexts:
                print(f"Selecting {protocol}, severity_known={context}", flush=True)
                report["runs"].append(run_protocol(frame, protocol, output.parent, context, args.bootstrap_draws, args.seed))
                output.write_text(json.dumps(report, indent=2, allow_nan=False))
    report["status"] = "complete"; output.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(str(output), flush=True)


if __name__ == "__main__":
    main()

"""Research-only, frozen-split comparison of boosting and small tabular networks.

US Accidents severity is reported traffic impact, not injury severity or driver
behavior. This module never writes safety snapshots or deployed model artifacts.
Run explicitly: python -m src.advanced_benchmark --rows 60000 --epochs 15
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import average_precision_score, log_loss, mean_absolute_error, r2_score, roc_auc_score

from src.features import ROAD_FLAGS

NUMERIC = ["Start_Lat", "Start_Lng", "year", "hour_sin", "hour_cos", "dow_sin", "dow_cos",
           "month_sin", "month_cos", "is_night", "is_weekend", "is_rush_hour",
           "Temperature(F)", "Visibility(mi)", "Precipitation(in)", "Wind_Speed(mph)", "Humidity(%)"] + ROAD_FLAGS
RAW_NUMERIC = [c for c in NUMERIC if c not in {"year", "is_weekend", "is_rush_hour"} and not c.endswith(("_sin", "_cos"))]
READ_COLUMNS = list(dict.fromkeys(RAW_NUMERIC + ["Start_Time", "Severity", "duration_min", "w", "Source", "weather_group"]))
MODEL_NAMES = ("hist_gradient_boosting", "residual_mlp", "soft_mixture_of_experts")


def prepare_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive predictors without reading cached target encodings or model scores."""
    d = frame.reindex(columns=READ_COLUMNS).copy()
    d["Start_Time"] = pd.to_datetime(d.Start_Time, errors="coerce")
    for c in ["Severity", "duration_min", "Start_Lat", "Start_Lng", "w"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if frame.get("w") is None:
        d["w"] = 1.
    valid = (d.Start_Time.notna() & d.Severity.isin([1, 2, 3, 4]) & d.duration_min.between(1, 10080)
             & d.Start_Lat.between(18, 72) & d.Start_Lng.between(-180, -60)
             & np.isfinite(d.w) & d.w.gt(0))
    d = d.loc[valid].sort_values("Start_Time", kind="stable").reset_index(drop=True)
    t = d.Start_Time.dt
    d["year"], d["is_weekend"] = t.year, (t.dayofweek >= 5).astype(float)
    d["is_rush_hour"] = ((t.dayofweek < 5) & (t.hour.between(7, 9) | t.hour.between(16, 18))).astype(float)
    for name, values, period in [("hour", t.hour, 24), ("dow", t.dayofweek, 7), ("month", t.month - 1, 12)]:
        d[name + "_sin"], d[name + "_cos"] = np.sin(values * 2*np.pi/period), np.cos(values * 2*np.pi/period)
    d["target_severe"] = d.Severity.ge(3).astype(int)
    d["target_duration"] = np.log1p(d.duration_min)
    return d


def sample_parquet(path, rows=60000, seed=878):
    """Exact deterministic uniform sample; project columns and bound batch memory."""
    parquet = pq.ParquetFile(path)
    chosen = np.sort(np.random.default_rng(seed).choice(parquet.metadata.num_rows,
                     min(rows, parquet.metadata.num_rows), replace=False))
    parts, offset = [], 0
    columns = [c for c in READ_COLUMNS if c in parquet.schema.names]
    for batch in parquet.iter_batches(batch_size=32768, columns=columns):
        end = offset + batch.num_rows
        local = chosen[np.searchsorted(chosen, offset):np.searchsorted(chosen, end)] - offset
        if len(local):
            parts.append(batch.take(local).to_pandas())
        offset = end
    if not parts:
        raise ValueError("No input records")
    return prepare_rows(pd.concat(parts, ignore_index=True))


def spatial_groups(frame, cell_degrees=.25):
    if not np.isfinite(cell_degrees) or cell_degrees <= 0:
        raise ValueError("Spatial cell size must be positive")
    lat = np.floor(frame.Start_Lat.to_numpy() / cell_degrees).astype(int)
    lng = np.floor(frame.Start_Lng.to_numpy() / cell_degrees).astype(int)
    return np.array([f"{a}:{b}" for a, b in zip(lat, lng)])


def time_boundaries(frame):
    ordered = pd.to_datetime(frame.Start_Time).sort_values()
    return ordered.iloc[int(len(frame)*.6)], ordered.iloc[int(len(frame)*.8)]


def split_rows(frame, protocol="temporal", seed=878, cell_degrees=.25):
    """60/20/20 time windows; spatial_future also holds out geography at every stage.

    Boundary timestamps are never shared. The strict protocol uses independent
    hash-selected train/validation/test cells within their respective time windows.
    Rows outside that intersection are deliberately excluded, never recycled.
    """
    if protocol not in {"temporal", "spatial_future"} or len(frame) < 20:
        raise ValueError("Use temporal/spatial_future with at least 20 records")
    timestamps = pd.to_datetime(frame.Start_Time)
    val_start, test_start = time_boundaries(frame)
    # Both heads use only labels known at the next stage's forecast origin.
    known_at = timestamps + pd.to_timedelta(frame.duration_min, unit="m")
    train = (timestamps < val_start).to_numpy(copy=True)
    validation = ((timestamps >= val_start) & (timestamps < test_start)).to_numpy(copy=True)
    test = (timestamps >= test_start).to_numpy(copy=True)
    train &= (known_at < val_start).to_numpy()
    validation &= (known_at < test_start).to_numpy()
    groups = spatial_groups(frame, cell_degrees)
    if protocol == "spatial_future":
        bucket = np.array([int.from_bytes(hashlib.blake2b(f"{seed}:{g}".encode(), digest_size=4).digest(), "big") % 10 for g in groups])
        train &= bucket < 6
        validation &= (bucket >= 6) & (bucket < 8)
        test &= bucket >= 8
    masks = {"train": train, "validation": validation, "test": test}
    if any(mask.sum() < 5 for mask in masks.values()):
        raise ValueError("Insufficient records in a frozen split; increase sample or change the preregistered split")
    return masks, groups


class TrainPreprocessor:
    """Train-fitted median/scaling, missingness indicators and categorical vocabularies."""
    def __init__(self, include_source=True):
        self.categorical = ["weather_group"] + (["Source"] if include_source else [])

    def fit(self, frame):
        values = frame.reindex(columns=NUMERIC).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
        self.median = values.median().fillna(0).to_numpy()
        filled = np.where(np.isfinite(values.to_numpy()), values.to_numpy(), self.median)
        self.mean = filled.mean(axis=0)
        self.scale = np.maximum(filled.std(axis=0), 1e-6)
        self.vocab = {c: sorted(frame[c].fillna("unknown").astype(str).unique().tolist()) for c in self.categorical}
        self.feature_names = NUMERIC + [c+"_missing" for c in NUMERIC]
        for c, values in self.vocab.items():
            self.feature_names += [f"{c}={v}" for v in values] + [f"{c}=<unseen>"]
        return self

    def transform(self, frame):
        values = frame.reindex(columns=NUMERIC).apply(pd.to_numeric, errors="coerce").to_numpy(float)
        missing = ~np.isfinite(values)
        filled = np.where(missing, self.median, values)
        arrays = [np.clip((filled-self.mean)/self.scale, -20, 20), missing.astype(float)]
        for c, vocab in self.vocab.items():
            series = frame[c].fillna("unknown").astype(str)
            arrays.append(np.column_stack([(series == v).to_numpy() for v in vocab] + [(~series.isin(vocab)).to_numpy()]))
        return np.concatenate(arrays, axis=1).astype(np.float32)


def make_network(features, kind="residual_mlp", width=48, experts=3):
    import torch
    from torch import nn
    if kind not in MODEL_NAMES[1:]:
        raise ValueError("Unknown neural architecture")

    class ResidualExpert(nn.Module):
        def __init__(self):
            super().__init__()
            self.input = nn.Sequential(nn.Linear(features, width), nn.LayerNorm(width), nn.SiLU())
            self.block = nn.Sequential(nn.Linear(width, width), nn.SiLU(), nn.Dropout(.1), nn.Linear(width, width))
            self.output = nn.Linear(width, 2)

        def forward(self, x):
            h = self.input(x)
            return self.output(h + self.block(h))

    class Network(nn.Module):
        def __init__(self):
            super().__init__()
            self.experts = nn.ModuleList([ResidualExpert() for _ in range(experts if kind == "soft_mixture_of_experts" else 1)])
            self.gate = nn.Sequential(nn.Linear(features, 24), nn.SiLU(), nn.Linear(24, experts)) if len(self.experts) > 1 else None

        def forward(self, x):
            outputs = torch.stack([expert(x) for expert in self.experts], dim=1)
            gates = torch.softmax(self.gate(x), dim=1) if self.gate else torch.ones((len(x), 1), device=x.device)
            # A probability mixture, not an inaccurately named average of logits.
            severity = (torch.sigmoid(outputs[:, :, 0]) * gates).sum(dim=1).clamp(1e-6, 1-1e-6)
            duration = (outputs[:, :, 1] * gates).sum(dim=1)
            return torch.stack([torch.logit(severity), duration], dim=1), gates

    return Network()


def neural_predict(model, x, duration_center=0., duration_scale=1.):
    import torch
    model.eval()
    outputs, gates = [], []
    with torch.no_grad():
        for start in range(0, len(x), 2048):
            out, gate = model(torch.from_numpy(x[start:start+2048]))
            outputs.append(out.numpy()); gates.append(gate.numpy())
    p = np.concatenate(outputs)
    return expit(p[:, 0]), p[:, 1]*duration_scale+duration_center, np.concatenate(gates).mean(axis=0)


def train_neural(x_train, y_train, duration_train, w_train, x_val, y_val, duration_val, w_val,
                 kind="residual_mlp", epochs=15, seed=878, width=48, threads=2):
    import torch
    from torch.nn import functional as F
    torch.set_num_threads(threads)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    model = make_network(x_train.shape[1], kind, width)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.01)
    center = float(np.average(duration_train, weights=w_train))
    scale = max(float(np.sqrt(np.average((duration_train-center)**2, weights=w_train))), .01)
    x = torch.from_numpy(x_train)
    y = torch.tensor(y_train, dtype=torch.float32)
    duration = torch.tensor((duration_train-center)/scale, dtype=torch.float32)
    weights = torch.tensor(w_train/np.mean(w_train), dtype=torch.float32)
    best, best_loss, best_epoch, history = None, float("inf"), 0, []
    rng = np.random.default_rng(seed)
    for epoch in range(epochs):
        model.train()
        order = rng.permutation(len(x_train))
        for start in range(0, len(order), 512):
            idx = order[start:start+512]
            prediction, gates = model(x[idx])
            per_row = F.binary_cross_entropy_with_logits(prediction[:, 0], y[idx], reduction="none")
            per_row += .5*F.smooth_l1_loss(prediction[:, 1], duration[idx], reduction="none")
            loss = (per_row*weights[idx]).sum()/weights[idx].sum()
            if gates.shape[1] > 1:
                loss = loss + .01*gates.shape[1]*(gates.mean(0)**2).sum()
            optimizer.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5.); optimizer.step()
        p, d, _ = neural_predict(model, x_val, center, scale)
        score = float(log_loss(y_val, np.clip(p, 1e-7, 1-1e-7), labels=[0, 1], sample_weight=w_val)
                      + .5*np.average(np.abs(d-duration_val)/scale, weights=w_val))
        history.append(score)
        if score < best_loss - 1e-5:
            best, best_loss, best_epoch = copy.deepcopy(model.state_dict()), score, epoch+1
        elif epoch+1-best_epoch >= 4:
            break
    if best is None:
        raise ValueError("Neural training did not produce a finite validation loss")
    model.load_state_dict(best)
    return model, center, scale, {"best_epoch": best_epoch, "validation_objective": history,
                                 "parameters": sum(p.numel() for p in model.parameters()), "device": "cpu"}


def fit_temperature(y, p, weights):
    logits = logit(np.clip(p, 1e-7, 1-1e-7))
    objective = lambda t: log_loss(y, expit(logits / np.exp(t)), labels=[0, 1], sample_weight=weights)
    fit = minimize_scalar(objective, bounds=(-2.3, 2.3), method="bounded")
    # Identity stays available when bounded optimization offers no improvement.
    return float(np.exp(fit.x)) if fit.success and objective(fit.x) < objective(0.) else 1.


def calibrated(p, temperature):
    return expit(logit(np.clip(p, 1e-7, 1-1e-7))/temperature)


def duration_to_minutes(log_duration):
    return np.expm1(np.clip(log_duration, 0, np.log1p(10080)))


def select_blend(validation_predictions, y, duration, weights):
    """Choose separate members and weights with the declared validation metric."""
    base = validation_predictions["hist_gradient_boosting"]
    cls_member = min(MODEL_NAMES[1:], key=lambda name: log_loss(y, validation_predictions[name][0], labels=[0, 1], sample_weight=weights))
    duration_member = min(MODEL_NAMES[1:], key=lambda name: mean_absolute_error(np.expm1(duration), duration_to_minutes(validation_predictions[name][1]), sample_weight=weights))
    nn_cls = validation_predictions[cls_member][0]
    nn_duration = validation_predictions[duration_member][1]
    candidates = np.linspace(0, 1, 21)
    alpha_cls = min(candidates, key=lambda a: log_loss(y, (1-a)*base[0]+a*nn_cls, labels=[0, 1], sample_weight=weights))
    alpha_duration = min(candidates, key=lambda a: mean_absolute_error(np.expm1(duration), duration_to_minutes((1-a)*base[1]+a*nn_duration), sample_weight=weights))
    return {"neural_member_severity": cls_member, "neural_member_duration": duration_member,
            "neural_weight_severity": float(alpha_cls), "neural_weight_duration": float(alpha_duration),
            "severity_selection_metric": "validation_log_loss", "duration_selection_metric": "validation_mae_minutes"}


def score_predictions(y, duration, probability, log_duration, weights):
    p = np.clip(probability, 1e-7, 1-1e-7)
    observed = np.expm1(duration)
    predicted = duration_to_minutes(log_duration)
    both = len(np.unique(y)) == 2
    return {"roc_auc": float(roc_auc_score(y, p, sample_weight=weights)) if both else None,
            "pr_auc": float(average_precision_score(y, p, sample_weight=weights)) if both else None,
            "brier": float(np.average((p-y)**2, weights=weights)),
            "log_loss": float(log_loss(y, p, labels=[0, 1], sample_weight=weights)),
            "duration_mae_minutes": float(mean_absolute_error(observed, predicted, sample_weight=weights)),
            "duration_r2_log": float(r2_score(duration, np.log1p(predicted), sample_weight=weights)) if len(y)>1 else None,
            "weighted_severe_prevalence": float(np.average(y, weights=weights)), "rows": len(y)}


def paired_block_intervals(y, duration, baseline, candidate, groups, weights, draws=200, seed=878):
    """Paired geographical-cluster bootstrap; positive delta favors candidate."""
    unique, inverse = np.unique(groups, return_inverse=True)
    if len(unique) < 2 or draws < 2:
        return {"status": "insufficient_blocks_or_draws", "blocks": len(unique)}
    p0, d0 = baseline; p1, d1 = candidate
    brier = (p0-y)**2 - (p1-y)**2
    duration_error = np.abs(np.expm1(duration)-np.expm1(np.clip(d0, 0, np.log1p(10080)))) - np.abs(np.expm1(duration)-np.expm1(np.clip(d1, 0, np.log1p(10080))))
    rng = np.random.default_rng(seed); samples = []
    for _ in range(draws):
        multiplicity = np.bincount(rng.integers(0, len(unique), len(unique)), minlength=len(unique))
        w = weights*multiplicity[inverse]
        samples.append([np.average(brier, weights=w), np.average(duration_error, weights=w)])
    intervals = np.quantile(samples, [.025, .975], axis=0)
    return {"status": "computed", "blocks": len(unique), "draws": draws, "unit": "geographical_cell",
            "interpretation": "Positive baseline-minus-candidate differences favor candidate; CI crossing zero is inconclusive",
            "brier_improvement": {"estimate": float(np.average(brier, weights=weights)), "lower95": float(intervals[0, 0]), "upper95": float(intervals[1, 0])},
            "duration_mae_improvement_minutes": {"estimate": float(np.average(duration_error, weights=weights)), "lower95": float(intervals[0, 1]), "upper95": float(intervals[1, 1])}}


def cohort_scores(frame, p, d):
    """Descriptive context cohorts; no driver traits or causal behavior inference."""
    result = {}
    for name in ["is_night", "is_rush_hour", "weather_group", "Source"]:
        groups = frame[name].fillna("unknown").astype(str)
        result[name] = {}
        for group in sorted(groups.unique()):
            mask = groups.eq(group).to_numpy()
            if mask.sum() >= 30:
                subset = frame.loc[mask]
                result[name][group] = score_predictions(subset.target_severe.to_numpy(), subset.target_duration.to_numpy(), p[mask], d[mask], subset.w.to_numpy())
    return result


def run_protocol(frame, protocol, include_source=True, epochs=15, iterations=200, bootstrap_draws=200, seed=878, width=48, threads=2, artifact_dir=None):
    masks, groups = split_rows(frame, protocol, seed)
    tr, va, te = (masks[k] for k in ("train", "validation", "test"))
    if len(np.unique(frame.target_severe[tr])) < 2:
        raise ValueError("Training split requires both impact-severity classes")
    prep = TrainPreprocessor(include_source).fit(frame[tr])
    xtr, xva, xte = (prep.transform(frame[m]) for m in (tr, va, te))
    y, duration, w = frame.target_severe.to_numpy(), frame.target_duration.to_numpy(), frame.w.to_numpy()
    predictions, rows = {}, []
    artifact_path = Path(artifact_dir)/f"{protocol}-{'with' if include_source else 'without'}-source" if artifact_dir else None
    if artifact_path:
        import joblib
        artifact_path.mkdir(parents=True, exist_ok=True)
        joblib.dump(vars(prep), artifact_path/"preprocessor.joblib")
    for name in MODEL_NAMES:
        started = time.monotonic(); details = {}
        if name == "hist_gradient_boosting":
            classifier = HistGradientBoostingClassifier(max_iter=iterations, learning_rate=.08, early_stopping=False, l2_regularization=1, random_state=seed)
            regressor = HistGradientBoostingRegressor(max_iter=iterations, learning_rate=.08, loss="absolute_error", early_stopping=False, l2_regularization=1, random_state=seed)
            classifier.fit(xtr, y[tr], sample_weight=w[tr]); regressor.fit(xtr, duration[tr], sample_weight=w[tr])
            vp, vd = classifier.predict_proba(xva)[:, 1], regressor.predict(xva)
            tp, td = classifier.predict_proba(xte)[:, 1], regressor.predict(xte)
        else:
            model, center, scale, details = train_neural(xtr, y[tr], duration[tr], w[tr], xva, y[va], duration[va], w[va], name, epochs, seed, width, threads)
            vp, vd, gate_val = neural_predict(model, xva, center, scale)
            tp, td, gate_test = neural_predict(model, xte, center, scale)
            if name == "soft_mixture_of_experts":
                details.update(expert_usage_validation=gate_val.tolist(), expert_usage_test=gate_test.tolist(), routing="dense learned soft probabilities; all experts evaluated")
        temperature = fit_temperature(y[va], vp, w[va])
        if artifact_path:
            if name == "hist_gradient_boosting":
                path = artifact_path/f"{name}.joblib"
                joblib.dump({"classification": classifier, "duration": regressor, "temperature": temperature,
                             "research_only": True, "commercial_eligible": False}, path)
            else:
                import torch
                path = artifact_path/f"{name}.pt"
                torch.save({"state_dict": model.state_dict(), "kind": name, "width": width, "features": xtr.shape[1],
                            "duration_center": center, "duration_scale": scale, "temperature": temperature,
                            "research_only": True, "commercial_eligible": False}, path)
            details["artifact"] = str(path)
        cp, ct = calibrated(vp, temperature), calibrated(tp, temperature)
        predictions[name] = ((cp, vd), (ct, td))
        row = {"model": name, "validation": score_predictions(y[va], duration[va], cp, vd, w[va]),
               "test": score_predictions(y[te], duration[te], ct, td, w[te]),
               "uncalibrated_test": score_predictions(y[te], duration[te], tp, td, w[te]),
               "temperature_fit_on_validation": temperature, "training_seconds": time.monotonic()-started, **details}
        rows.append(row)
    # Independent task choices; test performance never sets either member or weight.
    blend_config = select_blend({name: value[0] for name, value in predictions.items()}, y[va], duration[va], w[va])
    cls_name, duration_name = blend_config["neural_member_severity"], blend_config["neural_member_duration"]
    alpha_cls, alpha_duration = blend_config["neural_weight_severity"], blend_config["neural_weight_duration"]
    base_val, base_test = predictions[MODEL_NAMES[0]]
    blended = lambda index: ((1-alpha_cls)*predictions[MODEL_NAMES[0]][index][0]+alpha_cls*predictions[cls_name][index][0],
                             (1-alpha_duration)*predictions[MODEL_NAMES[0]][index][1]+alpha_duration*predictions[duration_name][index][1])
    blend_val, blend_test = blended(0), blended(1)
    predictions["validation_blend"] = (blend_val, blend_test)
    if artifact_path:
        (artifact_path/"blend.json").write_text(json.dumps({**blend_config, "research_only": True, "commercial_eligible": False}, indent=2))
    rows.append({"model": "validation_blend", **blend_config,
                 "validation": score_predictions(y[va], duration[va], *blend_val, w[va]),
                 "test": score_predictions(y[te], duration[te], *blend_test, w[te])})
    baseline_p = np.full(te.sum(), np.average(y[tr], weights=w[tr]))
    order = np.argsort(duration[tr]); sorted_duration, sorted_weights = duration[tr][order], w[tr][order]
    baseline_duration = sorted_duration[np.searchsorted(np.cumsum(sorted_weights), sorted_weights.sum()/2)]
    rows.append({"model": "training_prior", "test": score_predictions(y[te], duration[te], baseline_p, np.full(te.sum(), baseline_duration), w[te])})
    for row in rows:
        name = row["model"]
        if name not in predictions:
            continue
        test_predictions = predictions[name][1]
        row["paired_vs_boosting"] = paired_block_intervals(y[te], duration[te], base_test, test_predictions, groups[te], w[te], bootstrap_draws, seed)
        row["context_cohorts_test"] = cohort_scores(frame[te], *test_predictions)
    val_start, test_start = time_boundaries(frame)
    known_at = frame.Start_Time + pd.to_timedelta(frame.duration_min, unit="m")
    report = {"protocol": protocol, "source_feature": include_source, "predictors": prep.feature_names,
              "label_availability": {"assumption": "Impact and duration labels treated as known only after incident end",
                "validation_start": str(val_start), "test_start": str(test_start),
                "train_boundary_exclusions": int(((frame.Start_Time < val_start) & (known_at >= val_start)).sum()),
                "validation_boundary_exclusions": int(((frame.Start_Time >= val_start) & (frame.Start_Time < test_start) & (known_at >= test_start)).sum()),
                "exclusion_count_scope": "Full sampled time windows, before spatial filtering"},
              "split": {k: {"rows": int(m.sum()), "first": str(frame.Start_Time[m].min()), "last": str(frame.Start_Time[m].max()),
                             "spatial_cells": len(np.unique(groups[m])), "weighted_severe_prevalence": float(np.average(y[m], weights=w[m]))}
                        for k, m in masks.items()},
              "split_hash": hashlib.sha256(np.column_stack([tr, va, te]).tobytes()).hexdigest(), "models": rows,
              "selected_on_validation_log_loss": min(rows[:-1], key=lambda r: r["validation"]["log_loss"])["model"]}
    return report


def digest(path):
    checksum = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/processed/engine_rows.parquet")
    parser.add_argument("--out", default="outputs/research/advanced_benchmark.json")
    parser.add_argument("--rows", type=int, default=60000)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--bootstrap-draws", type=int, default=200)
    parser.add_argument("--protocol", choices=["both", "temporal", "spatial_future"], default="both")
    parser.add_argument("--source-ablation", choices=["both", "with", "without"], default="both")
    parser.add_argument("--seed", type=int, default=878)
    parser.add_argument("--width", type=int, default=48)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--artifact-dir", default="outputs/research/models")
    args = parser.parse_args()
    if min(args.rows, args.epochs, args.iterations, args.width, args.threads) < 1 or args.bootstrap_draws < 0:
        parser.error("Model/sample settings must be positive; bootstrap draws must be nonnegative")
    from threadpoolctl import threadpool_limits
    from importlib.metadata import version
    config = vars(args)
    frame = sample_parquet(args.input, args.rows, args.seed)
    protocols = ["temporal", "spatial_future"] if args.protocol == "both" else [args.protocol]
    ablations = [False, True] if args.source_ablation == "both" else [args.source_ablation == "with"]
    report = {"schema_version": 1, "research_only": True, "commercial_eligible": False,
              "dataset": "US Accidents legacy research cache; noncommercial licensing",
              "input_sha256": digest(args.input), "code_sha256": digest(__file__),
              "versions": {name: version(name) for name in ["numpy", "pandas", "scikit-learn", "torch"]},
              "config": config, "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
              "sample_rows": len(frame), "status": "running", "runs": [], "limitations": [
                  "Previously explored corpus: internal frozen test partitions, not a never-seen external validation dataset",
                  "Traffic-impact labels drift with reporting feeds and time; no injury-severity or crash-occurrence prediction",
                  "Weather/night/rush-hour/road context are observational proxies, not human behavior measurements or causal explanations",
                  "Validation is reused for early stopping, calibration and blend selection; no test-based model tuning",
                  "Historical weather and road annotations may not be available at real-time inference; feature availability requires audit",
                  "Spatial cells are held out without a buffer; adjacent-cell roads may remain correlated",
                  "US Accidents and its derived weights/models must remain outside the commercial safety engine",
                  "Uncertainty intervals resample geographic test blocks only; they omit training and dataset-selection uncertainty",
                  "Paired 95% intervals are exploratory per-comparison intervals, not familywise or model-selection-adjusted significance tests",
                  "No automatic model promotion or acquisition-readiness claim"]}
    output = Path(args.out); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False))
    with threadpool_limits(limits=args.threads):
        for protocol in protocols:
            for source in ablations:
                print(f"Running {protocol}, source_feature={source}, rows={len(frame)}", flush=True)
                report["runs"].append(run_protocol(frame, protocol, source, args.epochs, args.iterations, args.bootstrap_draws, args.seed, args.width, args.threads, args.artifact_dir))
                output = Path(args.out); output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, indent=2, allow_nan=False))
    report["status"] = "complete"
    output.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(str(args.out), flush=True)


if __name__ == "__main__":
    main()

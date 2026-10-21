"""Inference for trusted local, noncommercial traffic-impact research models.

No labels are required. Input outcomes and cached encodings are never predictors.
This module intentionally cannot load arbitrary user-supplied pickle/checkpoints.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import threading

import numpy as np
import pandas as pd

from src import advanced_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[1]
TRUSTED_MODEL_ROOT = ROOT / "outputs/research/models"
REPORT_PATH = ROOT / "outputs/research/advanced_benchmark.json"
VARIANTS = {f"{protocol}-{source}-source": (protocol, source == "with")
            for protocol in ("temporal", "spatial_future") for source in ("with", "without")}
DEFAULT_ARTIFACT_DIR = TRUSTED_MODEL_ROOT / "temporal-with-source"
ALLOWED_FIELDS = tuple(dict.fromkeys(["Start_Time"] + benchmark.RAW_NUMERIC + ["Source", "weather_group"]))
_ARTIFACT_FILES = ("preprocessor.joblib", "hist_gradient_boosting.joblib", "residual_mlp.pt", "soft_mixture_of_experts.pt", "blend.json")
_LOCK = threading.Lock()


def inference_frame(records):
    """Same deterministic input/calendar transform as the benchmark, without labels."""
    if not isinstance(records, list) or not records or len(records) > 1000 or any(not isinstance(r, dict) for r in records):
        raise ValueError("Provide a nonempty list of at most 1000 incident objects")
    timestamps = []
    for index, row in enumerate(records):
        if not isinstance(row.get("Start_Time"), (str, datetime, pd.Timestamp, np.datetime64)):
            raise ValueError(f"Incident {index}: Start_Time must be a local date/time string or datetime")
        try:
            timestamp = pd.Timestamp(row.get("Start_Time"))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"Incident {index}: Start_Time must be a valid local incident timestamp") from exc
        if pd.isna(timestamp) or timestamp.tzinfo is not None:
            raise ValueError(f"Incident {index}: provide timezone-naive local Start_Time, matching the training data")
        timestamps.append(timestamp)
    frame = pd.DataFrame(records).reindex(columns=ALLOWED_FIELDS).copy()
    frame["Start_Time"] = timestamps
    for column in benchmark.RAW_NUMERIC:
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame[column].notna() & (values.isna() | np.isinf(values))
        if invalid.any():
            raise ValueError(f"{column} must contain finite numbers or null")
        frame[column] = values.astype(float)
    if not frame.Start_Lat.between(18, 72).all() or not frame.Start_Lng.between(-180, -60).all():
        raise ValueError("Every incident needs finite US-domain Start_Lat (18–72) and Start_Lng (−180–−60)")
    for column in benchmark.ROAD_FLAGS + ["is_night"]:
        if not frame[column].dropna().isin([0, 1]).all():
            raise ValueError(f"{column} must be 0, 1 or null")
    for column in ["Source", "weather_group"]:
        if any(not isinstance(value, str) or len(value) > 100 for value in frame[column].dropna()):
            raise ValueError(f"{column} must be a string of at most 100 characters or null")
    t = frame.Start_Time.dt
    frame["year"], frame["is_weekend"] = t.year, (t.dayofweek >= 5).astype(float)
    frame["is_rush_hour"] = ((t.dayofweek < 5) & (t.hour.between(7, 9) | t.hour.between(16, 18))).astype(float)
    for name, values, period in [("hour", t.hour, 24), ("dow", t.dayofweek, 7), ("month", t.month-1, 12)]:
        frame[name+"_sin"], frame[name+"_cos"] = np.sin(values*2*np.pi/period), np.cos(values*2*np.pi/period)
    return frame


def _trusted_directory(artifact_dir):
    path = Path(artifact_dir).resolve()
    trusted = TRUSTED_MODEL_ROOT.resolve()
    if path.parent != trusted or path.name not in VARIANTS:
        raise ValueError("Only the four fixed local research artifact directories are allowed")
    for filename in _ARTIFACT_FILES:
        candidate = path/filename
        if candidate.resolve().parent != path:
            raise ValueError(f"Trusted research artifact escapes its directory: {filename}")
        if not candidate.is_file():
            raise FileNotFoundError(f"Trusted research artifact has not been built: {filename}")
    return path


def _fingerprint(path):
    files = [REPORT_PATH, Path(benchmark.__file__), *(path/name for name in _ARTIFACT_FILES)]
    return tuple((str(file), file.stat().st_mtime_ns, file.stat().st_size) for file in files)


@lru_cache(maxsize=4)
def _load_bundle(path_string, fingerprint):
    """Caller must validate the path first; cache invalidates when artifacts change."""
    import joblib
    import torch
    path = Path(path_string)
    report = json.loads(REPORT_PATH.read_text())
    if report.get("status") != "complete" or not report.get("research_only") or report.get("commercial_eligible") is not False:
        raise ValueError("Only a completed, explicitly noncommercial research report may supply inference")
    if benchmark.digest(benchmark.__file__) != report.get("code_sha256"):
        raise ValueError("Benchmark code changed after the recorded model build; verify a matching inference bundle")
    protocol, source = VARIANTS[path.name]
    matches = [run for run in report["runs"] if run["protocol"] == protocol and run["source_feature"] == source]
    if len(matches) != 1:
        raise ValueError("Research report does not uniquely identify this model protocol")
    run = matches[0]
    artifact_hashes = {name: benchmark.digest(path/name) for name in _ARTIFACT_FILES}
    preprocessor = benchmark.TrainPreprocessor(source)
    preprocessor.__dict__.update(joblib.load(path/"preprocessor.joblib"))
    if preprocessor.feature_names != run["predictors"]:
        raise ValueError("Preprocessing feature schema does not match the recorded benchmark")
    boost = joblib.load(path/"hist_gradient_boosting.joblib")
    blend = json.loads((path/"blend.json").read_text())
    for value in (boost, blend):
        if not value.get("research_only") or value.get("commercial_eligible") is not False:
            raise ValueError("Artifact is missing the required research-use declaration")
    ensemble_row = next(r for r in run["models"] if r["model"] == "validation_blend")
    for key in ["neural_member_severity", "neural_member_duration", "neural_weight_severity", "neural_weight_duration"]:
        if blend.get(key) != ensemble_row.get(key):
            raise ValueError("Blend settings disagree with the recorded validation selection")
    if any(not 0 <= blend[key] <= 1 for key in ["neural_weight_severity", "neural_weight_duration"]):
        raise ValueError("Invalid blend weights")
    networks = {}; temperatures = {"hist_gradient_boosting": boost["temperature"]}
    # Validate every checkpoint, even when a validation-selected weight is zero.
    for kind in benchmark.MODEL_NAMES[1:]:
        saved = torch.load(path/f"{kind}.pt", weights_only=True, map_location="cpu")
        if saved.get("kind") != kind or saved.get("features") != len(preprocessor.feature_names):
            raise ValueError("Neural checkpoint feature/architecture mismatch")
        if not saved.get("research_only") or saved.get("commercial_eligible") is not False:
            raise ValueError("Neural checkpoint is missing the research-use declaration")
        model = benchmark.make_network(saved["features"], kind, saved["width"])
        model.load_state_dict(saved["state_dict"], strict=True)
        model.eval()
        networks[kind] = (model, saved["duration_center"], saved["duration_scale"])
        temperatures[kind] = saved["temperature"]
    for name, temperature in temperatures.items():
        expected = next(r["temperature_fit_on_validation"] for r in run["models"] if r["model"] == name)
        if not np.isfinite(temperature) or temperature <= 0 or temperature != expected:
            raise ValueError("Saved calibration temperature does not match the recorded validation fit")
    provenance = {"variant": path.name, "protocol": protocol, "source_feature": source,
                  "model": "validation_blend", "blend": blend, "temperatures": temperatures,
                  "dataset": report["dataset"], "training_data_sha256": report["input_sha256"],
                  "benchmark_code_sha256": report["code_sha256"], "benchmark_config_sha256": report["config_sha256"],
                  "benchmark_report_sha256": benchmark.digest(REPORT_PATH), "artifact_sha256": artifact_hashes,
                  "versions_at_training": report["versions"], "windows": run["split"],
                  "label_availability": run["label_availability"], "source_feature_names": preprocessor.feature_names}
    identity = json.dumps({"variant": path.name, "artifacts": artifact_hashes, "config": report["config_sha256"]}, sort_keys=True)
    provenance["model_identity_sha256"] = hashlib.sha256(identity.encode()).hexdigest()
    return {"preprocessor": preprocessor, "boost": boost, "blend": blend, "networks": networks,
            "temperatures": temperatures, "provenance": provenance, "limitations": report["limitations"]}


def predict_incidents(records, artifact_dir=DEFAULT_ARTIFACT_DIR):
    """Predict traffic impact conditional on a reported incident, not crash risk.

    The optional artifact_dir is a developer configuration, never a request field.
    All supplied outcome/derived fields are ignored and reported, not consumed.
    """
    frame = inference_frame(records)
    path = _trusted_directory(artifact_dir)
    from threadpoolctl import threadpool_limits
    import torch
    # Serialize CPU model access; do not let per-request thread pools multiply.
    with _LOCK, threadpool_limits(limits=2):
        torch.set_num_threads(2)
        bundle = _load_bundle(str(path), _fingerprint(path))
        prep, blend, boost = bundle["preprocessor"], bundle["blend"], bundle["boost"]
        x = prep.transform(frame)
        base_p = benchmark.calibrated(boost["classification"].predict_proba(x)[:, 1], bundle["temperatures"]["hist_gradient_boosting"])
        base_duration = boost["duration"].predict(x)
        neural = {}
        for name in {blend["neural_member_severity"], blend["neural_member_duration"]}:
            model, center, scale = bundle["networks"][name]
            p, duration, _ = benchmark.neural_predict(model, x, center, scale)
            neural[name] = (benchmark.calibrated(p, bundle["temperatures"][name]), duration)
        a, b = blend["neural_weight_severity"], blend["neural_weight_duration"]
        probability = (1-a)*base_p+a*neural[blend["neural_member_severity"]][0]
        log_duration = (1-b)*base_duration+b*neural[blend["neural_member_duration"]][1]
        minutes = benchmark.duration_to_minutes(log_duration)
    if not np.isfinite(probability).all() or not np.isfinite(minutes).all():
        raise ValueError("Model produced nonfinite predictions; inference is unavailable")
    train = bundle["provenance"]["windows"]["train"]
    test_end = pd.Timestamp(bundle["provenance"]["windows"]["test"]["last"])
    predictions = []
    for index, row in frame.iterrows():
        missing = [c for c in benchmark.RAW_NUMERIC if pd.isna(row[c])]
        missing += [c for c in prep.categorical if pd.isna(row[c])]
        unseen = {c: str(row[c]) for c in prep.categorical if not pd.isna(row[c]) and str(row[c]) not in prep.vocab[c]}
        timestamp = row.Start_Time
        predictions.append({"index": int(index), "Start_Time": str(timestamp),
                            "severe_traffic_impact_probability": float(np.clip(probability[index], 0, 1)),
                            "predicted_impact_duration_minutes": float(minutes[index]),
                            "missing_feature_count": len(missing), "missing_features": missing,
                            "unseen_categories": unseen,
                            "ignored_input_fields": sorted(set(records[index])-set(ALLOWED_FIELDS)),
                            "outside_training_time_range": bool(timestamp < pd.Timestamp(train["first"]) or timestamp > pd.Timestamp(train["last"])),
                            "after_evaluation_time_range": bool(timestamp > test_end)})
    return {"research_only": True, "commercial_eligible": False,
            "prediction_scope": "Reported traffic-impact severity >=3 and impact duration, conditional on a reported incident; not injury severity or crash occurrence",
            "predictions": predictions, "provenance": copy.deepcopy(bundle["provenance"]),
            "limitations": ["Research-only estimates from noncommercial US Accidents data; never use as commercial safety-engine outputs",
                            "Source-feed and time drift materially affect these labels and predictions",
                            "No driver behavior, causality, individual safety or injury prediction is implied",
                            "Missing inputs use training-only preprocessing; completeness does not establish real-time feature availability",
                            "Timezone-naive local incident timestamps match the source convention; no timezone conversion is inferred",
                            "Dates outside the recorded training/evaluation windows are extrapolation, with no validated future accuracy",
                            "Impact duration is bounded to 0–10080 minutes, exactly as in reported evaluation"] + bundle["limitations"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON list, or object containing records, without outcome labels")
    parser.add_argument("--output", help="Output JSON path; defaults to stdout")
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="temporal-with-source")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.input).read_text())
        result = predict_incidents(payload.get("records") if isinstance(payload, dict) else payload, TRUSTED_MODEL_ROOT/args.variant)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    serialized = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(serialized+"\n")
    else:
        print(serialized)


if __name__ == "__main__":
    main()

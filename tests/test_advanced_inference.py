"""Tiny trusted-bundle fixtures; no real dataset or training workload required."""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from src import advanced_benchmark as benchmark
from src import advanced_inference as inference


def records(n=40):
    return [{"Start_Time": str(t), "Start_Lat": 41.2, "Start_Lng": -95.9,
             "is_night": i % 2, "Source": "Source1", "weather_group": "clear",
             "Temperature(F)": 60.+i, "Severity": 2+i % 2, "duration_min": 15.+i}
            for i, t in enumerate(pd.date_range("2020-01-01", periods=n, freq="h"))]


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    torch.set_num_threads(1); torch.manual_seed(33)
    root = tmp_path/"models"; path = root/"temporal-with-source"; path.mkdir(parents=True)
    frame = benchmark.prepare_rows(pd.DataFrame(records()))
    prep = benchmark.TrainPreprocessor().fit(frame)
    x = prep.transform(frame)
    y = frame.target_severe.to_numpy(); d = frame.target_duration.to_numpy()
    classifier = HistGradientBoostingClassifier(max_iter=2, min_samples_leaf=5, early_stopping=False).fit(x, y)
    regressor = HistGradientBoostingRegressor(max_iter=2, min_samples_leaf=5, early_stopping=False).fit(x, d)
    joblib.dump(vars(prep), path/"preprocessor.joblib")
    joblib.dump({"classification": classifier, "duration": regressor, "temperature": 1.3,
                 "research_only": True, "commercial_eligible": False}, path/"hist_gradient_boosting.joblib")
    temperatures = {"hist_gradient_boosting": 1.3, "residual_mlp": 1.7, "soft_mixture_of_experts": 2.1}
    neural = {}
    for kind in benchmark.MODEL_NAMES[1:]:
        model = benchmark.make_network(x.shape[1], kind, width=8)
        neural[kind] = model
        torch.save({"state_dict": model.state_dict(), "kind": kind, "width": 8, "features": x.shape[1],
                    "duration_center": 3., "duration_scale": .5, "temperature": temperatures[kind],
                    "research_only": True, "commercial_eligible": False}, path/f"{kind}.pt")
    blend = {"neural_member_severity": "residual_mlp", "neural_member_duration": "soft_mixture_of_experts",
             "neural_weight_severity": .35, "neural_weight_duration": .6,
             "research_only": True, "commercial_eligible": False}
    (path/"blend.json").write_text(json.dumps(blend))
    report = {"status": "complete", "research_only": True, "commercial_eligible": False,
              "code_sha256": benchmark.digest(benchmark.__file__), "input_sha256": "0"*64,
              "config_sha256": "1"*64, "dataset": "Synthetic unit-test fixture", "versions": {}, "limitations": [],
              "runs": [{"protocol": "temporal", "source_feature": True, "predictors": prep.feature_names,
                        "label_availability": {}, "split": {"train": {"first": "2020-01-01", "last": "2020-01-02"},
                                                               "test": {"first": "2020-01-03", "last": "2020-01-04"}},
                        "models": [{"model": name, "temperature_fit_on_validation": temp} for name, temp in temperatures.items()]
                        + [{"model": "validation_blend", **blend}]}]}
    report_path = tmp_path/"report.json"; report_path.write_text(json.dumps(report))
    monkeypatch.setattr(inference, "TRUSTED_MODEL_ROOT", root)
    monkeypatch.setattr(inference, "REPORT_PATH", report_path)
    inference._load_bundle.cache_clear()
    yield path, prep, classifier, regressor, neural, temperatures
    inference._load_bundle.cache_clear()


def test_inference_calendar_and_matrix_match_training_without_labels():
    inputs = records()
    train = benchmark.prepare_rows(pd.DataFrame(inputs))
    clean = [{k: v for k, v in r.items() if k not in {"Severity", "duration_min"}} for r in inputs]
    transformed = inference.inference_frame(clean)
    for column in benchmark.NUMERIC:
        np.testing.assert_allclose(train[column], transformed[column], equal_nan=True)
    prep = benchmark.TrainPreprocessor().fit(train)
    np.testing.assert_array_equal(prep.transform(train), prep.transform(transformed))


def test_saved_temperatures_and_separate_heads_reproduce_direct_blend(bundle):
    path, prep, classifier, regressor, neural, temps = bundle
    inputs = records(3)
    prediction = inference.predict_incidents(inputs, path)
    x = prep.transform(inference.inference_frame(inputs))
    base_p = benchmark.calibrated(classifier.predict_proba(x)[:, 1], temps["hist_gradient_boosting"])
    npred, _, _ = benchmark.neural_predict(neural["residual_mlp"], x, 3., .5)
    _, ndur, _ = benchmark.neural_predict(neural["soft_mixture_of_experts"], x, 3., .5)
    expected_p = .65*base_p+.35*benchmark.calibrated(npred, temps["residual_mlp"])
    expected_duration = benchmark.duration_to_minutes(.4*regressor.predict(x)+.6*ndur)
    np.testing.assert_allclose([r["severe_traffic_impact_probability"] for r in prediction["predictions"]], expected_p, rtol=1e-6)
    np.testing.assert_allclose([r["predicted_impact_duration_minutes"] for r in prediction["predictions"]], expected_duration, rtol=1e-6)
    assert prediction["research_only"] and not prediction["commercial_eligible"]
    assert len(prediction["provenance"]["model_identity_sha256"]) == 64


def test_outcomes_and_cached_predictions_cannot_change_inference(bundle):
    path = bundle[0]
    a = records(1)
    b = [{**a[0], "Severity": 4, "duration_min": 99999, "enc_severe": 1., "p_severe": 1., "hour": 22, "year": 2099}]
    first, second = [inference.predict_incidents(value, path)["predictions"][0] for value in [a, b]]
    assert first["severe_traffic_impact_probability"] == second["severe_traffic_impact_probability"]
    assert first["predicted_impact_duration_minutes"] == second["predicted_impact_duration_minutes"]
    assert set(second["ignored_input_fields"]) >= {"Severity", "duration_min", "enc_severe", "p_severe", "hour", "year"}


def test_missing_unseen_and_future_inputs_are_reported(bundle):
    result = inference.predict_incidents([{"Start_Time": "2026-09-29 15:00:00", "Start_Lat": 41.2,
                 "Start_Lng": -95.9, "Source": "new-feed"}], bundle[0])["predictions"][0]
    assert result["missing_feature_count"] > 10
    assert result["unseen_categories"] == {"Source": "new-feed"}
    assert result["outside_training_time_range"] and result["after_evaluation_time_range"]
    assert 0 <= result["severe_traffic_impact_probability"] <= 1
    assert 0 <= result["predicted_impact_duration_minutes"] <= 10080.000001


def test_response_metadata_cannot_mutate_cached_model_configuration(bundle):
    first = inference.predict_incidents(records(1), bundle[0])
    expected = first["predictions"][0]["predicted_impact_duration_minutes"]
    first["provenance"]["blend"]["neural_weight_duration"] = 99
    second = inference.predict_incidents(records(1), bundle[0])
    assert second["predictions"][0]["predicted_impact_duration_minutes"] == expected
    assert second["provenance"]["blend"]["neural_weight_duration"] == .6


@pytest.mark.parametrize("record", [
    {"Start_Time": "not a time", "Start_Lat": 41., "Start_Lng": -96.},
    {"Start_Time": 20260101, "Start_Lat": 41., "Start_Lng": -96.},
    {"Start_Time": "2020-01-01T00:00:00Z", "Start_Lat": 41., "Start_Lng": -96.},
    {"Start_Time": "2020-01-01", "Start_Lat": 100., "Start_Lng": -96.},
    {"Start_Time": "2020-01-01", "Start_Lat": 41., "Start_Lng": -96., "is_night": 2},
    {"Start_Time": "2020-01-01", "Start_Lat": 41., "Start_Lng": -96., "Temperature(F)": "hot"},
])
def test_invalid_inputs_fail_before_loading_models(record):
    with pytest.raises(ValueError):
        inference.inference_frame([record])


def test_arbitrary_and_escaping_checkpoint_directories_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="fixed local"):
        inference.predict_incidents(records(1), tmp_path)


def test_tampered_blend_does_not_silently_override_validation_selection(bundle):
    path = bundle[0]
    blend = json.loads((path/"blend.json").read_text()); blend["neural_weight_duration"] = .99
    (path/"blend.json").write_text(json.dumps(blend))
    with pytest.raises(ValueError, match="Blend settings disagree"):
        inference.predict_incidents(records(1), path)


def test_missing_bundle_is_an_unavailable_artifact_not_bad_incident(bundle):
    path = bundle[0]
    (path / "blend.json").rename(path / "saved-blend.json")
    with pytest.raises(FileNotFoundError, match="has not been built"):
        inference.predict_incidents(records(1), path)


def test_cli_reads_label_free_json_and_writes_provenance(bundle, monkeypatch, tmp_path):
    inputs = [{k: v for k, v in row.items() if k not in {"Severity", "duration_min"}} for row in records(2)]
    source = tmp_path/"incidents.json"; output = tmp_path/"predictions.json"
    source.write_text(json.dumps({"records": inputs}))
    monkeypatch.setattr("sys.argv", ["advanced_inference", "--input", str(source), "--output", str(output)])
    inference.main()
    result = json.loads(output.read_text())
    assert len(result["predictions"]) == 2 and result["provenance"]["variant"] == "temporal-with-source"

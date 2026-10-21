"""Small synthetic checks; no expensive research experiment or cache mutation."""
import numpy as np
import pandas as pd
import pytest

from src.advanced_benchmark import (TrainPreprocessor, calibrated, fit_temperature, make_network,
                                    paired_block_intervals, prepare_rows, run_protocol,
                                    sample_parquet, score_predictions, select_blend, spatial_groups, split_rows, time_boundaries)


def frame(n=240):
    rng = np.random.default_rng(14)
    return prepare_rows(pd.DataFrame({
        "Start_Time": pd.date_range("2018-01-01", periods=n, freq="h"),
        "Start_Lat": 25 + rng.integers(0, 80, n)*.3,
        "Start_Lng": -120 + rng.integers(0, 80, n)*.3,
        "Severity": np.where(np.arange(n) % 3, 2, 3),
        "duration_min": rng.uniform(10, 150, n), "w": np.where(np.arange(n) % 5, 10., 1.),
        "Source": np.where(np.arange(n) % 2, "Source1", "Source2"),
        "weather_group": np.where(np.arange(n) % 3, "clear", "rain"),
        "is_night": (np.arange(n) % 24 < 6).astype(int),
        "Temperature(F)": rng.normal(60, 12, n),
    }))


@pytest.mark.parametrize("protocol", ["temporal", "spatial_future"])
def test_time_and_space_partitions_never_leak(protocol):
    d = frame(1000)
    masks, groups = split_rows(d, protocol)
    tr, va, te = [masks[k] for k in ["train", "validation", "test"]]
    assert not np.any(tr & va | tr & te | va & te)
    assert d.Start_Time[tr].max() < d.Start_Time[va].min()
    assert d.Start_Time[va].max() < d.Start_Time[te].min()
    if protocol == "spatial_future":
        assert not set(groups[tr]) & set(groups[te])
        assert not set(groups[tr]) & set(groups[va])
        assert not set(groups[va]) & set(groups[te])
    again, _ = split_rows(d, protocol)
    assert np.array_equal(te, again["test"])


def test_equal_timestamps_remain_together():
    d = frame(100)
    d["Start_Time"] = pd.date_range("2020-01-01", periods=10, freq="D").repeat(10)
    masks, _ = split_rows(d)
    for timestamp in d.Start_Time.unique():
        same = d.Start_Time.eq(timestamp).to_numpy()
        assert sum(bool((same & mask).any()) for mask in masks.values()) == 1


def test_labels_from_events_ending_across_boundaries_are_embargoed():
    d = frame(100)
    d.loc[59, "duration_min"] = 121
    d.loc[79, "duration_min"] = 121
    masks, _ = split_rows(d)
    assert not masks["train"][59]
    assert not masks["validation"][79]
    validation_start, test_start = time_boundaries(d)
    known_at = d.Start_Time + pd.to_timedelta(d.duration_min, unit="m")
    assert (known_at[masks["train"]] < validation_start).all()
    assert (known_at[masks["validation"]] < test_start).all()


def test_duration_blend_uses_its_own_member_and_minute_error():
    y = np.array([0, 1, 0, 1])
    duration = np.log1p([1, 1, 1, 1000])
    predictions = {
        "hist_gradient_boosting": (np.array([.3, .7, .3, .7]), np.log1p([2, 2, 2, 200])),
        # Best classification/log-duration candidate misses the large duration.
        "residual_mlp": (np.array([.01, .99, .01, .99]), np.log1p([1, 1, 1, 100])),
        "soft_mixture_of_experts": (np.array([.4, .6, .4, .6]), np.log1p([10, 10, 10, 1000])),
    }
    selection = select_blend(predictions, y, duration, np.ones(4))
    assert selection["neural_member_severity"] == "residual_mlp"
    assert selection["neural_member_duration"] == "soft_mixture_of_experts"
    assert selection["neural_weight_duration"] == 1


def test_duration_metrics_share_the_same_clipped_predictions():
    from sklearn.metrics import r2_score
    target = np.log1p([1, 10080])
    scored = score_predictions(np.array([0, 1]), target, np.array([.1, .9]), np.array([-100., 100.]), np.ones(2))
    assert scored["duration_mae_minutes"] == pytest.approx(.5)
    assert scored["duration_r2_log"] == pytest.approx(r2_score(target, [0., np.log1p(10080)]))


def test_preprocessing_is_train_only_with_unknown_and_missing_indicators():
    d = frame(100)
    prep = TrainPreprocessor().fit(d.iloc[:60])
    median = prep.median.copy(); vocab = dict(prep.vocab)
    heldout = d.iloc[60:].copy()
    heldout["Temperature(F)"] = np.inf
    heldout["Source"] = "test-only-feed"
    x = prep.transform(heldout)
    assert np.isfinite(x).all()
    assert np.array_equal(prep.median, median)
    assert prep.vocab == vocab and "test-only-feed" not in prep.vocab["Source"]
    assert x[:, prep.feature_names.index("Source=<unseen>")].min() == 1
    assert x[:, prep.feature_names.index("Temperature(F)_missing")].min() == 1


def test_cached_target_features_and_outcomes_never_enter_predictors():
    d = frame()
    d["enc_severe"] = d.target_severe
    d["p_severe"] = d.target_severe
    d["regime"] = d.target_severe
    prep = TrainPreprocessor(False).fit(d)
    assert not any(name.startswith(("enc_", "p_severe", "regime", "Severity", "duration", "Source=")) for name in prep.feature_names)
    assert prep.transform(d).shape[1] == len(prep.feature_names)


def test_temperature_calibration_uses_only_supplied_validation_labels():
    y = np.tile([0, 0, 0, 1], 30)
    raw = np.tile([.001, .001, .999, .999], 30)
    temperature = fit_temperature(y, raw, np.ones(len(y)))
    assert temperature > 1
    assert np.mean((calibrated(raw, temperature)-y)**2) < np.mean((raw-y)**2)
    assert np.isfinite(calibrated(np.array([0., 1.]), temperature)).all()


def test_paired_block_intervals_allow_network_to_lose():
    n = 100
    y = np.arange(n) % 2
    duration = np.ones(n)
    groups = np.array([f"cell-{x//5}" for x in range(n)])
    base = (.1+.8*y, duration)
    worse = (.9-.8*y, duration+.5)
    result = paired_block_intervals(y, duration, base, worse, groups, np.ones(n), draws=40)
    assert result["brier_improvement"]["upper95"] < 0
    assert result["duration_mae_improvement_minutes"]["upper95"] < 0
    identity = paired_block_intervals(y, duration, base, base, groups, np.ones(n), draws=40)
    assert identity["brier_improvement"]["estimate"] == 0
    assert paired_block_intervals(y, duration, base, base, ["one"]*n, np.ones(n))["status"].startswith("insufficient")


def test_parquet_sampler_is_deterministic_and_projects_columns(tmp_path):
    d = frame(100)
    d["prohibited_cached_target"] = d.target_severe
    path = tmp_path/"research.parquet"
    d.to_parquet(path)
    a, b = sample_parquet(path, 40), sample_parquet(path, 40)
    assert len(a) == 40
    pd.testing.assert_frame_equal(a, b)
    assert "prohibited_cached_target" not in a
    assert a.Start_Time.is_monotonic_increasing


def test_moe_gates_are_probabilities_and_all_experts_receive_gradients():
    torch = pytest.importorskip("torch")
    torch.set_num_threads(1)
    torch.manual_seed(1)
    network = make_network(6, "soft_mixture_of_experts", width=8)
    output, gate = network(torch.randn(16, 6))
    assert output.shape == (16, 2) and gate.shape == (16, 3)
    assert torch.allclose(gate.sum(1), torch.ones(16))
    output.square().mean().backward()
    assert all(expert.output.weight.grad.abs().sum().item() > 0 for expert in network.experts)


def test_tiny_end_to_end_retains_baseline_and_pre_post_calibration():
    pytest.importorskip("torch")
    result = run_protocol(frame(), "temporal", include_source=False, epochs=1, iterations=2,
                          bootstrap_draws=4, width=8, threads=1)
    names = {r["model"] for r in result["models"]}
    assert {"hist_gradient_boosting", "residual_mlp", "soft_mixture_of_experts", "validation_blend", "training_prior"} == names
    assert result["selected_on_validation_log_loss"] in names
    for row in result["models"][:3]:
        assert 0 <= row["test"]["brier"] <= 1
        assert "uncalibrated_test" in row and row["temperature_fit_on_validation"] > 0
    assert not any(c.startswith("Source=") for c in result["predictors"])
    assert len(result["split_hash"]) == 64

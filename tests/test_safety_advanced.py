import json

import numpy as np
import pandas as pd
import pytest

from safety import advanced


def panel():
    records = []
    rng = np.random.default_rng(41)
    for segment in range(60):
        for year in [2021, 2022, 2023, 2024]:
            records.append({"segment_id": str(segment), "year": year,
                "aadt": 1000. + segment * 150, "length_miles": 1. + segment / 100,
                "days": 366 if year == 2024 else 365, "lat": 40. + (segment // 10) * .3,
                "lng": -99. + segment % 10 * .005, "fatal_crashes": rng.poisson(.4),
                "aadt_aligned": False, "model_eligible": True, "outcome": "fatal_crash"})
    return pd.DataFrame(records)


def test_feature_whitelist_excludes_current_crash_and_fatality_labels():
    d = panel()
    before = advanced._features(d)
    d["fatal_crashes"] = 999
    d["fatalities"] = 999
    d["light_condition"] = 999  # crash-selected context is not a roadway attribute
    np.testing.assert_array_equal(before, advanced._features(d))


def test_pairwise_bootstrap_preserves_groups_and_direction():
    y = np.array([1, 2, 3, 4, 1, 2, 3, 4])
    groups = np.repeat(np.arange(4), 2)
    exact = advanced.paired_block_interval(y, y, y, groups, replicates=50)
    assert exact["lower"] == exact["upper"] == exact["mean_deviance_improvement"] == 0
    improved = advanced.paired_block_interval(y, np.ones(8) * .1, y, groups, replicates=50)
    assert improved["lower"] > 0 and improved["bootstrap_blocks"] == 4
    with pytest.raises(ValueError, match=">=2"):
        advanced.paired_block_interval(y, y, y, np.zeros(8), replicates=50)


def test_historical_eb_never_uses_target_outcome_and_rejects_future_history():
    d = panel()
    train, test = d[d.year < 2024].copy(), d[d.year == 2024].copy()
    model = {"intercept": -1., "log_aadt_coefficient": 1., "alpha": .5}
    a = advanced.historical_eb_prediction(train, test, model)
    test["fatal_crashes"] = 999
    np.testing.assert_array_equal(a, advanced.historical_eb_prediction(train, test, model))
    train.loc[train.segment_id.eq("0"), "fatal_crashes"] += 5
    assert advanced.historical_eb_prediction(train, test, model)[0] > a[0]
    with pytest.raises(ValueError, match="strictly precede"):
        advanced.historical_eb_prediction(d, test, model)


def test_panel_requires_complete_history_finite_features_and_fatal_scope():
    with pytest.raises(ValueError, match="complete"):
        advanced._validate_panel(panel().iloc[1:])
    d = panel()
    d.loc[0, "lat"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        advanced._validate_panel(d)
    d = panel()
    d["outcome"] = "all_crash"
    with pytest.raises(ValueError, match="fatal-crash"):
        advanced._validate_panel(d)


def test_small_nested_benchmark_is_json_safe_and_never_promotes():
    data = panel()
    data["sinuosity"] = np.where(data.segment_id.astype(int) % 2, 1.2, np.nan)
    report, artifact = advanced.run_benchmark(data, spatial_folds=2, bootstrap_replicates=25)
    json.dumps(report, allow_nan=False)
    assert artifact is None and not report["decision"]["final_model_fitted"]
    assert report["temporal"]["holdout_year"] == 2024
    assert report["temporal"]["training_years"] == [2021, 2022, 2023]
    assert report["temporal"]["gate_training_rows"] == 60
    assert "historical_eb" in report["temporal"]["models"]
    assert "historical_eb" not in report["spatial"]["models"]
    assert sum(f["test_rows"] for f in report["spatial"]["folds"]) == len(panel())
    assert report["aadt_proxy_fraction"] == 1
    assert report["features"] == advanced.FEATURES + ["sinuosity"]
    assert report["schema_version"] == 1
    assert "independent" in report["decision"]["promotion"]

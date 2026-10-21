import numpy as np
import pandas as pd
import pytest

from src.metro_online import FEATURES, block_intervals, fit_at_origin, mature_history, metrics, periods, run, weights_at_origin


def frame():
    t = pd.date_range("2019-01-01", periods=100, freq="D")
    return pd.DataFrame({"Start_Time": t, "End_Time": t + pd.Timedelta(hours=2),
        "Severity": np.tile([1, 2, 3, 4], 25), "duration_min": np.full(100, 120.),
        "log_duration": np.full(100, np.log1p(120))})


def test_monthly_origins_preserve_original_holdout_and_exclude_unmatured_labels():
    d = frame()
    d.loc[79, "End_Time"] = d.loc[81, "Start_Time"]
    cut, windows = periods(d)
    assert cut == 80
    assert np.concatenate([indices for _, indices in windows]).tolist() == list(range(80, 100))
    origin = windows[0][0]
    history = mature_history(d, origin)
    assert not history[79] and not history[80:].any()
    assert d.loc[history, "End_Time"].max() < origin
    later_history = mature_history(d, windows[-1][0])
    assert later_history[80:90].any()  # disclosed sequential learning


def test_recency_class_balance_and_label_boundary():
    d = frame()
    origin = d.End_Time.max() + pd.Timedelta(days=1)
    balanced, recency = weights_at_origin(d, origin)
    assert recency[-1] > recency[0]
    totals = [balanced[d.Severity.eq(level)].sum() for level in [1, 2, 3, 4]]
    assert np.allclose(totals, [25] * 4)
    with pytest.raises(ValueError, match="matured"):
        weights_at_origin(d, d.End_Time.max())


def test_metrics_keep_four_class_task_and_duration_units():
    d = frame()
    score = metrics(d, d.Severity, d.log_duration)
    assert score["macro_f1"] == 1
    assert score["balanced_accuracy"] == 1
    assert score["duration_mae_minutes"] < 1e-9
    assert score["per_class"]["1"]["support"] == 25


def test_invalid_order_and_duration_rejected():
    d = frame()
    with pytest.raises(ValueError, match="sorted"):
        periods(d.iloc[::-1])
    d.loc[0, "End_Time"] = d.loc[0, "Start_Time"]
    with pytest.raises(ValueError, match="finish"):
        periods(d)


def test_paired_blocks_preserve_identical_predictions():
    d = frame()
    d["Start_Lat"] = np.repeat([41., 41.1, 41.2, 41.3], 25)
    d["Start_Lng"] = -96.
    prediction = (d.Severity.to_numpy(), d.log_duration.to_numpy())
    result = block_intervals(d, prediction, prediction, draws=10)
    assert result["balanced_accuracy_difference95"] == [0, 0]
    assert result["duration_mae_reduction_minutes95"] == [0, 0]


def test_sequential_run_fits_only_available_labels_and_archives_original_ids():
    from src.features import CATEGORICAL
    from threadpoolctl import threadpool_limits
    d = frame()
    d['ID'] = [f'incident-{i}' for i in range(len(d))]
    for name in FEATURES:
        d[name] = 'known' if name in CATEGORICAL else 1.
    d['Start_Lat'], d['Start_Lng'] = 41., -96.
    seen = []
    def guarded_fit(history, origin, iterations):
        assert history.End_Time.max() < origin
        seen.append(set(history.ID))
        return fit_at_origin(history, origin, iterations)
    with threadpool_limits(limits=1):
        report, predictions, _ = run(d, iterations=2, bootstrap_draws=5, fit_function=guarded_fit)
    assert predictions.ID.tolist() == d.ID.iloc[80:].tolist()
    assert not (seen[0] & set(predictions.ID))
    assert seen[-1] & set(predictions.ID)
    assert report['test_rows'] == 20 and len(report['test_id_sha256']) == 64
    d.loc[0, 'ID'] = d.loc[1, 'ID']
    with pytest.raises(ValueError, match='unique IDs'):
        run(d, iterations=2, bootstrap_draws=5)

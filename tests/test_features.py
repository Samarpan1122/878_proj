"""Self-checks for the logic most likely to silently break results. Run: .venv/bin/python -m tests.test_features"""
import numpy as np
import pandas as pd

from src.features import ROAD_FLAGS, clean, neighborhood, temporal_split, weather_group
from src.imagery import spectral


def _raw(rows):
    base = {"Severity": 2, "Start_Lat": 41.25, "Start_Lng": -96.0, "Sunrise_Sunset": "Day",
            "Weather_Condition": "Clear", "Source": "Source1", "Wind_Direction": "N"}
    return pd.DataFrame([{**base, **{f: False for f in ROAD_FLAGS}, **r} for r in rows])


def test_clean_duration_and_filters():
    df = clean(_raw([
        {"Start_Time": "2020-01-01 08:00:00", "End_Time": "2020-01-01 08:30:00.000000000"},  # ok, 30 min
        {"Start_Time": "2020-01-01 09:00:00", "End_Time": "2020-01-01 08:00:00"},  # negative -> dropped
        {"Start_Time": "2020-01-01 09:00:00", "End_Time": "2020-03-01 09:00:00"},  # > 7 days -> dropped
    ]))
    assert len(df) == 1 and df.duration_min.iloc[0] == 30
    assert df.is_rush_hour.iloc[0] == 1 and df.is_weekend.iloc[0] == 0


def test_neighborhood_uses_only_finished_past_accidents():
    df = clean(_raw([
        {"Start_Time": "2020-01-01 08:00:00", "End_Time": "2020-01-01 08:30:00", "Severity": 4},
        {"Start_Time": "2020-01-01 08:10:00", "End_Time": "2020-01-01 09:00:00", "Severity": 2},  # overlaps #0
        {"Start_Time": "2020-01-01 10:00:00", "End_Time": "2020-01-01 10:30:00", "Severity": 2},
        {"Start_Time": "2020-01-01 11:00:00", "End_Time": "2020-01-01 11:30:00", "Severity": 3, "Start_Lat": 42.0},  # far away
    ]))
    nb = neighborhood(df)
    assert nb.nb_count.tolist() == [0, 0, 2, 0]  # #1 can't see #0 (still ongoing); far point sees nothing
    assert nb.nb_mean_severity.iloc[2] == 3.0 and np.isnan(nb.nb_mean_severity.iloc[0])


def test_temporal_split_is_ordered():
    tr, te = temporal_split(pd.DataFrame({"x": range(10)}), test_frac=0.2)
    assert tr.sum() == 8 and te[-2:].all() and not te[:8].any()


def test_weather_group_and_spectral():
    g = weather_group(pd.Series(["Light Snow", "Heavy T-Storm", "Mostly Cloudy", None, "Fair / Windy"]))
    assert g.tolist() == ["snow", "thunder", "cloudy", "unknown", "clear"]
    chip = np.zeros((4, 10, 10), np.uint8)
    chip[:, :, :5] = np.array([40, 40, 40, 200])[:, None, None]    # left half: vegetation (high NIR)
    chip[:, :, 5:] = np.array([150, 150, 150, 140])[:, None, None]  # right half: impervious
    s = spectral(chip)
    assert s["img_veg_frac"] == 0.5 and s["img_impervious_frac"] == 0.5


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)

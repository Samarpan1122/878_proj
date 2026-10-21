"""Cleaning, targets, temporal features, leakage-safe neighborhood features, feature groups."""
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

EARTH_KM = 6371.0
MAX_DURATION_MIN = 7 * 24 * 60  # longer "impacts" are data errors (roadworks logged as accidents)
SEVERE = 3  # severity >= 3 counts as severe
NEIGHBOR_KM = 1.0

WEATHER_NUM = ["Temperature(F)", "Wind_Chill(F)", "Humidity(%)", "Pressure(in)",
               "Visibility(mi)", "Wind_Speed(mph)", "Precipitation(in)"]
ROAD_FLAGS = ["Amenity", "Bump", "Crossing", "Give_Way", "Junction", "No_Exit", "Railway",
              "Roundabout", "Station", "Stop", "Traffic_Calming", "Traffic_Signal"]
TEMPORAL = ["hour", "dow", "month", "year", "is_weekend", "is_rush_hour", "is_night"]
CATEGORICAL = ["Source", "weather_group", "Wind_Direction"]
TABULAR = WEATHER_NUM + ROAD_FLAGS + TEMPORAL + CATEGORICAL
NEIGHBORHOOD = ["nb_count", "nb_mean_severity", "nb_severe_rate", "nb_mean_log_duration", "nb_night_frac"]


def weather_group(cond: pd.Series) -> pd.Series:
    """Collapse ~140 raw Weather_Condition strings into a handful of groups."""
    c = cond.fillna("").str.lower()
    groups = [("snow", "snow|sleet|ice|wintry|hail"), ("thunder", "thunder|t-storm|storm"),
              ("rain", "rain|drizzle|shower"), ("fog", "fog|mist|haze|smoke|dust"),
              ("cloudy", "cloud|overcast"), ("clear", "clear|fair")]
    out = pd.Series("other", index=cond.index)
    for name, pat in reversed(groups):  # first listed wins
        out[c.str.contains(pat)] = name
    return out.where(c != "", "unknown")


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Parse times, derive duration target and temporal features, drop unusable rows."""
    df = df.copy()
    for col in ("Start_Time", "End_Time"):
        df[col] = pd.to_datetime(df[col].astype(str).str[:19], errors="coerce")
    df["duration_min"] = (df["End_Time"] - df["Start_Time"]).dt.total_seconds() / 60
    ok = (df["Start_Time"].notna() & df["duration_min"].between(1, MAX_DURATION_MIN)
          & df["Start_Lat"].between(18, 72) & df["Start_Lng"].between(-180, -60)
          & df["Severity"].between(1, 4))
    df = df[ok].copy()
    df["log_duration"] = np.log1p(df["duration_min"])
    t = df["Start_Time"]
    df["hour"], df["dow"], df["month"], df["year"] = t.dt.hour, t.dt.dayofweek, t.dt.month, t.dt.year
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["is_rush_hour"] = ((df["dow"] < 5) & (df["hour"].between(7, 9) | df["hour"].between(16, 18))).astype(int)
    df["is_night"] = (df["Sunrise_Sunset"] == "Night").astype(int)
    df["weather_group"] = weather_group(df["Weather_Condition"])
    for col in ROAD_FLAGS:
        df[col] = df[col].astype(bool).astype(int)
    for col in CATEGORICAL:
        df[col] = df[col].fillna("unknown").astype("category")
    df["is_severe"] = (df["Severity"] >= SEVERE).astype(int)
    return df.sort_values("Start_Time").reset_index(drop=True)


def neighborhood(df: pd.DataFrame, radius_km: float = NEIGHBOR_KM) -> pd.DataFrame:
    """Stats over accidents within radius_km that had already ENDED before this one started.

    Only outcomes known at the accident's start time are used, so the features are
    leakage-safe under a temporal train/test split.
    # ponytail: O(n * neighbors) python loop; fine for city scale (~1e5 rows), vectorize for national.
    """
    coords = np.radians(df[["Start_Lat", "Start_Lng"]].to_numpy())
    idx = BallTree(coords, metric="haversine").query_radius(coords, r=radius_km / EARTH_KM)
    start = df["Start_Time"].to_numpy()
    end = df["End_Time"].to_numpy()
    sev = df["Severity"].to_numpy(float)
    logd = df["log_duration"].to_numpy()
    night = df["is_night"].to_numpy(float)
    rows = np.full((len(df), len(NEIGHBORHOOD)), np.nan)
    for i, nb in enumerate(idx):
        nb = nb[end[nb] < start[i]]
        rows[i, 0] = len(nb)
        if len(nb):
            rows[i, 1:] = sev[nb].mean(), (sev[nb] >= SEVERE).mean(), logd[nb].mean(), night[nb].mean()
    return pd.DataFrame(rows, columns=NEIGHBORHOOD, index=df.index)


def temporal_split(df: pd.DataFrame, test_frac: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """Train on the earliest (1 - test_frac) of accidents, test on the latest. Assumes df sorted by time."""
    cut = int(len(df) * (1 - test_frac))
    mask = np.arange(len(df)) < cut
    return mask, ~mask

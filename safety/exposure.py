"""Conservative metric linkage and a complete fatal-crash exposure panel.

Unmatched and ambiguous crashes remain in the coverage report. These counts are
not an estimate of all traffic crashes, and a current AADT is a labeled proxy.
"""
import calendar

import geopandas as gpd
import numpy as np
import pandas as pd


def match_crashes(crashes, segments, max_distance_m=50, ambiguity_margin_m=5):
    """Return one audit row per crash and JSON-safe linkage coverage.

    Coordinates are projected to Nebraska UTM 14N. If the second road is within
    ``ambiguity_margin_m`` of the nearest distance, neither road gets the crash.
    This deliberately withholds uncertain junction/parallel-carriageway matches.
    """
    if not 0 < max_distance_m <= 50 or not 0 <= ambiguity_margin_m <= max_distance_m:
        raise ValueError("Use a positive maximum distance <=50m and a valid ambiguity margin")
    if crashes.crash_id.isna().any() or crashes.crash_id.duplicated().any():
        raise ValueError("Crash IDs must be present and unique")
    if segments.crs is None or segments.segment_id.isna().any() or segments.segment_id.duplicated().any():
        raise ValueError("Road CRS and unique segment IDs are required")
    roads = segments.reset_index(drop=True).to_crs(26914)
    if roads.empty or roads.geometry.is_empty.any() or not roads.geometry.is_valid.all():
        raise ValueError("Nonempty valid road geometries are required")
    rows = crashes[["crash_id", "year", "fatalities"]].copy().reset_index(drop=True)
    rows["segment_id"] = pd.Series([None] * len(rows), dtype=object)
    rows["distance_m"] = np.nan
    rows["match_status"] = "unlocated"
    coords = crashes.reset_index(drop=True)
    valid = coords.lat.between(-90, 90) & coords.lng.between(-180, 180)
    points = gpd.GeoSeries(gpd.points_from_xy(coords.loc[valid, "lng"], coords.loc[valid, "lat"]),
                          index=coords.index[valid], crs=4326).to_crs(26914)
    spatial = roads.sindex
    for index, point in points.items():
        # Bounding-box query followed by exact metric distance, never degrees.
        candidates = spatial.query(point.buffer(max_distance_m))
        distances = roads.geometry.iloc[candidates].distance(point).sort_values()
        distances = distances[distances <= max_distance_m]
        if distances.empty:
            rows.at[index, "match_status"] = "outside_tolerance"
            continue
        rows.at[index, "distance_m"] = float(distances.iloc[0])
        if len(distances) > 1 and distances.iloc[1] - distances.iloc[0] <= ambiguity_margin_m:
            rows.at[index, "match_status"] = "ambiguous"
            continue
        rows.at[index, "segment_id"] = roads.iloc[distances.index[0]].segment_id
        rows.at[index, "match_status"] = "matched"
    counts = rows.match_status.value_counts().to_dict()
    coverage = {"total_crashes": len(rows), **{name: int(counts.get(name, 0)) for name in
                ["matched", "ambiguous", "unlocated", "outside_tolerance"]},
                "matched_fraction": float(counts.get("matched", 0) / len(rows)) if len(rows) else 0.0,
                "max_distance_m": max_distance_m, "ambiguity_margin_m": ambiguity_margin_m,
                "metric_crs": "EPSG:26914", "outcome": "fatal_crash",
                "interpretation": "Matched fatal crashes on supplied roads; unresolved locations excluded"}
    return rows, coverage


def build_segment_years(crashes, segments, years, allow_aadt_proxy=True):
    """Build every road x declared complete FARS year, including zero crashes.

    Callers must supply complete annual FARS extracts for the selected geography.
    ``aadt_aligned`` means equal vintage only, not an independently verified
    historical geometry. Invalid AADT/length rows remain visible but ineligible.
    """
    years = sorted(set(years))
    if not years or any(int(y) != y or not 1900 <= y <= 2100 for y in years):
        raise ValueError("Explicit complete observation years are required")
    if not set(crashes.year).issubset(years):
        raise ValueError("Crash years outside declared observation period")
    if not crashes.outcome.eq("fatal_crash").all() or not crashes.fatalities.ge(1).all():
        raise ValueError("Only normalized fatal-crash records are supported")
    matches, coverage = match_crashes(crashes, segments)
    columns = [c for c in ["segment_id", "route", "aadt", "aadt_year", "length_miles", "lat", "lng",
                           "facility_type", "source"] if c in segments]
    panel = pd.DataFrame(segments[columns]).merge(pd.DataFrame({"year": years}), how="cross")
    matched = matches[matches.match_status.eq("matched")]
    counts = matched.groupby(["segment_id", "year"]).agg(fatal_crashes=("crash_id", "size"),
                                                          fatalities=("fatalities", "sum")).reset_index()
    panel = panel.merge(counts, on=["segment_id", "year"], how="left")
    panel[["fatal_crashes", "fatalities"]] = panel[["fatal_crashes", "fatalities"]].fillna(0).astype(int)
    panel["days"] = panel.year.map(lambda y: 366 if calendar.isleap(y) else 365)
    panel["aadt_aligned"] = panel.aadt_year.eq(panel.year)
    panel["exposure_status"] = np.where(panel.aadt_aligned, "vintage_aligned", "aadt_vintage_proxy")
    valid = (np.isfinite(panel.aadt) & panel.aadt.gt(0) & np.isfinite(panel.length_miles)
             & panel.length_miles.gt(0) & panel.aadt_year.notna())
    panel.loc[~valid, "exposure_status"] = "missing_or_invalid_exposure"
    panel["model_eligible"] = valid & (panel.aadt_aligned | allow_aadt_proxy)
    panel["vehicle_miles"] = (panel.aadt * panel.length_miles * panel.days).where(valid)
    panel["fatal_crashes_per_100m_vmt"] = panel.fatal_crashes / panel.vehicle_miles * 100_000_000
    panel["outcome"] = "fatal_crash"
    coverage.update({"segment_years": len(panel), "zero_crash_segment_years": int(panel.fatal_crashes.eq(0).sum()),
                     "eligible_segment_years": int(panel.model_eligible.sum()),
                     "proxy_segment_years": int((valid & ~panel.aadt_aligned).sum()),
                     "years": years, "allow_aadt_proxy": bool(allow_aadt_proxy),
                     "coverage_assumption": "Caller declared each annual FARS extract complete for geography"})
    return panel, coverage

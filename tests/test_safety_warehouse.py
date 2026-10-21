import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from safety.warehouse import export_bigquery


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    roads = gpd.GeoDataFrame({"segment_id": ["A", "B"], "aadt": [1000, np.nan],
        "aadt_year": [2023, np.nan], "length_miles": [1.1, 2.2], "source": ["ndot_aadt"] * 2},
        geometry=[LineString([(-96, 41), (-96.1, 41.1)]), LineString([(-96, 41), (-95.9, 41.1)])], crs=4326)
    roads.to_parquet(root / "segments.parquet")
    pd.DataFrame({"crash_id": ["FARS-1", "FARS-2"], "year": [2023, 2023], "fatalities": [1, 2],
        "lat": [41, np.nan], "lng": [-96, np.nan], "source": ["fars"] * 2}).to_parquet(root / "crashes.parquet")
    (root / "snapshot.json").write_text('{"built_at":"2026-09-29T14:00:00+00:00"}')
    pd.DataFrame({"segment_id": ["A"], "expected_annual": [0.12], "missing_stat": [np.nan]}).to_parquet(root / "screening.parquet")
    return root


def test_roundtrip_ndjson_with_native_json_and_wkt(source, tmp_path):
    result = export_bigquery(source, tmp_path / "export")
    assert result["segments"] == result["crashes"] == 2
    assert result["unlocated_crashes"] == 1
    roads = [json.loads(line) for line in (tmp_path / "export/segments.ndjson").read_text().splitlines()]
    crashes = [json.loads(line) for line in (tmp_path / "export/crashes.ndjson").read_text().splitlines()]
    assert roads[0]["snapshot_date"] == "2026-09-29"
    assert roads[0]["geometry"].startswith("LINESTRING")
    assert isinstance(roads[0]["properties"], dict)
    assert roads[0]["properties"]["expected_annual"] == 0.12
    assert roads[0]["properties"]["missing_stat"] is None
    assert roads[1]["aadt"] is None and roads[1]["aadt_year"] is None
    assert crashes[0]["geometry"] == "POINT (-96 41)" and crashes[1]["geometry"] is None
    schema = json.loads((tmp_path / "export/segments-schema.json").read_text())
    assert {s["name"]: s["type"] for s in schema}["properties"] == "JSON"
    assert result["files"]["segments.ndjson"]["sha256"]
    assert json.loads((tmp_path / "export/manifest.json").read_text())["commercial_ready"] is False


@pytest.mark.parametrize("field,values", [("source", ["legacy", "fars"]), ("crash_id", ["same", "same"]),
    ("lat", [91.0, np.nan]), ("lng", [np.inf, np.nan]), ("fatalities", [1.5, 2])])
def test_rejects_invalid_crash_exports(source, tmp_path, field, values):
    crashes = pd.read_parquet(source / "crashes.parquet")
    crashes[field] = values
    crashes.to_parquet(source / "crashes.parquet")
    with pytest.raises(ValueError):
        export_bigquery(source, tmp_path / "export")
    assert not (tmp_path / "export/manifest.json").exists()


@pytest.mark.parametrize("geometry", [Point(-96, 41), LineString(), LineString([(181, 41), (182, 42)])])
def test_rejects_invalid_road_geometry(source, tmp_path, geometry):
    roads = gpd.read_parquet(source / "segments.parquet")
    roads.loc[0, "geometry"] = geometry
    roads.to_parquet(source / "segments.parquet")
    with pytest.raises(ValueError):
        export_bigquery(source, tmp_path / "export")


def test_export_without_optional_screening_or_snapshot(source, tmp_path):
    (source / "screening.parquet").unlink()
    (source / "snapshot.json").unlink()
    assert export_bigquery(source, tmp_path / "export")["segments"] == 2


def test_duplicate_screening_rejected(source, tmp_path):
    pd.DataFrame({"segment_id": ["A", "A"]}).to_parquet(source / "screening.parquet")
    with pytest.raises(ValueError, match="unique"):
        export_bigquery(source, tmp_path / "export")

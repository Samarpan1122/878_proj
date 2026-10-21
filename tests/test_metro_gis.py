"""Local geometry and cache-correction regressions; no external data requests."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, MultiLineString, Point

from src.gis import correct_cached_road_density, road_length_density, unique_road_geometries


def frame(geometries, **attributes):
    return gpd.GeoDataFrame(attributes, geometry=geometries, crs=26914)


def test_reversed_duplicate_counts_once_but_parallel_centerline_survives():
    a = [(499800, 4500000), (500200, 4500000)]
    edges = frame([LineString(a), LineString(a[::-1]),
                   LineString([(499800, 4500050), (500200, 4500050)])])
    assert len(unique_road_geometries(edges)) == 2
    point = frame([Point(500000, 4500000)])
    actual = road_length_density(point, edges, radii=[100]).iloc[0, 0]
    expected = sum(g.intersection(point.geometry.iloc[0].buffer(100)).length
                   for g in edges.geometry.iloc[[0, 2]]) / 1000 / (np.pi * .1 ** 2)
    assert actual == pytest.approx(expected)
    assert road_length_density(point, edges.iloc[:2], radii=[100]).iloc[0, 0] == pytest.approx(200 / 1000 / (np.pi * .1 ** 2))


def test_multipart_direction_component_order_and_nonconsecutive_indices():
    parts = [[(499800, 4500000), (500000, 4500000)], [(500000, 4500000), (500200, 4500000)]]
    edges = frame([MultiLineString(parts), MultiLineString([p[::-1] for p in parts[::-1]])])
    edges.index = [80, 90]
    assert len(unique_road_geometries(edges)) == 1
    points = frame([Point(500000, 4500000), Point(500000, 4510000)])
    points.index = [40, 20]
    density = road_length_density(points, edges, radii=[100])
    assert density.index.tolist() == [40, 20]
    assert density.loc[40].iloc[0] > 0 and density.loc[20].iloc[0] == 0


def test_density_rejects_nonmetric_crs_and_invalid_geometries():
    points = frame([Point(500000, 4500000)])
    edges = frame([LineString([(499800, 4500000), (500200, 4500000)])])
    with pytest.raises(ValueError, match="metre"):
        road_length_density(points.to_crs(4326), edges.to_crs(4326))
    with pytest.raises(ValueError, match="positive"):
        road_length_density(points, edges, radii=[0])
    with pytest.raises(ValueError, match="linework"):
        unique_road_geometries(points)
    with pytest.raises(ValueError, match="nonempty"):
        unique_road_geometries(frame([LineString()]))


def test_cache_rebuild_preserves_identity_other_features_and_original_files(tmp_path, monkeypatch):
    import src.gis as gis

    monkeypatch.setattr(gis, "_osm_layers", lambda *a, **kw: pytest.fail("No network-backed layer helper permitted"))
    coords = [(499800, 4500000), (500200, 4500000)]
    edges = frame([LineString(coords), LineString(coords[::-1])])
    cache = tmp_path / "osm"
    cache.mkdir()
    edges.to_crs(4326).to_parquet(cache / "Omaha_edges.parquet")
    point = frame([Point(500000, 4500000)]).to_crs(4326).geometry.iloc[0]
    original = pd.DataFrame({"ID": ["fixture-2", "fixture-1"], "loc_id": [17, 17],
        "Start_Time": pd.to_datetime(["2020-01-02", "2020-01-01"]), "Start_Lat": point.y,
        "Start_Lng": point.x, "lat": point.y, "lng": point.x, "area": "Omaha",
        "road_km_per_km2_100": 12., "road_km_per_km2_250": 4., "road_km_per_km2_500": 1.,
        "Severity": [2, 4], "emb_0": [1.5, 9.], "nb_mean_severity": [np.nan, 2.],
        "building_frac_100": [.2, .3]})
    source = tmp_path / "metro_features.parquet"
    original.to_parquet(source, index=False)
    before_source = source.read_bytes()
    before_edges = (cache / "Omaha_edges.parquet").read_bytes()
    audit = correct_cached_road_density(source, cache, tmp_path / "output")
    corrected = pd.read_parquet(audit["output_path"])
    pd.testing.assert_frame_equal(corrected.drop(columns=audit["modified_columns"]),
                                  original.drop(columns=audit["modified_columns"]))
    assert audit["row_order_and_identity_preserved"] and audit["rows"] == 2
    assert audit["geometry_audits"][0]["duplicate_direction_geometries_removed"] == 1
    assert source.read_bytes() == before_source and (cache / "Omaha_edges.parquet").read_bytes() == before_edges
    assert audit["input_sha256"][str(source)] and audit["output_sha256"] and audit["row_identity_sha256"]
    assert json.loads((tmp_path / "output/gis_correction.json").read_text())["modified_columns"] == audit["modified_columns"]
    assert (corrected.road_km_per_km2_100 < original.road_km_per_km2_100).all()
    # A second run against immutable inputs produces the same value table/hash.
    again = correct_cached_road_density(source, cache, tmp_path / "output")
    assert again["output_sha256"] == audit["output_sha256"]

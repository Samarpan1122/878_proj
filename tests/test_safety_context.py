import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, MultiLineString

from safety.context import road_context


def roads(lines):
    return gpd.GeoDataFrame({"segment_id": [str(i) for i in range(len(lines))],
                            "aadt": [1000 * (i + 1) for i in range(len(lines))]},
                           geometry=lines, crs=26914)


def test_orientation_reversal_and_geometry_only_context():
    line = [(500000, 4500000), (500500, 4500000)]
    g = roads([LineString(line), LineString([(500000, 4500100), (500500, 4500100)]),
               LineString([(510000, 4500000), (510500, 4500000)])])
    first = road_context(g)
    g.loc[0, "geometry"] = LineString(line[::-1])
    second = road_context(g)
    assert np.allclose(first.bearing_sin, second.bearing_sin, atol=1e-10)
    assert np.allclose(first.bearing_cos, second.bearing_cos, atol=1e-10)
    assert first.neighbor_roads_1km.tolist() == [1, 1, 0]
    assert first.neighbor_mean_aadt_1km.iloc[0] == 2000
    assert np.isnan(first.neighbor_mean_aadt_1km.iloc[2])
    assert first.sinuosity.eq(1).all()


def test_parts_do_not_bridge_gaps_and_closed_line_missing():
    multi = MultiLineString([[(500000, 4500000), (500100, 4500000)],
                             [(501000, 4500000), (501100, 4500000)]])
    loop = LineString([(500000, 4510000), (500100, 4510100), (500000, 4510000)])
    result = road_context(roads([multi, loop]))
    assert result.sinuosity.iloc[0] == 1
    assert np.isnan(result.sinuosity.iloc[1])
    assert np.isnan(result.bearing_sin.iloc[1])


def test_context_rejects_bad_id_and_missing_crs():
    g = roads([LineString([(500000, 4500000), (500100, 4500000)])])
    g.loc[0, "segment_id"] = None
    with pytest.raises(ValueError):
        road_context(g)
    g.loc[0, "segment_id"] = "valid"
    with pytest.raises(ValueError):
        road_context(g.set_crs(None, allow_override=True))


def test_float_aadt_is_not_mutated():
    g = roads([LineString([(500000, 4500000), (500100, 4500000)]),
               LineString([(500000, 4500100), (500100, 4500100)])])
    g["aadt"] = [1000., np.nan]
    result = road_context(g)
    assert np.isnan(result.neighbor_mean_aadt_1km.iloc[0])
    assert result.neighbor_mean_aadt_1km.iloc[1] == 1000
    assert g.aadt.iloc[0] == 1000 and np.isnan(g.aadt.iloc[1])

"""Outcome-free geometry and neighborhood features from the published road network.

Neighborhoods use segment midpoints, not inferred intersections. Current road
geometry remains a vintage proxy for older crashes; these are not design ratings.
"""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

CONTEXT_FEATURES = ["sinuosity", "road_vertices_per_mile", "bearing_sin", "bearing_cos",
                    "neighbor_roads_1km", "neighbor_roads_5km", "neighbor_mean_aadt_1km"]


def road_context(roads):
    if roads.empty or roads.crs is None or roads.segment_id.isna().any() or roads.segment_id.duplicated().any():
        raise ValueError("Context requires nonempty georeferenced roads with unique IDs")
    projected = roads.to_crs(26914)
    if (not projected.geometry.geom_type.isin(["LineString", "MultiLineString"]).all()
            or not projected.geometry.is_valid.all() or not projected.geometry.length.gt(0).all()):
        raise ValueError("Context requires valid positive-length road lines")
    midpoints = projected.geometry.interpolate(.5, normalized=True)
    xy = np.column_stack([midpoints.x, midpoints.y])
    if not np.isfinite(xy).all():
        raise ValueError("Road midpoints must be finite")
    tree = cKDTree(xy)
    near = tree.query_ball_point(xy, 1000)
    broad = tree.query_ball_point(xy, 5000, return_length=True)
    aadt = pd.to_numeric(roads.aadt, errors="coerce").to_numpy(dtype=float, copy=True)
    aadt[~np.isfinite(aadt) | (aadt <= 0)] = np.nan
    records = []
    for position, geometry in enumerate(projected.geometry):
        parts = list(geometry.geoms) if geometry.geom_type == "MultiLineString" else [geometry]
        # Sum each part's endpoint chord: do not bridge disconnected parts.
        chord = sum(np.linalg.norm(np.asarray(p.coords)[-1, :2] - np.asarray(p.coords)[0, :2]) for p in parts)
        vertices = sum(len(p.coords) for p in parts)
        longest = max(parts, key=lambda p: p.length)
        delta = np.asarray(longest.coords)[-1, :2] - np.asarray(longest.coords)[0, :2]
        bearing = np.arctan2(delta[1], delta[0]) if np.linalg.norm(delta) > 1e-6 else np.nan
        neighbors = [j for j in near[position] if j != position]
        neighbor_aadt = aadt[neighbors]
        mean_aadt = float(np.nanmean(neighbor_aadt)) if np.isfinite(neighbor_aadt).any() else np.nan
        records.append({"segment_id": roads.segment_id.iloc[position],
                        "sinuosity": float(geometry.length / chord) if chord > 1e-6 else np.nan,
                        "road_vertices_per_mile": vertices / (geometry.length / 1609.344),
                        # Double angle makes orientation invariant to vertex direction.
                        "bearing_sin": float(np.sin(2 * bearing)), "bearing_cos": float(np.cos(2 * bearing)),
                        "neighbor_roads_1km": len(neighbors), "neighbor_roads_5km": int(broad[position] - 1),
                        "neighbor_mean_aadt_1km": mean_aadt})
    result = pd.DataFrame(records)
    if np.isinf(result[CONTEXT_FEATURES].to_numpy()).any():
        raise ValueError("Invalid infinite geometry context")
    return result

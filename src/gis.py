"""OpenStreetMap context around each accident location, at several buffer radii.

Per unique location (lat/lon rounded to ~11 m) and radius r in BUFFERS_M:
  road_km_per_km2_r, intersections_per_km2_r, {building,parking,green,water,commercial,
  residential,industrial}_frac_r
plus nearest-road attributes: road_class, is_highway, maxspeed, lanes, dist_highway_m.
"""
import re
import time
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import requests
import shapely

BUFFERS_M = (100, 250, 500)
PAD_DEG = 0.01
NEAREST_ROAD_MAX_M = 60
POLY_TAGS = {
    "building": {"building": True},
    "parking": {"amenity": "parking"},
    "green": {"leisure": ["park", "golf_course", "nature_reserve", "pitch"],
              "landuse": ["grass", "forest", "meadow", "recreation_ground", "cemetery"],
              "natural": ["wood", "scrub", "grassland"]},
    "water": {"natural": "water", "waterway": "riverbank"},
    "commercial": {"landuse": ["commercial", "retail"]},
    "residential": {"landuse": "residential"},
    "industrial": {"landuse": "industrial"},
}
ROAD_CLASS = {"motorway": 6, "trunk": 5, "primary": 4, "secondary": 3, "tertiary": 2,
              "residential": 1, "unclassified": 1, "living_street": 1}
ox.settings.use_cache = False  # we cache the parsed layers ourselves (OSM_CACHE), far smaller than raw JSON
OSM_CACHE = Path("data/osm")
OVERPASS_TRIES, OVERPASS_BACKOFF_S = 6, 30
# Public Overpass instances; rotated on failure (overpass-api.de rate-limits heavy building queries).
OVERPASS_URLS = ["https://maps.mail.ru/osm/tools/overpass/api", "https://overpass-api.de/api",
                 "https://overpass.kumi.systems/api"]
ox.settings.overpass_rate_limit = False  # mirrors don't all expose /status
ox.settings.requests_timeout = 600


def unique_road_geometries(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One copy of each exact centerline geometry, independent of vertex direction.

    OSM drive graphs contain both directions of many roads. Counting both copies
    doubles their physical line length. Parallel carriageways remain distinct.
    Normalization also makes equivalent multipart component order deterministic;
    this is not a topological union or an inference about grade separation.
    """
    if edges.crs is None or edges.geometry.isna().any() or edges.geometry.is_empty.any():
        raise ValueError("Road geometries require a CRS and nonempty lines")
    if not edges.geom_type.isin(["LineString", "MultiLineString"]).all() or not edges.is_valid.all():
        raise ValueError("Road geometries must be valid linework")
    normalized = shapely.normalize(edges.geometry.to_numpy())
    keys = pd.Series(shapely.to_wkb(normalized))
    return edges.iloc[np.flatnonzero(~keys.duplicated().to_numpy())].reset_index(drop=True).copy()


def road_length_density(points: gpd.GeoDataFrame, edges: gpd.GeoDataFrame,
                        radii=BUFFERS_M) -> pd.DataFrame:
    """Kilometres of unique centerline geometry per square kilometre of buffer.

    Both inputs must use the same projected metre CRS. Preserve the point index
    to keep joins to location identities independent of edge order/index labels.
    """
    if (points.crs is None or points.crs != edges.crs or not points.crs.is_projected
            or not points.crs.axis_info or any(abs(axis.unit_conversion_factor - 1) > 1e-9
                                              for axis in points.crs.axis_info[:2])):
        raise ValueError("Road density requires matching projected metre CRSs")
    if (not points.index.is_unique or points.geometry.isna().any() or points.geometry.is_empty.any()
            or not points.geom_type.eq("Point").all() or not points.is_valid.all()):
        raise ValueError("Density locations must be valid unique-indexed points")
    roads = unique_road_geometries(edges[["geometry"]])
    result = pd.DataFrame(index=points.index)
    for radius in radii:
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError("Buffer radii must be positive finite metres")
        buffers = gpd.GeoDataFrame(geometry=points.geometry.buffer(radius), crs=points.crs)
        joined = gpd.sjoin(buffers, roads, predicate="intersects")
        lengths = pd.Series(shapely.length(shapely.intersection(
            joined.geometry.to_numpy(), roads.geometry.to_numpy()[joined.index_right.to_numpy(dtype=int)])),
            index=joined.index)
        result[f"road_km_per_km2_{radius}"] = (lengths.groupby(level=0).sum()
            / 1000 / (np.pi * radius * radius / 1e6)).reindex(points.index, fill_value=0.)
    return result


def correct_cached_road_density(source_path="data/processed/metro_features.parquet",
                               osm_cache=OSM_CACHE, output_dir="outputs/research/metro"):
    """Correct only three density columns using local files; preserve source caches.

    No OSM requests, imagery reads, label fitting or other feature recomputation.
    The audit records exact input/output hashes and joins by stable loc_id.
    """
    from safety.io import digest, write_json

    source_path, osm_cache, output_dir = Path(source_path), Path(osm_cache), Path(output_dir)
    output_path = output_dir / "metro_features_corrected.parquet"
    if output_path.resolve() == source_path.resolve():
        raise ValueError("Corrected output must not overwrite the source cache")
    original = pd.read_parquet(source_path)
    columns = [f"road_km_per_km2_{radius}" for radius in BUFFERS_M]
    identity = ["ID", "loc_id", "Start_Time", "Start_Lat", "Start_Lng"]
    required = set(columns + identity + ["area", "lat", "lng"])
    if required - set(original) or original.ID.isna().any() or original.ID.duplicated().any():
        raise ValueError("Original metro features require unique crash IDs, location identities and density columns")
    if original.loc_id.isna().any() or original.groupby("loc_id")[["lat", "lng", "area"]].nunique(dropna=False).gt(1).any().any():
        raise ValueError("A location identity must have one coordinate and study area")
    locations = original[["loc_id", "lat", "lng", "area"]].drop_duplicates("loc_id")
    if locations.empty or not locations.area.isin(["Omaha", "Lincoln"]).all():
        raise ValueError("Cache-only correction supports the original Omaha/Lincoln study areas")
    if not np.isfinite(locations[["lat", "lng"]]).all().all():
        raise ValueError("Location coordinates must be finite")
    hashes = {str(source_path): digest(source_path)}
    pieces, audits = [], []
    for area, subset in locations.groupby("area", sort=True):
        edge_path = osm_cache / f"{area}_edges.parquet"
        hashes[str(edge_path)] = digest(edge_path)
        edges = gpd.read_parquet(edge_path)
        points = gpd.GeoDataFrame(subset.set_index("loc_id"),
            geometry=gpd.points_from_xy(subset.lng, subset.lat), crs=4326)
        crs = points.estimate_utm_crs()
        points, edges = points.to_crs(crs), edges.to_crs(crs)
        unique = unique_road_geometries(edges)
        pieces.append(road_length_density(points, unique))
        audits.append({"area": area, "locations": len(points), "crs": crs.to_string(),
            "original_edges": len(edges), "unique_geometries": len(unique),
            "duplicate_direction_geometries_removed": len(edges) - len(unique),
            "original_length_m": float(edges.length.sum()), "unique_geometry_length_m": float(unique.length.sum()),
            "edges_sha256": hashes[str(edge_path)]})
    values = pd.concat(pieces)
    if not values.index.is_unique or len(values) != len(locations):
        raise ValueError("Density correction produced missing or duplicate location identities")
    corrected = original.copy()
    for column in columns:
        corrected[column] = original.loc_id.map(values[column])
    if not np.isfinite(corrected[columns]).all().all():
        raise ValueError("Density correction produced nonfinite features")
    untouched = [column for column in original if column not in columns]
    if not corrected[untouched].equals(original[untouched]):
        raise AssertionError("Correction changed unrelated feature values or row identities")
    identity_hash = hashlib.sha256(pd.util.hash_pandas_object(original[identity], index=True).to_numpy().tobytes()).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".parquet", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        corrected.to_parquet(temporary, index=False)
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    if any(digest(Path(path)) != value for path, value in hashes.items()):
        raise RuntimeError("Source cache changed during correction; rerun against stable inputs")
    audit = {"schema_version": 1, "built_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path), "output_path": str(output_path), "input_sha256": hashes,
        "source_sha256": hashes[str(source_path)],
        "output_sha256": digest(output_path), "row_identity_sha256": identity_hash,
        "rows": len(corrected), "locations": len(locations), "modified_columns": columns,
        "unchanged_columns_verified": untouched, "row_order_and_identity_preserved": True,
        "geometry_audits": audits,
        "changes": {column: {"rows_changed": int((~np.isclose(original[column], corrected[column], equal_nan=True)).sum()),
                             "original_mean": float(original[column].mean()), "corrected_mean": float(corrected[column].mean())}
                    for column in columns},
        "definition": "Unique normalized centerline geometry length per circular-buffer area; reverse-direction copies counted once",
        "limitations": ["Exact geometry deduplication; not a topological union or grade-separation inference",
                        "OSM cache retrieval time is unavailable; historical-vintage uncertainty persists",
                        "All imagery, outcomes, history features and non-density GIS columns remain unchanged",
                        "Research-only original dataset licensing remains in effect"]}
    write_json(output_dir / "gis_correction.json", audit)
    return audit


def locations(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Unique rounded locations with a stable loc_id, plus each df row's loc_id."""
    key = df["Start_Lat"].round(4).astype(str) + "," + df["Start_Lng"].round(4).astype(str)
    codes, uniq = pd.factorize(key)
    lat, lng = zip(*(map(float, k.split(",")) for k in uniq))
    return pd.DataFrame({"loc_id": np.arange(len(uniq)), "lat": lat, "lng": lng}), codes


def _first(v):
    return v[0] if isinstance(v, list) else v


def _num(v):
    m = re.match(r"\d+", str(_first(v)))
    return float(m.group()) if m else np.nan


def _poly_frac(buf: gpd.GeoDataFrame, polys: gpd.GeoSeries, area: float) -> pd.Series:
    if polys.empty:
        return pd.Series(0.0, index=buf.index)
    polys = gpd.GeoDataFrame(geometry=polys.make_valid().reset_index(drop=True))
    j = gpd.sjoin(buf, polys, predicate="intersects")
    inter = pd.Series(shapely.area(shapely.intersection(j.geometry.values, polys.geometry.values[j["index_right"]])), index=j.index)
    return (inter.groupby(level=0).sum() / area).clip(upper=1).reindex(buf.index, fill_value=0.0)


def _retry(fn, tries: int = OVERPASS_TRIES):
    """Overpass rate-limits and occasionally refuses connections; back off and retry."""
    for k in range(tries):
        ox.settings.overpass_url = OVERPASS_URLS[k % len(OVERPASS_URLS)]
        try:
            return fn()
        except (requests.exceptions.RequestException, ox._errors.ResponseStatusCodeError) as e:
            if k == tries - 1:
                raise
            print(f"  overpass error at {ox.settings.overpass_url} ({type(e).__name__}), retrying", flush=True)
            time.sleep(OVERPASS_BACKOFF_S)


def _download_graph(bbox: tuple, nodes_path: Path, edges_path: Path):
    nodes, edges = ox.graph_to_gdfs(_retry(lambda: ox.graph_from_bbox(bbox, network_type="drive", simplify=True)))
    edges = edges.reset_index(drop=True)
    for col in ("highway", "maxspeed", "lanes"):
        edges[col] = edges[col].map(lambda v: str(_first(v))) if col in edges else None
    nodes[["street_count", "geometry"]].to_parquet(nodes_path)
    edges[["highway", "maxspeed", "lanes", "geometry"]].to_parquet(edges_path)


def _download_polys(bbox: tuple, tags: dict, path: Path):
    try:
        g = _retry(lambda: ox.features_from_bbox(bbox, tags))
        g = g.geometry[g.geom_type.isin(["Polygon", "MultiPolygon"])]
    except ox._errors.InsufficientResponseError:  # no such features in the area
        g = gpd.GeoSeries(crs=4326)
    gpd.GeoDataFrame(geometry=g.reset_index(drop=True), crs=4326).to_parquet(path)


def _osm_layers(bbox: tuple, name: str, crs) -> tuple:
    """Drive network + land-use polygons for bbox; each layer cached as parquet in OSM_CACHE."""
    OSM_CACHE.mkdir(parents=True, exist_ok=True)
    path = lambda layer: OSM_CACHE / f"{name}_{layer}.parquet"
    if not path("edges").exists():
        _download_graph(bbox, path("nodes"), path("edges"))
    for layer, tags in POLY_TAGS.items():
        if not path(layer).exists():
            _download_polys(bbox, tags, path(layer))
    nodes = gpd.read_parquet(path("nodes")).to_crs(crs)
    edges = gpd.read_parquet(path("edges")).to_crs(crs)
    polys = {layer: gpd.read_parquet(path(layer)).geometry.to_crs(crs) for layer in POLY_TAGS}
    print(f"  {name}: {len(edges):,} road edges, " + ", ".join(f"{k} {len(v):,}" for k, v in polys.items()), flush=True)
    return nodes, edges, polys


def _area_features(locs: pd.DataFrame, bbox: tuple, name: str) -> pd.DataFrame:
    """Features for one compact study area (bbox = west, south, east, north)."""
    pts = gpd.GeoDataFrame(locs, geometry=gpd.points_from_xy(locs.lng, locs.lat), crs=4326)
    crs = pts.estimate_utm_crs()
    pts = pts.to_crs(crs)

    nodes, edges, polys = _osm_layers(bbox, name, crs)
    edges["road_class"] = edges["highway"].map(lambda h: ROAD_CLASS.get(str(_first(h)).replace("_link", ""), 0))
    junctions = nodes[nodes["street_count"] >= 3][["geometry"]].reset_index(drop=True)

    out = pd.DataFrame(index=pts.index)
    # Physical centerline density must not count two directions of one OSM edge.
    out = out.join(road_length_density(pts, edges))
    for r in BUFFERS_M:
        area = np.pi * r * r
        buf = gpd.GeoDataFrame(geometry=pts.buffer(r), crs=crs)
        n_junc = gpd.sjoin(buf, junctions, predicate="contains").groupby(level=0).size()
        out[f"intersections_per_km2_{r}"] = (n_junc / (area / 1e6)).reindex(out.index, fill_value=0)
        for layer, g in polys.items():
            out[f"{layer}_frac_{r}"] = _poly_frac(buf, g, area)

    near = gpd.sjoin_nearest(pts[["geometry"]], edges[["geometry", "road_class", "maxspeed", "lanes"]],
                             max_distance=NEAREST_ROAD_MAX_M, how="left")
    near = near[~near.index.duplicated()]
    out["road_class"] = near["road_class"].fillna(0)
    out["maxspeed"] = near["maxspeed"].map(_num)
    out["lanes"] = near["lanes"].map(_num)
    highways = edges[edges["road_class"] >= 5][["geometry"]]
    dist = gpd.sjoin_nearest(pts[["geometry"]], highways, distance_col="d", how="left")["d"]
    out["dist_highway_m"] = dist[~dist.index.duplicated()]
    out["is_highway"] = (out["road_class"] >= 5).astype(int)
    out.insert(0, "loc_id", locs["loc_id"].to_numpy())
    return out


def gis_features(locs: pd.DataFrame, area: pd.Series) -> pd.DataFrame:
    """Run _area_features separately per study area (e.g. Omaha, Lincoln) to keep OSM queries compact."""
    parts = []
    for name, sub in locs.groupby(area):
        bbox = (sub.lng.min() - PAD_DEG, sub.lat.min() - PAD_DEG, sub.lng.max() + PAD_DEG, sub.lat.max() + PAD_DEG)
        print(f"GIS area {name}: {len(sub):,} locations, bbox {np.round(bbox, 3)}", flush=True)
        parts.append(_area_features(sub.reset_index(drop=True), bbox, name))
    return pd.concat(parts, ignore_index=True)


GIS_COLUMNS = ([f"{p}_{r}" for r in BUFFERS_M for p in ["road_km_per_km2", "intersections_per_km2"]
                + [f"{n}_frac" for n in POLY_TAGS]]
               + ["road_class", "maxspeed", "lanes", "dist_highway_m", "is_highway"])

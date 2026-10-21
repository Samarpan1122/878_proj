"""Source-bound road geometry for conservative point and route audit calculations.

Geometry proximity does not establish a legal route, travel direction or a crash's
true road. Route sampling is an experimental linkage aid, not navigation advice.
"""
import argparse
import gzip
import hashlib
import json
import math
import threading
from pathlib import Path

from pyproj import Transformer
from shapely import from_wkb, to_wkb
from shapely.geometry import LineString, Point
from shapely.ops import transform
from shapely.strtree import STRtree
from shapely.errors import GEOSException

_PROJECT = Transformer.from_crs(4326, 26914, always_xy=True).transform
_LOCK = threading.Lock()
_CACHE = {}


def build_geometry(root):
    import geopandas as gpd
    root = Path(root)
    snapshot = json.loads((root / 'snapshot.json').read_text())
    path = root / 'segments.parquet'
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if snapshot['provenance']['roads_sha256'] != source_hash:
        raise ValueError('Road source differs from active screening snapshot')
    roads = gpd.read_parquet(path).to_crs(26914)
    payload = {'schema_version': 1, 'metric_crs': 'EPSG:26914',
               'roads_sha256': source_hash, 'simplification_tolerance_m': .5,
               'roads': [{'segment_id': str(row.segment_id),
                          'wkb': to_wkb(row.geometry.simplify(.5, preserve_topology=True), hex=True)}
                         for row in roads.itertuples()]}
    target = root / 'road-geometry.json.gz'
    with gzip.open(target, 'wt') as stream:
        json.dump(payload, stream, separators=(',', ':'), allow_nan=False)
    return {'file': str(target), 'bytes': target.stat().st_size, 'roads': len(roads),
            'roads_sha256': source_hash, 'simplification_tolerance_m': .5}


def load_geometry(root, snapshot):
    path = Path(root) / 'road-geometry.json.gz'
    info = path.stat()
    expected = snapshot.get('provenance', {}).get('roads_sha256')
    identities = frozenset(r['segment_id'] for r in snapshot['segments'])
    key = (str(path.resolve()), info.st_mtime_ns, info.st_size, expected, identities)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        try:
            with gzip.open(path, 'rb') as stream:
                raw = stream.read(40_000_001)
        except EOFError as exc:
            raise ValueError('Truncated road geometry archive') from exc
        if len(raw) > 40_000_000:
            raise ValueError('Geometry artifact exceeds bounded size')
        value = json.loads(raw)
        if (not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('metric_crs') != 'EPSG:26914'
                or not expected or value.get('roads_sha256') != expected
                or value.get('simplification_tolerance_m') != .5):
            raise ValueError('Geometry artifact is not bound to this road snapshot')
        records = value.get('roads', [])
        if not isinstance(records,list) or not 1 <= len(records) <= 20000 or any(
                not isinstance(r,dict) or not isinstance(r.get('segment_id'),str)
                or not isinstance(r.get('wkb'),str) for r in records):
            raise ValueError('Invalid road geometry records')
        ids = [r['segment_id'] for r in records]
        if (not ids or len(ids) > 20000 or len(set(ids)) != len(ids)
                or set(ids) != {r['segment_id'] for r in snapshot['segments']}):
            raise ValueError('Geometry segment identities do not match snapshot')
        try:
            geometries = [from_wkb(r['wkb']) for r in records]
        except GEOSException as exc:
            raise ValueError('Invalid road line encoding') from exc
        if any(g.is_empty or not g.is_valid or g.geom_type not in {'LineString','MultiLineString'} for g in geometries):
            raise ValueError('Invalid road line geometry')
        result = (ids, geometries, STRtree(geometries))
        # Bound process memory to the most recently used release.
        _CACHE.clear()
        _CACHE[key] = result
        return result


def nearest(point, index, max_distance_m=20., ambiguity_margin_m=6.):
    ids, geometries, tree = index
    candidates = tree.query(point.buffer(max_distance_m))
    distances = sorted((point.distance(geometries[int(i)]), ids[int(i)]) for i in candidates)
    distances = [(d,s) for d,s in distances if d <= max_distance_m]
    if not distances:
        return {'segment_id': None, 'status': 'outside_tolerance', 'distance_m': None, 'candidates': []}
    ambiguous = len(distances) > 1 and distances[1][0] - distances[0][0] <= ambiguity_margin_m
    return {'segment_id': None if ambiguous else distances[0][1],
            'status': 'ambiguous' if ambiguous else 'matched', 'distance_m': distances[0][0],
            'candidates': [{'segment_id':s, 'distance_m':d} for d,s in distances[:3]]}


def match_points(records, snapshot, root):
    index = load_geometry(root, snapshot)
    results = []
    for r in records:
        point = Point(*_PROJECT(r['lng'], r['lat']))
        results.append({'case_id': r['case_id'], **nearest(point, index)})
    return {'results': results, 'snapshot_built_at': snapshot['built_at'],
            'roads_sha256': snapshot['provenance']['roads_sha256'],
            'max_distance_m': 20, 'ambiguity_margin_m': 6,
            'limitations': ['Experimental proximity matching on 0.5m-simplified lines; not independently verified.',
                           'Parallel roads, junctions and grade separation may remain unresolved.',
                           'Submitted coordinates are not persisted by this application.']}


def match_route(coordinates, snapshot, root):
    if not 2 <= len(coordinates) <= 30000:
        raise ValueError('Route needs 2-30000 coordinate pairs')
    if any(len(c) != 2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in c)
           or not -105 <= c[0] <= -94 or not 39 <= c[1] <= 44 for c in coordinates):
        raise ValueError('Road risk linkage is limited to Nebraska and its immediate boundary')
    line = transform(_PROJECT, LineString(coordinates))
    if not 0 < line.length <= 200000:
        raise ValueError('Route length must be positive and at most 200km')
    index = load_geometry(root, snapshot)
    n = min(2000, max(1, math.ceil(line.length / 50)))
    step = line.length / n
    lengths = {}
    ambiguous = 0
    for i in range(n):
        hit = nearest(line.interpolate((i+.5)*step), index)
        if hit['segment_id'] is not None:
            lengths[hit['segment_id']] = lengths.get(hit['segment_id'],0.) + step / 1609.344
        elif hit['status'] == 'ambiguous':
            ambiguous += 1
    matched = sum(lengths.values())
    total = line.length / 1609.344
    return {'matched_legs': [{'segment_id':s,'length_miles':v} for s,v in sorted(lengths.items())],
            'unmatched_length_miles': max(0., total-matched), 'total_length_miles': total,
            'coverage_fraction': min(1.,matched/total), 'sample_spacing_m':step,
            'sample_count':n, 'ambiguous_sample_count':ambiguous,
            'roads_sha256': snapshot['provenance']['roads_sha256'],
            'limitations': ['Sampled geometric linkage; not a validated route-to-road assignment.',
                           'Unknown or ambiguous portions have no estimated risk; they are not zero risk.',
                           '20m match tolerance and 6m ambiguity margin on 0.5m-simplified road geometry.',
                           'Grade separation and road direction are not resolved by this linkage.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='data/safety')
    args = parser.parse_args()
    print(json.dumps(build_geometry(args.root), indent=2))

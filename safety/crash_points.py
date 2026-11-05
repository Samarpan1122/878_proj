"""Per-crash FARS points behind place search (contract: docs/CRASH_POINTS.md).

Coordinates live in numpy arrays; each crash stays as its raw JSON line and is
decoded only when a query returns it, keeping ~150k crashes well under 120 MB.
"""
from __future__ import annotations

import gzip
import json

import numpy as np

EARTH_KM = 6371.0088
MAX_RETURNED = 500
REQUIRED_FIELDS = {'id', 'year', 'month', 'day', 'hour', 'minute', 'lat', 'lng', 'fatals', 'peds', 'light', 'speeding', 'drinking'}


def load(path):
    """Stream crashes.jsonl.gz into {'meta', 'fields', 'lat', 'lng', 'rows'}; ValueError on a malformed artifact."""
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        meta = json.loads(handle.readline())
        fields = meta.get('fields') if isinstance(meta, dict) else None
        if not isinstance(fields, list) or not REQUIRED_FIELDS <= set(fields):
            raise ValueError('Crash artifact meta is missing required fields')
        lat_at, lng_at = fields.index('lat'), fields.index('lng')
        lats, lngs, rows = [], [], []
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, list) or len(row) != len(fields):
                raise ValueError('Crash row does not match the field list')
            lats.append(float(row[lat_at]))
            lngs.append(float(row[lng_at]))
            rows.append(line)
    return {'meta': meta, 'fields': fields, 'lat': np.array(lats), 'lng': np.array(lngs), 'rows': rows}


def _haversine_km(lat, lng, lats, lngs):
    p1, p2 = np.radians(lat), np.radians(lats)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lngs - lng) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def query(index, lat, lng, r_km):
    """Summary over every crash within r_km; at most the 500 nearest returned, newest first."""
    dlat = r_km / 110.57
    dlng = r_km / max(111.32 * np.cos(np.radians(lat)), 1e-6)
    box = np.flatnonzero((np.abs(index['lat'] - lat) <= dlat) & (np.abs(index['lng'] - lng) <= dlng))
    dist = _haversine_km(lat, lng, index['lat'][box], index['lng'][box])
    inside = dist <= r_km
    hits, dist = box[inside], dist[inside]
    fields = index['fields']
    crashes = [dict(zip(fields, json.loads(index['rows'][i])), distance_km=round(float(d), 2)) for i, d in zip(hits, dist)]

    by_year = {str(y): 0 for y in index['meta'].get('years') or []}
    for c in crashes:
        by_year[str(c['year'])] = by_year.get(str(c['year']), 0) + 1
    summary = {'fatal_crashes': len(crashes), 'fatalities': sum(c['fatals'] or 0 for c in crashes),
               'with_pedestrians': sum(1 for c in crashes if (c['peds'] or 0) > 0),
               'speeding': sum(1 for c in crashes if c['speeding']), 'drinking': sum(1 for c in crashes if c['drinking']),
               'dark': sum(1 for c in crashes if str(c['light'] or '').startswith('Dark')), 'by_year': dict(sorted(by_year.items()))}

    nearest = sorted(crashes, key=lambda c: c['distance_km'])[:MAX_RETURNED]
    nearest.sort(key=lambda c: tuple(-1 if c[k] is None else c[k] for k in ('year', 'month', 'day', 'hour', 'minute')), reverse=True)
    years = index['meta'].get('years') or []
    span = f'{min(years)}–{max(years)}' if years else ''
    return {'center': {'lat': lat, 'lng': lng}, 'radius_km': r_km, 'years': span,
            'source': f'NHTSA FARS {span} · fatal crashes only', 'total': len(crashes), 'returned': len(nearest),
            'truncated': len(crashes) > len(nearest), 'summary': summary, 'crashes': nearest}

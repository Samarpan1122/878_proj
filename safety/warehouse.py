"""Export reviewed safety artifacts as explicit-schema BigQuery NDJSON load files."""
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import force_2d
from shapely.geometry import Point

from safety.io import digest, write_json

SEGMENTS_SCHEMA = [
    {"name": name, "type": kind, "mode": "NULLABLE"}
    for name, kind in [("snapshot_date", "DATE"), ("segment_id", "STRING"), ("geometry", "GEOGRAPHY"),
                       ("aadt", "FLOAT64"), ("aadt_year", "INT64"), ("length_miles", "FLOAT64"),
                       ("source", "STRING"), ("properties", "JSON")]
]
CRASHES_SCHEMA = [
    {"name": name, "type": kind, "mode": "NULLABLE"}
    for name, kind in [("crash_id", "STRING"), ("year", "INT64"), ("geometry", "GEOGRAPHY"),
                       ("fatalities", "INT64"), ("source", "STRING")]
]


def _number(value, integer=False):
    if pd.isna(value):
        return None
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError("Warehouse numeric values must be finite")
    if integer and float(value) != int(value):
        raise ValueError("Warehouse integer field contains a fraction")
    return int(value) if integer else float(value)


def _unique(frame, field):
    if field not in frame or frame[field].isna().any() or frame[field].duplicated().any():
        raise ValueError(f"Warehouse {field} values must be nonnull and unique")


def export_bigquery(root, output_dir):
    """Return export manifest; no cloud calls, no legacy or agency-record inputs.

    The native JSON properties value is an object, not double-encoded text:
    https://cloud.google.com/bigquery/docs/json-data#load_from_newline_delimited_json_files
    WKT strings need an explicit GEOGRAPHY schema, never schema autodetection.
    """
    root, output_dir = Path(root), Path(output_dir)
    roads = gpd.read_parquet(root / "segments.parquet").to_crs(4326)
    crashes = pd.read_parquet(root / "crashes.parquet")
    _unique(roads, "segment_id")
    _unique(crashes, "crash_id")
    if not roads.source.eq("ndot_aadt").all() or not crashes.source.eq("fars").all():
        raise ValueError("Warehouse exporter only permits independently ingested NDOT/FARS sources")
    snapshot_path = root / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else {}
    built_at = snapshot.get("built_at") or datetime.now(timezone.utc).isoformat()
    snapshot_date = datetime.fromisoformat(built_at).date().isoformat()
    screening_path = root / "screening.parquet"
    screening = pd.read_parquet(screening_path) if screening_path.exists() else None
    if screening is not None:
        _unique(screening, "segment_id")
        screening = screening.set_index("segment_id")
    output_dir.mkdir(parents=True, exist_ok=True)
    unlocated = 0
    with tempfile.TemporaryDirectory(prefix="warehouse-", dir=output_dir) as temporary:
        staging = Path(temporary)
        with (staging / "segments.ndjson").open("w") as stream:
            for _, row in roads.iterrows():
                geometry = row.geometry
                if geometry is None or geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ["LineString", "MultiLineString"]:
                    raise ValueError("Warehouse road geometry must be a valid, nonempty line")
                west, south, east, north = geometry.bounds
                if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
                    raise ValueError("Warehouse road coordinates outside WGS84 bounds")
                properties = json.loads(row.drop(labels=["geometry"]).to_json())
                if screening is not None and row.segment_id in screening.index:
                    properties.update(json.loads(screening.loc[row.segment_id].drop(labels=["geometry"], errors="ignore").to_json()))
                record = {"snapshot_date": snapshot_date, "segment_id": str(row.segment_id),
                    "geometry": force_2d(geometry).wkt, "aadt": _number(row.aadt),
                    "aadt_year": _number(row.aadt_year, integer=True), "length_miles": _number(row.length_miles),
                    "source": "ndot_aadt", "properties": properties}
                stream.write(json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n")
        with (staging / "crashes.ndjson").open("w") as stream:
            for row in crashes.itertuples(index=False):
                lat, lng = _number(row.lat), _number(row.lng)
                geometry = None
                if lat is not None and lng is not None:
                    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
                        raise ValueError("Warehouse crash coordinates outside WGS84 bounds")
                    geometry = Point(lng, lat).wkt
                else:
                    unlocated += 1
                record = {"crash_id": str(row.crash_id), "year": _number(row.year, integer=True),
                    "geometry": geometry, "fatalities": _number(row.fatalities, integer=True), "source": "fars"}
                stream.write(json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n")
        write_json(staging / "segments-schema.json", SEGMENTS_SCHEMA)
        write_json(staging / "crashes-schema.json", CRASHES_SCHEMA)
        manifest = {"snapshot_date": snapshot_date, "segments": len(roads), "crashes": len(crashes),
            "unlocated_crashes": unlocated, "commercial_ready": False,
            "note": "FARS national fatal crashes; Nebraska exposure only. NDOT reuse terms require confirmation.",
            "input_sha256": {name: digest(root / name) for name in ["segments.parquet", "crashes.parquet"]},
            "files": {name: {"path": str(output_dir / name), "sha256": digest(staging / name)}
                      for name in ["segments.ndjson", "crashes.ndjson", "segments-schema.json", "crashes-schema.json"]}}
        for name in manifest["files"]:
            (staging / name).replace(output_dir / name)
        write_json(output_dir / "manifest.json", manifest)
    return manifest

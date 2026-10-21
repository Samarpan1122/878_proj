"""Optional transactional PostGIS mirror. Filesystem artifacts remain the local default."""
import json
import math
import os
from pathlib import Path


def connect(database_url=None):
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is required for optional PostGIS storage")
    import psycopg
    return psycopg.connect(url)


def import_snapshot(root, database_url=None):
    """Replace one complete road/crash snapshot atomically; a failed import rolls back."""
    import geopandas as gpd
    import pandas as pd
    root = Path(root)
    segments = gpd.read_parquet(root / "segments.parquet").to_crs(4326)
    crashes = pd.read_parquet(root / "crashes.parquet")
    screening_path = root / "screening.parquet"
    screening = pd.read_parquet(screening_path).set_index("segment_id") if screening_path.exists() else None
    if segments.segment_id.duplicated().any() or crashes.crash_id.duplicated().any():
        raise ValueError("Snapshot IDs must be unique")
    if screening is not None and screening.index.duplicated().any():
        raise ValueError("Screening segment IDs must be unique")
    schema = Path(__file__).resolve().parent.parent / "infra" / "postgis.sql"
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema.read_text())
            cursor.execute("DELETE FROM safety.crashes")
            cursor.execute("DELETE FROM safety.segments")
            for _, row in segments.iterrows():
                properties = json.loads(pd.Series(row.drop(labels=["geometry"])).to_json())
                if screening is not None and row.segment_id in screening.index:
                    properties.update(json.loads(screening.loc[row.segment_id].drop(labels=["geometry"], errors="ignore").to_json()))
                cursor.execute("""INSERT INTO safety.segments(segment_id, geom, properties)
                    VALUES (%s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)), %s::jsonb)""",
                    (str(row.segment_id), json.dumps(row.geometry.__geo_interface__), json.dumps(properties)))
            for _, row in crashes.iterrows():
                properties = json.loads(row.to_json())
                located = pd.notna(row.lng) and pd.notna(row.lat)
                cursor.execute("""INSERT INTO safety.crashes(crash_id, year, geom, properties)
                    VALUES (%s,%s,CASE WHEN %s THEN ST_SetSRID(ST_MakePoint(%s,%s),4326) ELSE NULL END,%s::jsonb)""",
                    (str(row.crash_id), int(row.year), bool(located), float(row.lng) if located else None,
                     float(row.lat) if located else None, json.dumps(properties)))
    return {"segments": len(segments), "crashes": len(crashes)}


def nearby_segments(lat, lng, radius_miles=5, limit=100, database_url=None):
    if not all(math.isfinite(v) for v in [lat, lng, radius_miles]) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
        raise ValueError("Invalid coordinates or radius")
    if not 0 < radius_miles <= 100 or not 1 <= limit <= 1000:
        raise ValueError("Radius must be (0,100] miles and limit [1,1000]")
    with connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT segment_id, properties, ST_AsGeoJSON(geom)::json,
                ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) AS distance_m
                FROM safety.segments
                WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)
                ORDER BY distance_m, segment_id LIMIT %s""", (lng, lat, lng, lat, radius_miles * 1609.344, limit))
            return [{"segment_id": r[0], "properties": r[1], "geometry": r[2], "distance_m": r[3]} for r in cursor.fetchall()]

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS safety;
CREATE TABLE IF NOT EXISTS safety.segments (
    segment_id text PRIMARY KEY,
    geom geometry(MultiLineString,4326) NOT NULL,
    properties jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ST_IsValid(geom)),
    CHECK (ST_XMin(Box3D(geom)) >= -180 AND ST_XMax(Box3D(geom)) <= 180),
    CHECK (ST_YMin(Box3D(geom)) >= -90 AND ST_YMax(Box3D(geom)) <= 90)
);
CREATE INDEX IF NOT EXISTS segments_geography ON safety.segments USING gist ((geom::geography));
CREATE TABLE IF NOT EXISTS safety.crashes (
    crash_id text PRIMARY KEY,
    year integer NOT NULL CHECK (year BETWEEN 1900 AND 2100),
    geom geometry(Point,4326),
    properties jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CHECK (geom IS NULL OR (ST_X(geom) BETWEEN -180 AND 180 AND ST_Y(geom) BETWEEN -90 AND 90))
);
CREATE INDEX IF NOT EXISTS crashes_geography ON safety.crashes USING gist ((geom::geography));

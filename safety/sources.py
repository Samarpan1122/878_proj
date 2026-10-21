"""Official FARS crash and Nebraska AADT adapters. No Kaggle imports or weights."""
import json
import zipfile
from pathlib import Path
from urllib.parse import urlencode

import geopandas as gpd
import numpy as np
import pandas as pd

from safety.io import digest, download, get_json, now, write_json

FARS_BASE = "https://static.nhtsa.gov/nhtsa/downloads/FARS"
AADT_LAYER = "https://giscat.ne.gov/dot/rest/services/AnnualAverageDailyTrafficSegmentsDOT/MapServer/0"
SOURCES = {
    "fars": {
        "name": "NHTSA Fatality Analysis Reporting System",
        "url": "https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars",
        "rights": "US federal government data; public domain",
        "commercial_use": True,
        "scope": "Fatal motor-vehicle traffic crashes only; not all crashes or all injuries.",
    },
    "ndot_aadt": {
        "name": "Nebraska DOT AADT segments", "url": AADT_LAYER,
        "rights": "Publicly accessible. Redistribution/commercial terms require confirmation from NDOT.",
        "commercial_use": False,
        "public_use_policy": "https://dot.nebraska.gov/policies-and-disclaimers/",
        "public_use_note": "Published policy allows use of website information at the user's risk. Separate commercial redistribution terms remain unconfirmed.",
        "scope": "Current published traffic-count vintage; do not assume historical alignment.",
    },
    "ndot_crashes": {
        "name": "Nebraska DOT crash records", "url": "https://dot.nebraska.gov/safety/crash/",
        "rights": "Agency agreement required for supplied record-level extract.",
        "commercial_use": False, "scope": "Not connected; no all-crash completeness claim.",
    },
    "nws": {
        "name": "NOAA National Weather Service", "url": "https://www.weather.gov/documentation/services-web-api",
        "rights": "US federal government weather data", "commercial_use": True,
        "scope": "Weather alerts; never interpreted as observed crash incidents.",
    },
    "legacy": {
        "name": "US Accidents research dataset", "url": "https://www.kaggle.com/datasets/sobhanmoosavi/us-accidents",
        "rights": "CC BY-NC-SA 4.0 per existing project provenance", "commercial_use": False,
        "scope": "Excluded from safety engine, its models, API and container.",
    },
}


def normalize_fars(frame, year):
    frame = frame.rename(columns=lambda c: c.lstrip("\ufeffï»¿").strip())
    if frame.columns.duplicated().any():
        raise ValueError("Duplicate FARS schema columns after header normalization")
    required = {"STATE", "ST_CASE", "YEAR", "LATITUDE", "LONGITUD", "FATALS"}
    if missing := required - set(frame):
        raise ValueError(f"FARS schema missing: {sorted(missing)}")
    d = frame.copy()
    for col in required:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    if d.YEAR.isna().any() or not d.YEAR.eq(year).all():
        raise ValueError("FARS archive year disagrees with rows")
    if d.duplicated(["STATE", "ST_CASE"]).any():
        raise ValueError("Duplicate FARS crash IDs")
    if (d.FATALS.isna().any() or not d.FATALS.between(1, 999).all()
            or not d.FATALS.eq(np.floor(d.FATALS)).all()):
        raise ValueError("Invalid fatality counts")
    if (not d.STATE.between(1, 78).all() or not d.STATE.eq(np.floor(d.STATE)).all()
            or not d.ST_CASE.between(10000, 789999).all() or not d.ST_CASE.eq(np.floor(d.ST_CASE)).all()
            or not (d.ST_CASE // 10000).eq(d.STATE).all()):
        raise ValueError("Invalid crash identity")
    # 77/88/99 are coordinate missing-value codes. Keep records, flag spatial availability.
    valid = d.LATITUDE.between(18, 72) & d.LONGITUD.between(-180, -65)
    out = pd.DataFrame({
        "crash_id": "FARS-" + d.YEAR.astype(int).astype(str) + "-" + d.ST_CASE.astype(int).astype(str),
        "year": d.YEAR.astype(int), "state_fips": d.STATE.astype(int),
        "lat": d.LATITUDE.where(valid), "lng": d.LONGITUD.where(valid),
        "fatalities": d.FATALS.astype(int), "source": "fars", "outcome": "fatal_crash",
    })
    for original, name in [("RUR_URB", "rural_urban"), ("FUNC_SYS", "functional_class"),
                            ("MAN_COLL", "collision_type"), ("LGT_COND", "light_condition")]:
        out[name] = pd.to_numeric(d[original], errors="coerce") if original in d else float("nan")
    return out


def ingest_fars(root, years, archive_dir=None):
    root = Path(root)
    frames, manifests = [], []
    for year in sorted(set(years)):
        if isinstance(year, bool) or int(year) != year or not 2015 <= year <= 2100:
            raise ValueError("Adapter supports FARS 2015+ schema")
        url = f"{FARS_BASE}/{year}/National/FARS{year}NationalCSV.zip"
        path = root / "raw" / f"FARS{year}.zip"
        supplied = Path(archive_dir) / f"geocrash-fars{year}.zip" if archive_dir else path
        if supplied.exists():
            path = supplied
        elif not path.exists():
            download(url, path)
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if Path(n).name.lower() == "accident.csv"]
            if len(names) != 1:
                raise ValueError("Expected exactly one FARS accident.csv")
            if archive.getinfo(names[0]).file_size > 200_000_000:
                raise ValueError("FARS accident table exceeds extraction limit")
            with archive.open(names[0]) as stream:
                d = normalize_fars(pd.read_csv(stream, encoding="latin1", low_memory=False), year)
            if d.empty:
                raise ValueError("National FARS accident table is empty")
        frames.append(d)
        manifests.append({"source": "fars", "url": url, "year": year, "sha256": digest(path),
                          "retrieved_at": now(), "rows": len(d), "unlocated": int(d.lat.isna().sum()),
                          "release_status": "official_download_archive; final/revised status not independently verified"})
    if not frames:
        raise ValueError("At least one FARS year is required")
    root.mkdir(parents=True, exist_ok=True)
    result = pd.concat(frames, ignore_index=True)
    result.to_parquet(root / "crashes.parquet", index=False)
    write_json(root / "fars-manifest.json", manifests)
    return result


def normalize_aadt(features):
    if not features:
        raise ValueError("NDOT returned no road segments")
    g = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    fields = {"OBJECTID": "segment_id", "FIRST_RouteID": "route", "FIRST_COUNT_YEAR": "aadt_year",
              "FIRST_VEH_ADT_TOT_NUM": "aadt"}
    if missing := set(fields) - set(g):
        raise ValueError(f"NDOT schema missing: {sorted(missing)}")
    g = g.rename(columns=fields)[list(fields.values()) + ["geometry"]]
    ids = pd.to_numeric(g.segment_id, errors="coerce")
    if (not np.isfinite(ids).all() or not ids.gt(0).all() or not ids.eq(np.floor(ids)).all()
            or ids.duplicated().any()):
        raise ValueError("AADT segment IDs must be unique")
    if not g.geometry.geom_type.isin(["LineString", "MultiLineString"]).all() or not g.is_valid.all():
        raise ValueError("AADT geometries must be valid road lines")
    bounds = g.bounds
    if (not np.isfinite(bounds).all().all() or not bounds.minx.ge(-180).all() or not bounds.maxx.le(180).all()
            or not bounds.miny.ge(-90).all() or not bounds.maxy.le(90).all()):
        raise ValueError("AADT road coordinates must be finite longitude/latitude")
    g.segment_id = "NDOT-" + ids.astype("int64").astype(str)
    g["route"] = g.route.fillna("Unspecified route")
    for col in ["aadt", "aadt_year"]:
        g[col] = pd.to_numeric(g[col], errors="coerce")
    g["aadt_year"] = g.aadt_year.where(g.aadt_year.between(1900, 2100) & g.aadt_year.eq(np.floor(g.aadt_year)))
    g["aadt"] = g.aadt.where(np.isfinite(g.aadt) & g.aadt.gt(0))
    projected = g.to_crs(26914)  # Nebraska, UTM 14N; metres, not degrees or Web Mercator length.
    g["length_miles"] = projected.length / 1609.344
    if not np.isfinite(g.length_miles).all() or not g.length_miles.gt(0).all():
        raise ValueError("AADT road lengths must be finite and positive")
    points = projected.geometry.interpolate(0.5, normalized=True).to_crs(4326)
    g["lat"], g["lng"] = points.y, points.x
    g["source"] = "ndot_aadt"
    g["facility_type"] = "unknown"  # Do not infer road design from crash-selected records.
    return g


def ingest_aadt(root):
    root = Path(root)
    features, offset, seen_ids = [], 0, set()
    while True:
        params = {"where": "1=1", "outFields": "OBJECTID,FIRST_RouteID,FIRST_COUNT_YEAR,FIRST_VEH_ADT_TOT_NUM",
                  "outSR": 4326, "returnGeometry": "true", "f": "geojson", "orderByFields": "OBJECTID",
                  "resultOffset": offset, "resultRecordCount": 1000}
        response = get_json(AADT_LAYER + "/query?" + urlencode(params))
        if not isinstance(response, dict) or "error" in response or not isinstance(response.get("features"), list):
            raise ValueError("NDOT did not return a feature collection")
        page = response["features"]
        has_more = bool(response.get("exceededTransferLimit") or
                        (response.get("properties") or {}).get("exceededTransferLimit"))
        if not page and has_more:
            raise ValueError("NDOT pagination ended before declared transfer limit")
        for feature in page:
            ident = str(feature.get("properties", {}).get("OBJECTID"))
            if ident in seen_ids:
                raise ValueError("NDOT pagination repeated a segment ID")
            seen_ids.add(ident)
        features.extend(page)
        offset += len(page)
        if offset > 150_000:
            raise ValueError("Unexpectedly large NDOT response")
        if not page or (len(page) < 1000 and not has_more):
            break
    if not features:
        raise ValueError("NDOT returned no road segments")
    root.mkdir(parents=True, exist_ok=True)
    result = normalize_aadt(features)
    write_json(root / "raw" / "ndot-aadt.geojson", {"type": "FeatureCollection", "features": features})
    result.to_parquet(root / "segments.parquet", index=False)
    write_json(root / "aadt-manifest.json", {"source": "ndot_aadt", "url": AADT_LAYER,
        "sha256": digest(root / "raw" / "ndot-aadt.geojson"), "retrieved_at": now(),
        "rows": len(result), "count_years": sorted(result.aadt_year.dropna().astype(int).unique().tolist()),
        "commercial_use": False})
    return result


def import_state_crashes(csv_path, agreement_path, root):
    """Stage agency data separately; never combine FARS with overlapping state crash records."""
    agreement = json.loads(Path(agreement_path).read_text())
    if not isinstance(agreement, dict) or not all(agreement.get(k) for k in ["provider", "terms_url", "permitted_use", "approved_by", "coverage_start", "coverage_end"]):
        raise ValueError("Agency provenance and coverage agreement is incomplete")
    d = pd.read_csv(csv_path)
    required = {"crash_id", "date", "lat", "lng", "severity_kabco"}
    if required - set(d) or d.crash_id.isna().any() or d.crash_id.duplicated().any():
        raise ValueError("State extract requires unique IDs, date, lat/lng and severity_kabco")
    dates = pd.to_datetime(d.date, errors="coerce")
    if dates.isna().any() or not dates.dt.normalize().between(pd.Timestamp(agreement["coverage_start"]).normalize(), pd.Timestamp(agreement["coverage_end"]).normalize()).all():
        raise ValueError("State dates outside declared coverage")
    if not d.severity_kabco.isin(list("KABCO")).all():
        raise ValueError("State severity must use KABCO; Kaggle 1–4 is not injury severity")
    if not pd.to_numeric(d.lat, errors="coerce").between(39, 44).all() or not pd.to_numeric(d.lng, errors="coerce").between(-105, -94).all():
        raise ValueError("State coordinates outside Nebraska envelope")
    Path(root).mkdir(parents=True, exist_ok=True)
    d.to_parquet(Path(root) / "agency-crashes.parquet", index=False)
    write_json(Path(root) / "agency-manifest.json", {**agreement, "sha256": digest(csv_path), "rows": len(d),
        "retrieved_at": now(), "status": "staged; requires coverage and linkage review before modeling"})
    return len(d)

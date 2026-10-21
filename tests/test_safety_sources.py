"""Offline source-contract and failure-path checks; never call external services."""
import hashlib
import io as streamio
import json
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from safety import io, sources


def fars_frame():
    return pd.DataFrame({"STATE": [31, 31], "ST_CASE": [310001, 310002], "YEAR": [2021, 2021],
        "LATITUDE": [41.2, 99.999], "LONGITUD": [-96., 999.99], "FATALS": [2, 1],
        "RUR_URB": [1, 2], "MAN_COLL": [2, 6]})


def archive(path, frame=None, names=("nested/ACCIDENT.CSV",)):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name in names:
            z.writestr(name, (fars_frame() if frame is None else frame).to_csv(index=False))
    return path


def feature(ident=1, **properties):
    return {"type": "Feature", "properties": {"OBJECTID": ident, "FIRST_RouteID": None,
             "FIRST_COUNT_YEAR": 2025, "FIRST_VEH_ADT_TOT_NUM": 5000, **properties},
            "geometry": {"type": "LineString", "coordinates": [[-96., 41.], [-96.01, 41.]]}}


def test_fars_normalizes_sentinels_bom_and_optional_context():
    frame = fars_frame().rename(columns={"STATE": "ï»¿STATE"})
    result = sources.normalize_fars(frame, 2021)
    assert result.crash_id.to_list() == ["FARS-2021-310001", "FARS-2021-310002"]
    assert result.fatalities.to_list() == [2, 1]
    assert result.loc[1, ["lat", "lng"]].isna().all()
    assert result.functional_class.isna().all()
    assert result.rural_urban.to_list() == [1, 2]
    assert result.outcome.eq("fatal_crash").all()


@pytest.mark.parametrize("column,value,message", [
    ("YEAR", 2020, "year"), ("YEAR", None, "year"),
    ("ST_CASE", 310001.5, "identity"), ("ST_CASE", 320001, "identity"),
    ("STATE", 31.5, "identity"), ("STATE", None, "identity"),
    ("FATALS", 1.5, "fatality"), ("FATALS", 0, "fatality"), ("FATALS", float("inf"), "fatality")])
def test_fars_rejects_corrupt_counts_and_identifiers(column, value, message):
    frame = fars_frame().astype({column: "float64"})
    frame.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        sources.normalize_fars(frame, 2021)


def test_fars_rejects_duplicates_and_missing_schema():
    with pytest.raises(ValueError, match="Duplicate"):
        sources.normalize_fars(pd.concat([fars_frame(), fars_frame().iloc[:1]]), 2021)
    with pytest.raises(ValueError, match="missing"):
        sources.normalize_fars(fars_frame().drop(columns="STATE"), 2021)
    f = fars_frame()
    f["\ufeffSTATE"] = f.STATE
    with pytest.raises(ValueError, match="Duplicate"):
        sources.normalize_fars(f, 2021)


def test_ingest_fars_supplied_zip_and_provenance(tmp_path, monkeypatch):
    supplied = archive(tmp_path / "archives" / "geocrash-fars2021.zip")
    monkeypatch.setattr(sources, "download", lambda *a, **kw: pytest.fail("Supplied archive must not download"))
    result = sources.ingest_fars(tmp_path / "data", [2021, 2021], archive_dir=supplied.parent)
    assert len(result) == 2
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "data/crashes.parquet"), result)
    manifest = json.loads((tmp_path / "data/fars-manifest.json").read_text())
    assert len(manifest) == 1 and manifest[0]["unlocated"] == 1
    assert "not independently verified" in manifest[0]["release_status"]
    assert manifest[0]["sha256"] == hashlib.sha256(supplied.read_bytes()).hexdigest()


def test_ingest_fars_downloads_missing_archive_once_and_reuses_cache(tmp_path, monkeypatch):
    urls = []

    def fixture_download(url, destination):
        urls.append(url)
        return archive(destination)

    monkeypatch.setattr(sources, "download", fixture_download)
    sources.ingest_fars(tmp_path, [2021])
    sources.ingest_fars(tmp_path, [2021])
    assert len(urls) == 1 and "2021/National/FARS2021NationalCSV.zip" in urls[0]


@pytest.mark.parametrize("names", [("person.csv",), ("accident.csv", "nested/accident.csv")])
def test_fars_archive_requires_exactly_one_accident_table(tmp_path, names):
    archive(tmp_path / "raw/FARS2021.zip", names=names)
    with pytest.raises(ValueError, match="exactly one"):
        sources.ingest_fars(tmp_path, [2021])


def test_fars_empty_or_unsupported_year_fails(tmp_path):
    for years in [[], [2014], [2021.5]]:
        with pytest.raises(ValueError):
            sources.ingest_fars(tmp_path, years)
    archive(tmp_path / "raw/FARS2021.zip", frame=fars_frame().iloc[:0])
    with pytest.raises(ValueError, match="empty"):
        sources.ingest_fars(tmp_path, [2021])


def test_fars_extraction_is_bounded(tmp_path, monkeypatch):
    archive(tmp_path / "raw/FARS2021.zip")
    original = zipfile.ZipFile.getinfo

    def oversized(self, name):
        info = original(self, name)
        info.file_size = 200_000_001
        return info

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", oversized)
    with pytest.raises(ValueError, match="extraction limit"):
        sources.ingest_fars(tmp_path, [2021])


def test_aadt_normalizes_metric_length_unknown_facility_and_invalid_exposure():
    g = sources.normalize_aadt([feature(), feature(2, FIRST_COUNT_YEAR=2025.5, FIRST_VEH_ADT_TOT_NUM=-1)])
    assert g.segment_id.to_list() == ["NDOT-1", "NDOT-2"]
    assert .50 < g.length_miles.iloc[0] < .54
    assert g.facility_type.eq("unknown").all() and g.route.eq("Unspecified route").all()
    assert np.isnan(g.aadt_year.iloc[1]) and np.isnan(g.aadt.iloc[1])
    assert g.crs.to_epsg() == 4326


def test_aadt_rejects_duplicate_ids_missing_schema_nonroad_and_invalid_projection():
    with pytest.raises(ValueError, match="unique"):
        sources.normalize_aadt([feature(1), feature("1")])
    bad = feature()
    del bad["properties"]["FIRST_COUNT_YEAR"]
    with pytest.raises(ValueError, match="missing"):
        sources.normalize_aadt([bad])
    bad = feature()
    bad["geometry"] = {"type": "Point", "coordinates": [-96., 41.]}
    with pytest.raises(ValueError, match="road lines"):
        sources.normalize_aadt([bad])
    bad["geometry"] = {"type": "LineString", "coordinates": [[-96., 91.], [-95., 91.]]}
    with pytest.raises(ValueError, match="coordinates"):
        sources.normalize_aadt([bad])
    with pytest.raises(ValueError, match="no road"):
        sources.normalize_aadt([])


def test_ndot_paginates_nested_transfer_limit_and_keeps_rights_unapproved(tmp_path, monkeypatch):
    pages = [{"features": [feature()], "properties": {"exceededTransferLimit": True}},
             {"features": [feature(2)]}]
    offsets = []

    def fetch(url):
        offsets.append(parse_qs(urlparse(url).query)["resultOffset"][0])
        return pages.pop(0)

    monkeypatch.setattr(sources, "get_json", fetch)
    result = sources.ingest_aadt(tmp_path)
    assert len(result) == 2 and offsets == ["0", "1"]
    manifest = json.loads((tmp_path / "aadt-manifest.json").read_text())
    assert manifest["commercial_use"] is False and manifest["count_years"] == [2025]
    assert manifest["sha256"] == io.digest(tmp_path / "raw/ndot-aadt.geojson")
    assert len(gpd.read_parquet(tmp_path / "segments.parquet")) == 2


@pytest.mark.parametrize("response,message", [({"error": {}}, "feature collection"),
    ({"features": "invalid"}, "feature collection"), ({"features": []}, "no road"),
    ({"features": [], "exceededTransferLimit": True}, "pagination ended")])
def test_ndot_rejects_error_or_incomplete_pages(tmp_path, monkeypatch, response, message):
    monkeypatch.setattr(sources, "get_json", lambda url: response)
    with pytest.raises(ValueError, match=message):
        sources.ingest_aadt(tmp_path)
    assert not (tmp_path / "segments.parquet").exists()


def test_ndot_repeated_pages_fail_without_overwriting_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "get_json", lambda url: {"features": [feature()], "exceededTransferLimit": True})
    with pytest.raises(ValueError, match="repeated"):
        sources.ingest_aadt(tmp_path)
    assert not (tmp_path / "raw/ndot-aadt.geojson").exists()


def agency_files(tmp_path):
    data = pd.DataFrame({"crash_id": ["agency-1"], "date": ["2021-12-31 23:59:00"],
                         "lat": [41.], "lng": [-96.], "severity_kabco": ["K"]})
    agreement = {"provider": "Fixture agency", "terms_url": "https://example.org/terms",
        "permitted_use": "Research pilot", "approved_by": "Fixture reviewer",
        "coverage_start": "2021-01-01", "coverage_end": "2021-12-31"}
    csv, rights = tmp_path / "agency.csv", tmp_path / "agreement.json"
    data.to_csv(csv, index=False)
    rights.write_text(json.dumps(agreement))
    return csv, rights, data, agreement


def test_agency_data_remains_separate_with_explicit_review_status(tmp_path):
    csv, rights, _, agreement = agency_files(tmp_path)
    root = tmp_path / "staged"
    assert sources.import_state_crashes(csv, rights, root) == 1
    assert (root / "agency-crashes.parquet").exists() and not (root / "crashes.parquet").exists()
    manifest = json.loads((root / "agency-manifest.json").read_text())
    assert manifest["permitted_use"] == agreement["permitted_use"]
    assert "requires coverage and linkage review" in manifest["status"]
    assert manifest["sha256"] == io.digest(csv)


@pytest.mark.parametrize("column,value,message", [("date", "2022-01-01", "coverage"),
    ("date", "invalid", "coverage"), ("severity_kabco", "4", "KABCO"),
    ("lat", 0., "Nebraska"), ("crash_id", None, "unique")])
def test_agency_rejects_unusable_data(tmp_path, column, value, message):
    csv, rights, data, _ = agency_files(tmp_path)
    data.loc[0, column] = value
    data.to_csv(csv, index=False)
    with pytest.raises(ValueError, match=message):
        sources.import_state_crashes(csv, rights, tmp_path / "staged")


def test_agency_requires_documented_permission(tmp_path):
    csv, rights, _, agreement = agency_files(tmp_path)
    del agreement["approved_by"]
    rights.write_text(json.dumps(agreement))
    with pytest.raises(ValueError, match="agreement"):
        sources.import_state_crashes(csv, rights, tmp_path / "staged")


def test_atomic_json_rejects_nan_preserves_cache_and_removes_temporary_file(tmp_path):
    path = tmp_path / "state.json"
    io.write_json(path, {"version": 1})
    with pytest.raises(ValueError):
        io.write_json(path, {"bad": float("nan")})
    assert json.loads(path.read_text()) == {"version": 1}
    assert list(tmp_path.iterdir()) == [path]
    assert io.now().endswith("+00:00")


def test_atomic_json_removes_temporary_file_on_failed_replace(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text("old")

    def fail_replace(self, target):
        raise PermissionError("fixture denied rename")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(PermissionError):
        io.write_json(path, {"version": 2})
    assert path.read_text() == "old" and list(tmp_path.iterdir()) == [path]


def test_bounded_download_preserves_old_cache_and_cleans_temp(tmp_path, monkeypatch):
    dest = tmp_path / "source"
    dest.write_bytes(b"old")
    monkeypatch.setattr(io, "urlopen", lambda *a, **kw: streamio.BytesIO(b"oversized"))
    with pytest.raises(ValueError, match="size limit"):
        io.download("https://example.org/data", dest, max_bytes=3)
    assert dest.read_bytes() == b"old" and list(tmp_path.iterdir()) == [dest]
    for limit in [0, -1, True, 1.5]:
        with pytest.raises(ValueError, match="positive integer"):
            io.download("https://example.org/data", dest, max_bytes=limit)


def test_download_retries_transient_failure_and_sets_agent(tmp_path, monkeypatch):
    requests, delays = [], []

    def response(request, timeout):
        requests.append(request)
        assert timeout == 60
        if len(requests) < 3:
            raise URLError("fixture temporary failure")
        return streamio.BytesIO(b"complete")

    monkeypatch.setenv("NWS_USER_AGENT", "Fixture contact")
    monkeypatch.setattr(io, "urlopen", response)
    monkeypatch.setattr(io.time, "sleep", delays.append)
    dest = io.download("https://example.org/data", tmp_path / "file", max_bytes=8)
    assert dest.read_bytes() == b"complete" and delays == [1, 2]
    assert requests[-1].get_header("User-agent") == "Fixture contact"


def test_download_stops_after_third_failure_and_does_not_retry_404(tmp_path, monkeypatch):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("fixture timeout")

    monkeypatch.setattr(io, "urlopen", fail)
    monkeypatch.setattr(io.time, "sleep", lambda seconds: None)
    with pytest.raises(TimeoutError):
        io.download("https://example.org/data", tmp_path / "file")
    assert len(calls) == 3
    calls.clear()

    def missing(*args, **kwargs):
        calls.append(1)
        raise HTTPError("https://example.org/data", 404, "fixture missing", {}, None)

    monkeypatch.setattr(io, "urlopen", missing)
    with pytest.raises(HTTPError):
        io.download("https://example.org/data", tmp_path / "file")
    assert len(calls) == 1 and not list(tmp_path.iterdir())


def test_get_json_bounds_response_and_rejects_nonstandard_numbers(monkeypatch):
    limits = []

    def fixture(url, dest, max_bytes):
        limits.append(max_bytes)
        dest.write_text('{"ok": true}')
        return dest

    monkeypatch.setattr(io, "download", fixture)
    assert io.get_json("https://example.org/data") == {"ok": True}
    assert limits == [25_000_000]

    def nonfinite(url, dest, max_bytes):
        dest.write_text('{"bad": NaN}')
        return dest

    monkeypatch.setattr(io, "download", nonfinite)
    with pytest.raises(ValueError, match="Nonfinite"):
        io.get_json("https://example.org/data")

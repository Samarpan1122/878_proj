import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from safety import database, feeds, monitoring
from safety import cloud_job
from safety.io import write_json


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def incident(identity="1", coords=None):
    return {"id": identity, "properties": {"description": "Agency observation"},
            "geometry": {"type": "Point", "coordinates": coords if coords is not None else [-96, 41]}}


def agreement():
    return {"url": "https://agency.example/feed?token=private", "provider": "Agency",
            "terms_url": "https://agency.example/terms", "permitted_use": "pilot", "approved_by": "operator"}


def test_normalization_deduplication_and_weather_identity():
    rows = feeds.normalize_incidents(collection(incident(), incident(), incident(2)))
    assert len(rows) == 2 and rows[0]["lng"] == -96
    assert rows[0]["kind"] == "reported_incident"
    feature = {"properties": {"id": "weather-1", "event": "Flood warning"}}
    assert feeds.normalize_alerts(collection(feature, feature))[0]["kind"] == "weather_alert"
    with pytest.raises(ValueError, match="stable ID"):
        feeds.normalize_alerts(collection({"properties": {}}))


@pytest.mark.parametrize("payload", [{}, {"type": "FeatureCollection", "features": {}}, []])
def test_bad_feature_collections(payload):
    with pytest.raises(ValueError):
        feeds.normalize_incidents(payload)


@pytest.mark.parametrize("identity", [None, "", True, []])
def test_invalid_incident_ids(identity):
    with pytest.raises(ValueError):
        feeds.normalize_incidents(collection(incident(identity)))


@pytest.mark.parametrize("coords", [[-181, 0], [0, 91], [np.nan, 0], [True, 0], ["-96", 41], [0], [0, 0, 0]])
def test_invalid_incident_coordinates(coords):
    with pytest.raises(ValueError):
        feeds.normalize_incidents(collection(incident(coords=coords)))


def test_feed_snapshot_failure_preserves_data_and_timestamps(tmp_path):
    def fetch(url):
        return collection({"id": "alert-1", "properties": {"event": "Flood"}}) if "weather.gov" in url else collection(incident())
    result = feeds.refresh_feeds(tmp_path, incident_config=agreement(), fetch=fetch)
    assert not result["nws"]["stale"] and len(result["incidents"]["records"]) == 1
    assert "private" not in (tmp_path / "feeds.json").read_text()
    def fail(url):
        raise OSError("private URL token should never escape")
    failure = feeds.refresh_feeds(tmp_path, incident_config=agreement(), fetch=fail)
    assert failure["nws"]["stale"] and failure["nws"]["records"] == result["nws"]["records"]
    assert failure["nws"]["fetched_at"] == result["nws"]["fetched_at"]
    assert "private" not in (tmp_path / "feeds.json").read_text()
    changed = {**agreement(), "provider": "Another agency"}
    assert feeds.refresh_feeds(tmp_path, incident_config=changed, fetch=fail)["incidents"]["records"] == []


def test_not_configured_and_staleness(tmp_path):
    assert feeds.feed_status(tmp_path)["status"] == "not_refreshed"
    result = feeds.refresh_feeds(tmp_path, fetch=lambda url: collection())
    assert result["incidents"]["status"] == "not_configured"
    result["nws"]["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    write_json(tmp_path / "feeds.json", result)
    assert feeds.feed_status(tmp_path)["nws"]["stale"]
    result["nws"]["fetched_at"] = "broken"
    write_json(tmp_path / "feeds.json", result)
    assert feeds.feed_status(tmp_path)["nws"]["age_seconds"] is None
    with pytest.raises(ValueError):
        feeds.feed_status(tmp_path, 0)


@pytest.mark.parametrize("config", [{}, {**agreement(), "url": "file:///tmp/feed"}, {**agreement(), "url": "https://user:pass@agency.example/feed"}])
def test_unauthorized_feeds_not_fetched(tmp_path, config):
    with pytest.raises(ValueError):
        feeds.refresh_feeds(tmp_path, incident_config=config, fetch=lambda _: pytest.fail("should not fetch"))


def test_invalid_area(tmp_path):
    with pytest.raises(ValueError):
        feeds.refresh_feeds(tmp_path, nws_area="NE&extra=1")


def test_psi_identical_shifted_constant_and_missing():
    reference = list(range(100))
    assert monitoring.population_stability_index(reference, reference) == 0
    assert monitoring.population_stability_index(reference, list(range(100, 200))) > 0.2
    assert monitoring.population_stability_index([2] * 50, [3] * 50) > 0.2
    assert monitoring.population_stability_index(reference, [None] * 100) > 0.2
    for a, b, bins in [([], [1], 10), ([None], [1], 10), ([1], [], 10), ([1], [1], 1)]:
        with pytest.raises(ValueError):
            monitoring.population_stability_index(a, b, bins)


def test_drift_coverage_and_missingness():
    reference = pd.DataFrame({"aadt": np.arange(100) + 1000, "length_miles": np.ones(100)})
    same = monitoring.drift_report(reference, reference)
    assert not same["review_required"] and same["promotion"] == "manual_review_required"
    changed = pd.DataFrame({"aadt": [None] * 10 + [5000] * 10, "length_miles": np.ones(20)})
    report = monitoring.drift_report(reference, changed)
    assert report["review_required"] and report["coverage_ratio"] == 0.2
    assert report["missingness_change"]["aadt"] == 0.5
    empty_reference = pd.DataFrame({"aadt": [None]})
    assert monitoring.drift_report(empty_reference, changed)["psi"]["aadt"] is None
    with pytest.raises(ValueError):
        monitoring.drift_report(reference, changed, ["absent"])
    with pytest.raises(ValueError):
        monitoring.drift_report(pd.DataFrame(), changed)


def test_database_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError):
        database.connect()


@pytest.mark.parametrize("args", [(91, 0), (0, np.nan), (0, 0, 0), (0, 0, 1, 1001)])
def test_database_search_bounds(args):
    with pytest.raises(ValueError):
        database.nearby_segments(*args)


def mock_database(monkeypatch):
    connection, cursor = MagicMock(), MagicMock()
    connection.cursor.return_value = nullcontext(cursor)
    monkeypatch.setattr(database, "connect", lambda url=None: nullcontext(connection))
    return cursor


def test_database_parameterized_query(monkeypatch):
    cursor = mock_database(monkeypatch)
    cursor.fetchall.return_value = [("A", {"aadt": 10}, {"type": "MultiLineString"}, 100)]
    assert database.nearby_segments(41, -96)[0]["distance_m"] == 100
    sql, params = cursor.execute.call_args.args
    assert "ST_DWithin" in sql and params == (-96, 41, -96, 41, 8046.72, 100)


def test_database_snapshot_import(tmp_path, monkeypatch):
    segments = gpd.GeoDataFrame({"segment_id": ["A"], "aadt": [1000]}, geometry=[LineString([(-96, 41), (-96.1, 41.1)])], crs=4326)
    segments.to_parquet(tmp_path / "segments.parquet")
    crashes = pd.DataFrame({"crash_id": ["C", "D"], "year": [2022, 2022], "lat": [41, None], "lng": [-96, None]})
    crashes.to_parquet(tmp_path / "crashes.parquet")
    pd.DataFrame({"segment_id": ["A"], "expected_annual": [0.1]}).to_parquet(tmp_path / "screening.parquet")
    cursor = mock_database(monkeypatch)
    assert database.import_snapshot(tmp_path) == {"segments": 1, "crashes": 2}
    assert cursor.execute.call_count == 6
    assert json.loads(cursor.execute.call_args_list[3].args[1][2])["expected_annual"] == 0.1
    crashes.loc[1, "crash_id"] = "C"
    crashes.to_parquet(tmp_path / "crashes.parquet")
    with pytest.raises(ValueError):
        database.import_snapshot(tmp_path)


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name
        self.generation = bucket.objects.get(name, (0, b""))[0]

    def _check(self, expected):
        if self.bucket.objects.get(self.name, (0, b""))[0] != expected:
            raise RuntimeError("generation conflict")

    def upload_from_string(self, text, content_type=None, if_generation_match=None):
        self._check(if_generation_match)
        self.generation = self.bucket.counter = self.bucket.counter + 1
        self.bucket.objects[self.name] = (self.generation, text.encode() if isinstance(text, str) else text)

    def upload_from_filename(self, filename, if_generation_match=None):
        from pathlib import Path
        self.upload_from_string(Path(filename).read_bytes(), if_generation_match=if_generation_match)

    def download_to_filename(self, filename, if_generation_match=None):
        from pathlib import Path
        self._check(if_generation_match)
        Path(filename).write_bytes(self.bucket.objects[self.name][1])

    def delete(self, if_generation_match=None):
        self._check(if_generation_match)
        del self.bucket.objects[self.name]


class FakeBucket:
    def __init__(self):
        self.objects, self.counter = {}, 0

    def blob(self, name):
        return FakeBlob(self, name)

    def get_blob(self, name):
        return self.blob(name) if name in self.objects else None


def test_cloud_feed_generation_safe_publish():
    from pathlib import Path
    bucket = FakeBucket()
    bucket.blob("safety/feeds.json").upload_from_string('{"old": true}', if_generation_match=0)
    client = MagicMock()
    client.bucket.return_value = bucket
    def runner(command, check):
        root = Path(command[command.index("--root") + 1])
        assert json.loads((root / "feeds.json").read_text()) == {"old": True}
        (root / "feeds.json").write_text('{"new": true}')
    result = cloud_job.run_job("test-bucket", "feeds", client=client, runner=runner)
    assert result["uploaded"] == ["safety/feeds.json"]
    assert json.loads(bucket.objects["safety/feeds.json"][1]) == {"new": True}
    assert "safety/.job-lease.json" not in bucket.objects


def test_cloud_candidate_no_active_model_overwrite():
    from pathlib import Path
    bucket = FakeBucket()
    baseline = seed_cloud_sources(bucket)
    client = MagicMock()
    client.bucket.return_value = bucket
    def runner(command, check):
        assert command[-2:] == ["build", "--candidate"]
        root = Path(command[command.index("--root") + 1]) / "candidates" / "timestamp"
        root.mkdir(parents=True)
        (root / "snapshot.json").write_text('{"candidate": true}')
    result = cloud_job.run_job("test-bucket", "candidate", client=client, runner=runner)
    assert len(result["uploaded"]) == 1
    assert json.loads(bucket.objects["safety/snapshot.json"][1]) == baseline
    assert any(name.endswith("/complete.json") for name in bucket.objects)


def test_cloud_failures_release_only_owned_lease():
    bucket = FakeBucket()
    seed_cloud_sources(bucket)
    client = MagicMock()
    client.bucket.return_value = bucket
    with pytest.raises(RuntimeError, match="no artifacts"):
        cloud_job.run_job("test-bucket", "candidate", client=client, runner=lambda *a, **k: None)
    assert "safety/.job-lease.json" not in bucket.objects
    bucket.blob("safety/.job-lease.json").upload_from_string('{}', if_generation_match=0)
    with pytest.raises(RuntimeError, match="generation conflict"):
        cloud_job.run_job("test-bucket", "feeds", client=client)
    assert "safety/.job-lease.json" in bucket.objects
    for bucket_name, task in [("gs://bucket", "feeds"), ("bucket", "bad")]:
        with pytest.raises(ValueError):
            cloud_job.run_job(bucket_name, task, client=client)


def seed_cloud_sources(bucket):
    import hashlib
    payloads = {"crashes.parquet": b"crash data", "segments.parquet": b"road data",
                "fars-manifest.json": b'[{"year":2023}]', "aadt-manifest.json": b'{"year":2023}'}
    for name, payload in payloads.items():
        bucket.blob("safety/" + name).upload_from_string(payload, if_generation_match=0)
    baseline = {"active": True, "provenance": {
        "crashes_sha256": hashlib.sha256(payloads["crashes.parquet"]).hexdigest(),
        "roads_sha256": hashlib.sha256(payloads["segments.parquet"]).hexdigest(),
        "fars": [{"year": 2023}], "aadt": {"year": 2023}}}
    bucket.blob("safety/snapshot.json").upload_from_string(json.dumps(baseline), if_generation_match=0)
    return baseline


@pytest.mark.parametrize("filename", ["crashes.parquet", "segments.parquet", "fars-manifest.json", "aadt-manifest.json"])
def test_cloud_candidate_rejects_mixed_source_release(filename):
    bucket = FakeBucket()
    seed_cloud_sources(bucket)
    blob = bucket.get_blob("safety/" + filename)
    blob.upload_from_string('{}', if_generation_match=blob.generation)
    client = MagicMock()
    client.bucket.return_value = bucket
    with pytest.raises(ValueError, match="mismatch"):
        cloud_job.run_job("test-bucket", "candidate", client=client,
                          runner=lambda *a, **k: pytest.fail("Must not fit inconsistent inputs"))
    assert "safety/.job-lease.json" not in bucket.objects
    assert not any(name.startswith("safety/candidates/") for name in bucket.objects)

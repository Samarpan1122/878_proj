import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from safety.api import create_app
from safety.io import write_json


@pytest.fixture
def snapshot(tmp_path):
    rows = [{"segment_id": "A", "route": "Test road", "lat": 41., "lng": -96., "observed": 3,
             "expected_annual": .2, "excess_annual": .1, "rate_per_100m_vmt": 4.},
            {"segment_id": "B", "route": "Far road", "lat": 42., "lng": -100., "observed": 0,
             "expected_annual": .05, "excess_annual": -.01, "rate_per_100m_vmt": 0.}]
    write_json(tmp_path / "snapshot.json", {"schema_version": 1, "built_at": "2026-09-29T12:00:00Z",
               "segments": rows, "limitations": ["Test fixture"], "quality": {"matched": 3}})
    return tmp_path


def test_unbuilt_readiness_is_not_health(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/healthz").json()["legacy_models_loaded"] is False
    assert client.get("/readyz").status_code == 503
    assert client.get("/api/safety/status").json()["ready"] is False
    assert client.get("/api/safety/segments").status_code == 503
    assert client.get("/api/report").status_code == 404
    assert client.get("/.env").status_code == 404
    assert client.get("/home.js").status_code == 404


def test_snapshot_queries_exports_and_reloading(snapshot):
    client = TestClient(create_app(snapshot))
    assert client.get("/readyz").status_code == 200
    status = client.get("/api/safety/status").json()
    assert status["ready"] and not status["commercial_ready"] and "segments" not in status
    nearby = client.get("/api/safety/segments?lat=41&lng=-96&radius_km=1").json()
    assert nearby["total"] == 1 and nearby["segments"][0]["segment_id"] == "A"
    assert client.get("/api/safety/segments?limit=1").json()["returned"] == 1
    page = client.get("/api/safety/segments?limit=1&offset=1").json()
    assert page["segments"][0]["segment_id"] == "B" and page["next_offset"] is None
    assert client.get("/api/safety/segments/B").json()["route"] == "Far road"
    assert client.get("/api/safety/segments/nope").status_code == 404
    assert client.get("/api/safety/export?commercial=true").status_code == 409
    export = client.get("/api/safety/export")
    assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
    value = export.json()
    value["built_at"] = "updated"
    write_json(snapshot / "snapshot.json", value)
    assert client.get("/readyz").json()["built_at"] == "updated"
    write_json(snapshot / "snapshot.json", {"schema_version": 999})
    assert client.get("/readyz").status_code == 503


@pytest.mark.parametrize("query", ["lat=91&lng=0", "lat=41", "radius_km=0", "limit=100000", "lat=nan&lng=0", "sort=sql"])
def test_query_bounds(snapshot, query):
    assert TestClient(create_app(snapshot)).get("/api/safety/segments?" + query).status_code == 422


def test_benefits_require_explicit_applicability_and_severity_assumptions(snapshot):
    client = TestClient(create_app(snapshot))
    assert client.get("/api/safety/countermeasures").json()["countermeasures"][0]["id"] == "4737"
    body = {"segment_id": "A", "countermeasure_id": "4737", "implementation_cost": 10000,
            "eligible_fraction": .5, "fatalities_per_crash": 1}
    assert client.post("/api/safety/benefit-cost", json=body).status_code == 422
    body["applicability_confirmed"] = True
    assert client.post("/api/safety/benefit-cost", json=body).status_code == 422
    body["fatal_transfer_assumption_confirmed"] = True
    result = client.post("/api/safety/benefit-cost", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["annual_fatal_crashes_prevented"] == pytest.approx(.2 * .5 * .365)
    assert result.json()["dollar_year"] == 2025
    assert client.post("/api/safety/benefit-cost", json={**body, "eligible_fraction": 1.1}).status_code == 422
    assert client.post("/api/safety/benefit-cost", json={**body, "countermeasure_id": "unknown"}).status_code == 422
    del body["fatalities_per_crash"]
    assert client.post("/api/safety/benefit-cost", json=body).status_code == 422


@pytest.mark.parametrize("value", [[], {"schema_version": 1, "segments": []},
    {"schema_version": 1, "built_at": "today", "segments": [{"segment_id": "bad"}]}])
def test_corrupt_snapshot_fails_closed(tmp_path, value):
    write_json(tmp_path / "snapshot.json", value)
    assert TestClient(create_app(tmp_path)).get("/readyz").status_code == 503


def test_static_allowlist_and_headers(snapshot):
    client = TestClient(create_app(snapshot))
    for path in ["/", "/safety.html", "/safety.css", "/safety.js", "/tokens.css"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/models.html").status_code == 404
    assert client.get("/api/research/advanced").status_code == 404
    assert client.post("/api/research/predict", json={"records": [{}]}).status_code == 404


def test_analysis_requires_matching_source_provenance(snapshot):
    client = TestClient(create_app(snapshot))
    assert client.get("/api/safety/model-evidence").status_code == 503
    active = json.loads((snapshot / "snapshot.json").read_text())
    active["provenance"] = {"crashes_sha256": "crashes-v1", "roads_sha256": "roads-v1"}
    write_json(snapshot / "snapshot.json", active)
    artifact = {"schema_version": 1, "snapshot_inputs": active["provenance"],
                "temporal": {"models": {}}, "spatial": {"models": {}}, "decision": {}}
    write_json(snapshot / "advanced-benchmark.json", artifact)
    assert client.get("/api/safety/model-evidence").status_code == 200
    write_json(snapshot / "advanced-benchmark.json", {**artifact, "snapshot_inputs": {"crashes_sha256": "crashes-v1"}})
    assert client.get("/api/safety/model-evidence").status_code == 503
    write_json(snapshot / "advanced-benchmark.json", artifact)
    active["provenance"]["roads_sha256"] = "roads-v2"
    write_json(snapshot / "snapshot.json", active)
    assert client.get("/api/safety/model-evidence").status_code == 409
    write_json(snapshot / "behavior.json", [])
    assert client.get("/api/safety/behavior").status_code == 503
    write_json(snapshot / "behavior.json", {"schema_version": 1})
    assert client.get("/api/safety/behavior").status_code == 503


def test_local_research_routes_are_opt_in_and_lazy(snapshot, monkeypatch):
    # Exercise routing with a fixture asset; the standalone safety package
    # intentionally does not distribute the noncommercial research interface.
    static = snapshot / "web/static"
    static.mkdir(parents=True)
    (static / "models.html").write_text("<html><body>Research route fixture</body></html>")
    monkeypatch.setattr("safety.api.ROOT", snapshot)
    instances = []
    class FakeEngine:
        national_grid = [[1, 2, 3]]
        def __init__(self): instances.append(self)
        def report(self, *args): return {"research": True}
    fake = SimpleNamespace(Engine=FakeEngine, _env=lambda _: "test", _clean=lambda x: x)
    monkeypatch.setitem(sys.modules, "web.server", fake)
    client = TestClient(create_app(snapshot, research=True))
    assert client.get("/api/safety/status").json()["legacy_explorer_url"] == "/"
    assert not instances
    assert client.get("/api/config").json() == {"googleMapsKey": "test"}
    assert client.get("/api/national").json()["cells"] == [[1, 2, 3]]
    assert client.get("/api/report").json()["research"]
    assert len(instances) == 1
    assert client.get("/healthz").json()["legacy_models_loaded"] is True
    assert client.get("/api/missing").status_code == 404
    assert client.get("/models.html").status_code == 200


def test_research_prediction_request_is_bounded_and_opt_in(snapshot, monkeypatch):
    fake = SimpleNamespace(predict_incidents=lambda records: {"research_only": True, "predictions": records})
    monkeypatch.setitem(sys.modules, "src.advanced_inference", fake)
    client = TestClient(create_app(snapshot, research=True))
    body = {"records": [{"Start_Time": "2023-01-01 12:00:00", "Start_Lat": 41., "Start_Lng": -96.}]}
    assert client.post("/api/research/predict", json=body).json()["research_only"]
    assert client.post("/api/research/predict", json={"records": []}).status_code == 422
    assert client.post("/api/research/predict", json={"records": [{}] * 33}).status_code == 422
    assert client.post("/api/research/predict", json={"records": [{"Source": "s" * 257}]}).status_code == 422
    def missing(_):
        raise FileNotFoundError()
    fake.predict_incidents = missing
    assert client.post("/api/research/predict", json=body).status_code == 503
    def invalid(_):
        raise ValueError("Invalid incident context")
    fake.predict_incidents = invalid
    assert client.post("/api/research/predict", json=body).status_code == 422


def test_metro_reports_are_research_only_and_handle_partial_artifacts(snapshot, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(snapshot, research=True))
    assert client.get("/api/research/metro").status_code == 503
    folder = tmp_path / "outputs/research/metro"
    write_json(folder / "online.json", {"schema_version": 1, "status": "complete"})
    result = client.get("/api/research/metro").json()
    assert result["research_only"] and result["online"]["status"] == "complete"
    assert result["fixed"] is None
    write_json(folder / "data_audit.json", [])
    assert client.get("/api/research/metro").status_code == 503
    (folder / "data_audit.json").write_text('{"score": 1e999}')
    assert client.get("/api/research/metro").status_code == 503
    assert TestClient(create_app(snapshot)).get("/api/research/metro").status_code == 404


def test_cloud_readiness_alias_and_empty_snapshot(snapshot):
    client = TestClient(create_app(snapshot))
    assert client.get('/ready').json()['segments'] == 2
    value = json.loads((snapshot / 'snapshot.json').read_text())
    value['segments'] = []
    write_json(snapshot / 'snapshot.json', value)
    assert client.get('/ready').status_code == 503
    assert client.get('/health').status_code == 200


@pytest.mark.parametrize('location', ['metadata', 'segment'])
def test_overflow_in_untyped_snapshot_fields_fails_closed(snapshot, location):
    value = json.loads((snapshot / 'snapshot.json').read_text())
    target = value if location == 'metadata' else value['segments'][0]
    target['extra'] = {'nested': [float('inf')]}
    (snapshot / 'snapshot.json').write_text(json.dumps(value).replace('Infinity', '1e999'))
    assert TestClient(create_app(snapshot)).get('/ready').status_code == 503


def test_optional_broken_feed_does_not_disable_screening(snapshot):
    (snapshot / 'feeds.json').write_text('{"nws": []}')
    client = TestClient(create_app(snapshot))
    response = client.get('/api/safety/status')
    assert response.status_code == 200
    assert response.json()['feeds']['status'] == 'invalid'
    assert response.json()['ready'] is True
    assert client.get('/api/safety/segments').status_code == 200


def test_readiness_assessment_avoids_full_hashing_on_requests(snapshot, monkeypatch):
    calls = []
    def assess(root, verify_files=True):
        calls.append((root, verify_files))
        return {'commercial_ready': False, 'technical_ready': True}
    monkeypatch.setitem(sys.modules, 'safety.release', SimpleNamespace(assess_readiness=assess))
    result = TestClient(create_app(snapshot)).get('/api/safety/readiness')
    assert result.status_code == 200 and result.json()['commercial_ready'] is False
    assert calls == [(snapshot, False)]


def test_synthetic_sources_remain_labeled(snapshot):
    value = json.loads((snapshot / 'snapshot.json').read_text())
    value.update(data_mode='synthetic', sources=[{'id': 'synthetic', 'name': 'Synthetic fixture'}])
    write_json(snapshot / 'snapshot.json', value)
    client = TestClient(create_app(snapshot))
    status = client.get('/api/safety/status').json()
    assert status['sources'] == value['sources']
    assert status['data_mode'] == 'synthetic' and status['commercial_ready'] is False
    assert client.get('/api/safety/segments').json()['data_mode'] == 'synthetic'


@pytest.mark.parametrize('field,value', [('lat', '41.0'), ('observed', True)])
def test_snapshot_does_not_accept_coercible_raw_values(snapshot, field, value):
    data = json.loads((snapshot / 'snapshot.json').read_text())
    data['segments'][0][field] = value
    write_json(snapshot / 'snapshot.json', data)
    assert TestClient(create_app(snapshot)).get('/ready').status_code == 503


def test_analysis_rejects_overflow_in_nested_metrics(snapshot):
    data = json.loads((snapshot / 'snapshot.json').read_text())
    data['provenance'] = {'crashes_sha256': 'c', 'roads_sha256': 'r'}
    write_json(snapshot / 'snapshot.json', data)
    (snapshot / 'advanced-benchmark.json').write_text('{"schema_version":1,"snapshot_inputs":{"crashes_sha256":"c","roads_sha256":"r"},"temporal":{"models":{"metric":1e999}},"spatial":{"models":{}},"decision":{}}')
    assert TestClient(create_app(snapshot)).get('/api/safety/model-evidence').status_code == 503


def test_synthetic_scenario_and_export_preserve_context(snapshot):
    value = json.loads((snapshot / 'snapshot.json').read_text())
    value['data_mode'] = 'synthetic'
    write_json(snapshot / 'snapshot.json', value)
    client = TestClient(create_app(snapshot))
    body = {'segment_id': 'A', 'countermeasure_id': '4737', 'implementation_cost': 10000,
            'fatalities_per_crash': 1, 'eligible_fraction': .5,
            'applicability_confirmed': True, 'fatal_transfer_assumption_confirmed': True}
    response = client.post('/api/safety/benefit-cost', json=body)
    assert response.status_code == 200
    data = response.json()
    assert data['data_mode'] == 'synthetic' and data['segment_id'] == 'A'
    assert data['limitations'][0].startswith('Synthetic workflow')
    assert 'SYNTHETIC-demo' in client.get('/api/safety/export').headers['content-disposition']

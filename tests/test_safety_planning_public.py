"""Public deployment integration: route exposure, validation and optional geometry."""
import gzip
import io
import json

import pytest
from fastapi.testclient import TestClient

from safety.public_api import create_app
from test_safety_public_data import public_artifact


@pytest.fixture
def public_planning(tmp_path, public_artifact):
    public = tmp_path / 'public'
    public.mkdir()
    (public / 'snapshot.json').write_text(json.dumps(public_artifact))
    screening = tmp_path / 'screening'
    screening.mkdir()
    snapshot = {'schema_version': 1, 'built_at': '2026-09-30T00:00:00Z',
                'data_mode': 'synthetic', 'commercial_ready': False,
                'provenance': {'roads_sha256': 'test-road-source'},
                'segments': [{'segment_id': 'A', 'lat': 41., 'lng': -96., 'observed': 3,
                              'expected_annual': .2, 'excess_annual': .1, 'rate_per_100m_vmt': 4.,
                              'length_miles': 1.} ]}
    (screening / 'snapshot.json').write_text(json.dumps(snapshot))
    return TestClient(create_app(public, screening_root=screening)), screening


def candidate():
    return {'candidate_id': 'road-edge', 'segment_id': 'A', 'countermeasure_id': '4737',
            'implementation_cost': 10000, 'fatalities_per_crash': 1., 'eligible_fraction': .5,
            'applicability_confirmed': True, 'fatal_transfer_assumption_confirmed': True}


def requests():
    return {
        'portfolio': {'budget': 10000, 'candidates': [candidate()]},
        'workflow': {'annual_cases': 100, 'before_hours_per_case': 4., 'after_hours_per_case': 1.,
                     'hourly_cost': 50., 'annual_software_cost': 10000},
        'outcomes': {'before': {'crashes': 10, 'exposure_vmt': 1e8},
                     'after': {'crashes': 5, 'exposure_vmt': 1e8}, 'source_note': 'Synthetic integration fixture'},
        'evidence': {'project_name': 'Test project', 'agency_name': 'Test only',
                     'project_description': 'No agency endorsement', 'segment_ids': ['A']},
    }


def provider_request():
    return {'origin': {'lat': 41., 'lng': -96.}, 'destination': {'lat': 41.01, 'lng': -96.},
            'weights': {'time': 1., 'risk': 1., 'residential': 0.}}


def stub_provider(monkeypatch):
    monkeypatch.setenv('SAFETY_ROUTING_OSRM_URL', 'https://operator-routing.example.test')
    data = {'code': 'Ok', 'routes': [{'distance': 1110., 'duration': 120.,
             'geometry': {'type': 'LineString', 'coordinates': [[-96., 41.], [-96., 41.01]]}}]}
    monkeypatch.setattr('safety.routing.urlopen', lambda *a, **kw: io.BytesIO(json.dumps(data).encode()))


def write_bad_geometry(screening, kind):
    path = screening / 'road-geometry.json.gz'
    if kind == 'truncated_gzip':
        path.write_bytes(gzip.compress(b'{"hello":"world"}')[:-10])
    elif kind == 'wrong_json_type':
        path.write_bytes(gzip.compress(b'[]'))
    else:
        value = {'schema_version': 1, 'metric_crs': 'EPSG:26914', 'roads_sha256': 'test-road-source',
                 'simplification_tolerance_m': .5, 'roads': [{'segment_id': 'A', 'wkb': 'invalid'}]}
        path.write_bytes(gzip.compress(json.dumps(value).encode()))


def test_public_and_mounted_planning_endpoints_exist(public_planning):
    client, _ = public_planning
    for endpoint, body in requests().items():
        for prefix in ['/api/safety/planning/', '/screening/api/safety/planning/']:
            response = client.post(prefix + endpoint, json=body)
            assert response.status_code == 200, (endpoint, prefix, response.text)
            assert response.headers['cache-control'] == 'no-store'
    paths = client.get('/openapi.json').json()['paths']
    for endpoint in requests():
        assert '/api/safety/planning/' + endpoint in paths


@pytest.mark.parametrize('nonfinite', ['NaN', 'Infinity', '-Infinity', '1e999'])
def test_public_planning_nonfinite_inputs_are_422(public_planning, nonfinite):
    client, _ = public_planning
    body = json.dumps(requests()['portfolio']).replace('10000', nonfinite, 1)
    response = client.post('/api/safety/planning/portfolio', content=body, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert response.json()['detail']


@pytest.mark.parametrize('path,body', [
    ('/api/safety/linkage/match', '{"records":[{"case_id":"x","lat":NaN,"lng":-96}]}'),
    ('/api/safety/routing/routes', '{"origin":{"lat":1e999,"lng":-96},"destination":{"lat":41,"lng":-96}}'),
    ('/api/safety/routing/compare', '{"candidates":[{"route_id":"x","source":"test","edges":[{"edge_id":"x","length_miles":Infinity,"baseline_minutes":1}]}]}'),
])
def test_other_public_planning_inputs_fail_with_422(public_planning, path, body):
    client, _ = public_planning
    response = client.post(path, content=body, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422


def test_missing_geometry_and_provider_fail_cleanly(public_planning, monkeypatch):
    client, _ = public_planning
    monkeypatch.delenv('SAFETY_ROUTING_OSRM_URL', raising=False)
    assert client.post('/api/safety/routing/routes', json=provider_request()).status_code == 503
    assert client.post('/api/safety/linkage/match', json={'records': [{'case_id': 'x', 'lat': 41., 'lng': -96.}]}).status_code == 503
    stub_provider(monkeypatch)
    response = client.post('/api/safety/routing/routes', json=provider_request())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['routes'][0]['risk_linkage_status'] == 'unavailable'
    assert data['routes'][0]['historical_risk_index'] is None
    assert data['preferred_candidate_id'] is None
    assert data['time_basis'] == 'provider_baseline_non_live'


@pytest.mark.parametrize('kind', ['wrong_json_type', 'invalid_wkb', 'truncated_gzip'])
def test_corrupt_geometry_is_503_for_matching_and_nonfatal_for_routes(public_planning, monkeypatch, kind):
    client, screening = public_planning
    write_bad_geometry(screening, kind)
    stub_provider(monkeypatch)
    response = client.post('/api/safety/linkage/match', json={'records': [{'case_id': 'x', 'lat': 41., 'lng': -96.} ]})
    assert response.status_code == 503, response.text
    response = client.post('/api/safety/routing/routes', json=provider_request())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['routes'][0]['risk_linkage_status'] == 'unavailable'
    assert data['preferred_candidate_id'] is None


def test_disabled_screening_does_not_expose_planning(tmp_path, public_artifact):
    (tmp_path / 'snapshot.json').write_text(json.dumps(public_artifact))
    client = TestClient(create_app(tmp_path, enable_screening=False))
    assert client.post('/api/safety/planning/workflow', json=requests()['workflow']).status_code == 404


def test_public_body_limit_applies_to_planning_requests(public_planning):
    client, _ = public_planning
    body = requests()['evidence']
    body['project_description'] = 'x' * 17000
    assert client.post('/api/safety/planning/evidence', json=body).status_code == 413

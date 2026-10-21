from datetime import datetime, timezone
import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from safety.routing import CompareRequest, GenerateRequest, compare_routes, provider_routes, register_routing_routes

NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
SNAPSHOT = {"built_at": "2026-09-29", "segments": [
    {"segment_id": "A", "expected_annual": 100, "eb_fatal_crashes_per_100m_vmt": 1., "length_miles": 10},
    {"segment_id": "B", "expected_annual": .1, "eb_fatal_crashes_per_100m_vmt": 5., "length_miles": 10}]}


def edge(segment="A", **kwargs):
    return {"edge_id": segment, "segment_id": segment, "length_miles": 2., "baseline_minutes": 3.,
            "residential": False, "allowed_vehicle_types": ["car"], **kwargs}


def candidate(name="one", edges=None):
    return {"route_id": name, "source": "Unit test road paths", "edges": edges or [edge()]}


def evaluate(candidates=None, **kwargs):
    return compare_routes(CompareRequest(candidates=candidates or [candidate()], **kwargs), SNAPSHOT, now=NOW)


def test_risk_uses_exposure_normalized_rate_not_annual_count():
    result = evaluate([candidate("lower", [edge()]), candidate("higher", [edge("B")])],
                      weights={"time": 0, "risk": 1, "residential": 0})
    assert result["preferred_candidate_id"] == "lower"
    assert result["candidates"][0]["historical_risk_index"] == 2.
    assert "not a probability" in result["risk_index_units"]


def test_risk_scales_by_traversed_miles():
    result = evaluate([candidate("short", [edge(length_miles=1)]), candidate("long", [edge(length_miles=3)])])
    assert [r["historical_risk_index"] for r in result["candidates"]] == [1., 3.]


def test_missing_risk_never_becomes_zero_or_wins():
    result = evaluate([candidate("unknown", [edge("missing", baseline_minutes=1)]), candidate("known")])
    unknown = result["candidates"][0]
    assert unknown["historical_risk_index"] is None
    assert unknown["risk_coverage_fraction"] == 0
    assert not unknown["rankable"]
    assert result["preferred_candidate_id"] == "known"
    time_only = evaluate([candidate("unknown", [edge("missing")])], weights={"time": 1, "risk": 0, "residential": 0})
    assert time_only["preferred_candidate_id"] == "unknown"


def test_partial_coverage_not_extrapolated():
    result = evaluate([candidate(edges=[edge(), edge("missing")])])["candidates"][0]
    assert result["risk_coverage_fraction"] == .5
    assert result["historical_risk_index"] is None
    assert result["covered_historical_risk_index"] == 2.


@pytest.mark.parametrize("stamp,status,minutes", [
    ("2026-09-30T11:55:00Z", "fresh_caller_supplied", 7),
    ("2026-09-30T10:00:00Z", "stale_ignored", 3),
    ("2026-09-30T12:01:00Z", "future_timestamp_rejected", 3)])
def test_traffic_freshness(stamp, status, minutes):
    route = evaluate([candidate(edges=[edge(traffic={"observed_at": stamp, "source": "Agency", "travel_minutes": 7})])])["candidates"][0]
    assert route["travel_minutes"] == minutes
    assert route["edges"][0]["traffic_status"] == status


@pytest.mark.parametrize("kwargs", [{"allowed_vehicle_types": ["truck"]}, {"allowed_vehicle_types": None},
                                    {"max_height_m": 1.5}, {"max_weight_tonnes": 1}])
def test_restrictions_fail_closed(kwargs):
    route = evaluate([candidate(edges=[edge(**kwargs)])], vehicle={"type": "car", "height_m": 2, "weight_tonnes": 2})["candidates"][0]
    assert not route["eligible"] and not route["rankable"]


def test_personal_preferences_change_choice():
    candidates = [candidate("fast", [edge("B", baseline_minutes=1)]), candidate("lower_proxy", [edge(baseline_minutes=5)])]
    assert evaluate(candidates, weights={"time": 2, "risk": 1, "residential": 0})["preferred_candidate_id"] == "fast"
    assert evaluate(candidates, weights={"time": 1, "risk": 2, "residential": 0})["preferred_candidate_id"] == "lower_proxy"


def test_residential_exposure_and_unknown_classification():
    result = evaluate([candidate("residential", [edge(residential=True)]), candidate("arterial", [edge()]),
                       candidate("unknown", [edge(residential=None)])], weights={"time": 0, "risk": 0, "residential": 1})
    assert result["preferred_candidate_id"] == "arterial"
    assert not result["candidates"][2]["rankable"]


def test_congestion_scenario_separate_from_actual_eta():
    row = evaluate([candidate(edges=[edge(capacity_vph=1000, baseline_flow_vph=500, additional_flow_vph=500)])])["candidates"][0]
    assert row["travel_minutes"] == 3
    assert row["time_basis"] == "baseline_non_live"
    assert row["congestion_scenario_minutes"] == pytest.approx(3 * 1.15)
    assert row["congestion_scenario_baseline_minutes"] == pytest.approx(3 * (1 + .15 * .5**4))


@pytest.mark.parametrize("changes", [{"length_miles": float("nan")}, {"capacity_vph": 100},
                                      {"traffic": {"travel_minutes": 1, "observed_at": "2026-09-30T12:00:00", "source": "x"}}])
def test_invalid_inputs(changes):
    with pytest.raises(ValidationError):
        CompareRequest(candidates=[candidate(edges=[edge(**changes)])])


def test_generation_disabled_and_vehicle_profiles(monkeypatch, tmp_path):
    monkeypatch.delenv("SAFETY_ROUTING_OSRM_URL", raising=False)
    app = FastAPI()
    register_routing_routes(app, lambda: SNAPSHOT, tmp_path)
    client = TestClient(app)
    assert client.get("/api/safety/routing/status").json()["live_traffic_available"] is False
    request = {"origin": {"lat": 41, "lng": -96}, "destination": {"lat": 41.1, "lng": -96}}
    assert client.post("/api/safety/routing/routes", json=request).status_code == 503
    assert client.post("/api/safety/routing/routes", json={**request, "vehicle": {"type": "truck"}}).status_code == 422
    assert client.post("/api/safety/routing/routes", json={**request, "url": "https://bad.test"}).status_code == 422


def test_provider_real_geometry_baseline_and_rate_limit(monkeypatch, tmp_path):
    requests = []
    def open_stub(url, timeout):
        requests.append(url)
        return io.BytesIO(json.dumps({"code": "Ok", "routes": [{"distance": 1609.344, "duration": 120,
             "geometry": {"type": "LineString", "coordinates": [[-96, 41], [-96, 41.1]]}}]}).encode())
    monkeypatch.setattr("safety.routing.urlopen", open_stub)
    monkeypatch.setenv("SAFETY_ROUTING_OSRM_URL", "https://routing.example.test")
    app = FastAPI()
    register_routing_routes(app, lambda: SNAPSHOT, tmp_path)
    client = TestClient(app)
    request = {"origin": {"lat": 41, "lng": -96}, "destination": {"lat": 41.1, "lng": -96}}
    for _ in range(6):
        response = client.post("/api/safety/routing/routes", json=request)
        assert response.status_code == 200
    data = response.json()
    assert data["time_basis"] == "provider_baseline_non_live"
    assert data["routes"][0]["distance_miles"] == 1
    assert data["routes"][0]["historical_risk_index"] is None
    assert client.post("/api/safety/routing/routes", json=request).status_code == 429
    assert len(requests) == 6


@pytest.mark.parametrize("coverage,expected_index", [(1., 2.), (.5, None)])
def test_generated_route_partial_risk_and_full_risk_ranking(monkeypatch, tmp_path, coverage, expected_index):
    monkeypatch.setenv("SAFETY_ROUTING_OSRM_URL", "https://routing.example.test")
    monkeypatch.setattr("safety.routing.provider_routes", lambda *args: {
        "routes": [{"route_id": "one", "baseline_minutes": 3., "distance_miles": 2.,
                    "geometry": {"coordinates": [[-96,41],[-96,41.01]]}, "risk_coverage_fraction": 0,
                    "historical_risk_index": None}], "limitations": []})
    monkeypatch.setattr("safety.road_geometry.match_route", lambda *args: {
        "matched_legs": [{"segment_id": "A", "length_miles": 2. * coverage}],
        "total_length_miles": 2., "coverage_fraction": coverage})
    app = FastAPI()
    register_routing_routes(app, lambda: SNAPSHOT, tmp_path)
    result = TestClient(app).post("/api/safety/routing/routes", json={
        "origin": {"lat": 41, "lng": -96}, "destination": {"lat": 41.01, "lng": -96},
        "weights": {"time": 0, "risk": 1, "residential": 0}}).json()
    assert result["routes"][0]["historical_risk_index"] == expected_index
    assert result["preferred_candidate_id"] == ("one" if coverage == 1 else None)


@pytest.mark.parametrize("value", [[], {"code": "Ok", "routes": [None]},
    {"code": "Ok", "routes": [{"distance": 10, "duration": 5, "geometry": {"coordinates": [[True,1],[1,1]]}}]}])
def test_malformed_provider_response_fails_cleanly(monkeypatch, value):
    from fastapi import HTTPException
    monkeypatch.setattr("safety.routing.urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(value).encode()))
    request = GenerateRequest(origin={"lat": 41, "lng": -96}, destination={"lat": 41.1, "lng": -96})
    with pytest.raises(HTTPException) as error:
        provider_routes(request, "https://routing.example.test")
    assert error.value.status_code == 502


@pytest.mark.parametrize("stale", [False, True])
def test_provider_integration_uses_real_source_bound_geometry(monkeypatch, tmp_path, stale):
    import gzip
    from shapely.geometry import LineString
    from shapely.ops import transform
    from shapely import to_wkb
    from safety.road_geometry import _PROJECT
    snapshot = {**SNAPSHOT, "provenance": {"roads_sha256": "correct"}}
    roads = [{"segment_id": name, "wkb": to_wkb(transform(_PROJECT, LineString(coords)), hex=True)}
             for name, coords in [("A", [(-96,41),(-96,41.01)]), ("B", [(-96.1,41),(-96.1,41.01)])]]
    with gzip.open(tmp_path / "road-geometry.json.gz", "wt") as stream:
        json.dump({"schema_version": 1, "metric_crs": "EPSG:26914", "simplification_tolerance_m": .5,
                   "roads_sha256": "stale" if stale else "correct", "roads": roads}, stream)
    monkeypatch.setenv("SAFETY_ROUTING_OSRM_URL", "https://routing.example.test")
    monkeypatch.setattr("safety.routing.provider_routes", lambda *args: {
        "routes": [{"route_id": "one", "baseline_minutes": 3., "distance_miles": .7,
                    "geometry": {"type": "LineString", "coordinates": [[-96,41],[-96,41.01]]},
                    "risk_coverage_fraction": 0, "historical_risk_index": None}], "limitations": []})
    app = FastAPI()
    register_routing_routes(app, lambda: snapshot, tmp_path)
    result = TestClient(app).post("/api/safety/routing/routes", json={
        "origin": {"lat": 41, "lng": -96}, "destination": {"lat": 41.01, "lng": -96},
        "weights": {"time": 0, "risk": 1, "residential": 0}}).json()
    route = result["routes"][0]
    if stale:
        assert route["historical_risk_index"] is None
        assert result["preferred_candidate_id"] is None
    else:
        assert route["risk_coverage_fraction"] == pytest.approx(1)
        assert route["historical_risk_index"] > 0
        assert result["preferred_candidate_id"] == "one"


@pytest.mark.parametrize("changes", [{"baseline_minutes": True}, {"length_miles": False}, {"residential": "false"}])
def test_strict_input_types(changes):
    with pytest.raises(ValidationError):
        CompareRequest(candidates=[candidate(edges=[edge(**changes)])])


def test_private_provider_identity_token_audience_and_no_redirect(monkeypatch):
    from safety.routing import _open_provider, _NoRedirect
    calls = []
    class Opener:
        def open(self, request, timeout):
            assert request.get_header('Authorization') == 'Bearer test-identity-token'
            assert timeout == 8
            calls.append(request.full_url)
            return io.BytesIO(b'{}')
    monkeypatch.setenv('SAFETY_ROUTING_AUTH_AUDIENCE', 'https://routing.example.test')
    monkeypatch.setattr('google.oauth2.id_token.fetch_id_token', lambda transport, audience:
                        'test-identity-token' if audience == 'https://routing.example.test' else None)
    monkeypatch.setattr('safety.routing.build_opener', lambda handler: Opener())
    _open_provider('https://routing.example.test/route/v1/driving/1,2;3,4', 'https://routing.example.test')
    assert len(calls) == 1
    assert _NoRedirect().redirect_request(None,None,302,'Found',{},'https://elsewhere.test') is None


def test_private_provider_rejects_wrong_audience_before_token_fetch(monkeypatch):
    from safety.routing import _open_provider
    from fastapi import HTTPException
    monkeypatch.setenv('SAFETY_ROUTING_AUTH_AUDIENCE', 'https://another.example.test')
    with pytest.raises(HTTPException) as error:
        _open_provider('https://routing.example.test/route', 'https://routing.example.test')
    assert error.value.status_code == 503


def test_generation_rejects_outside_nebraska_scope():
    with pytest.raises(ValidationError):
        GenerateRequest(origin={'lat': 37.77, 'lng': -122.42}, destination={'lat': 41.1, 'lng': -96})

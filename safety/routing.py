"""Planning route comparisons; historical exposure proxies are not trip probabilities."""
from datetime import datetime, timezone
import json
import math
import os
import threading
import time
from collections import deque
from urllib.parse import urlparse
from urllib.request import urlopen, Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


VehicleType = Literal["car", "truck", "bus", "bicycle", "pedestrian"]


class Vehicle(StrictModel):
    type: VehicleType = "car"
    height_m: float | None = Field(default=None, gt=0, le=10)
    weight_tonnes: float | None = Field(default=None, gt=0, le=200)


class Weights(StrictModel):
    time: float = Field(default=1, ge=0, le=100)
    risk: float = Field(default=1, ge=0, le=100)
    residential: float = Field(default=.5, ge=0, le=100)

    @model_validator(mode="after")
    def nonzero(self):
        if not self.time + self.risk + self.residential:
            raise ValueError("At least one comparison weight must be positive")
        return self


class Traffic(StrictModel):
    travel_minutes: float = Field(gt=0, le=1440)
    observed_at: datetime = Field(strict=False)
    source: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def timezone_required(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("Traffic timestamp must include a timezone")
        return self


class Edge(StrictModel):
    edge_id: str = Field(min_length=1, max_length=100)
    segment_id: str | None = Field(default=None, min_length=1, max_length=100)
    length_miles: float = Field(gt=0, le=500)
    baseline_minutes: float = Field(gt=0, le=1440)
    residential: bool | None = None
    allowed_vehicle_types: list[VehicleType] | None = Field(default=None, max_length=5)
    max_height_m: float | None = Field(default=None, gt=0, le=10)
    max_weight_tonnes: float | None = Field(default=None, gt=0, le=200)
    traffic: Traffic | None = None
    capacity_vph: float | None = Field(default=None, gt=0, le=100000)
    baseline_flow_vph: float | None = Field(default=None, ge=0, le=100000)
    additional_flow_vph: float | None = Field(default=None, ge=0, le=100000)

    @model_validator(mode="after")
    def capacity_scenario(self):
        fields = [self.capacity_vph, self.baseline_flow_vph, self.additional_flow_vph]
        if any(x is not None for x in fields) and not all(x is not None for x in fields):
            raise ValueError("Capacity scenarios require capacity, baseline flow and additional flow")
        if self.capacity_vph is not None and (self.baseline_flow_vph + self.additional_flow_vph) / self.capacity_vph > 5:
            raise ValueError("Volume/capacity above 5 is outside this illustrative model")
        return self


class Candidate(StrictModel):
    route_id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=250)
    edges: list[Edge] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def no_repeated_edges(self):
        if len({e.edge_id for e in self.edges}) != len(self.edges):
            raise ValueError("Repeated edge IDs are not supported")
        return self


class CompareRequest(StrictModel):
    candidates: list[Candidate] = Field(min_length=1, max_length=8)
    vehicle: Vehicle = Field(default_factory=Vehicle)
    weights: Weights = Field(default_factory=Weights)
    max_traffic_age_minutes: int = Field(default=15, ge=1, le=120)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({r.route_id for r in self.candidates}) != len(self.candidates):
            raise ValueError("Route IDs must be unique")
        return self


LIMITATIONS = [
    "Planning comparison only; not navigation instructions or a certified safest route.",
    "Caller-supplied path connectivity, restrictions, traffic observations and road linkage are not independently verified.",
    "Historical fatal-crash rates do not describe current conditions, all crashes, or calibrated per-trip probabilities.",
    "Traffic exposure may use historical-vintage proxies; missing risk coverage is never treated as zero risk.",
    "Weights express user preferences, not an objectively optimal or network-wide traffic assignment.",
    "Congestion scenarios use an illustrative BPR curve (alpha=.15, beta=4); capacity/flow inputs are assumptions, not measured effects.",
]


def _rate(row):
    if not row:
        return None, None
    for field in ("eb_fatal_crashes_per_100m_vmt", "rate_per_100m_vmt"):
        value = row.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            return value, field
    return None, None


def compare_routes(request: CompareRequest, snapshot, now=None):
    now = now or datetime.now(timezone.utc)
    segments = {r["segment_id"]: r for r in snapshot["segments"]}
    results = []
    for candidate in request.candidates:
        distance = covered = risk = residential = residential_known = fresh_distance = travel = 0.
        scenario_minutes = scenario_baseline = scenario_distance = 0.
        reasons, fields, edge_details = [], set(), []
        eligible = True
        for edge in candidate.edges:
            distance += edge.length_miles
            if edge.allowed_vehicle_types is None:
                reasons.append(f"{edge.edge_id}: vehicle access unknown")
                eligible = False
            elif request.vehicle.type not in edge.allowed_vehicle_types:
                reasons.append(f"{edge.edge_id}: vehicle type prohibited")
                eligible = False
            for limit_name, vehicle_name in (("max_height_m", "height_m"), ("max_weight_tonnes", "weight_tonnes")):
                limit, value = getattr(edge, limit_name), getattr(request.vehicle, vehicle_name)
                if limit is not None and (value is None or value > limit):
                    reasons.append(f"{edge.edge_id}: {vehicle_name} missing or exceeds restriction")
                    eligible = False
            row = segments.get(edge.segment_id)
            rate, field = _rate(row)
            if row and row.get("length_miles") and edge.length_miles > row["length_miles"] * 1.01:
                rate, field = None, None
                reasons.append(f"{edge.edge_id}: traversal exceeds matched segment length")
            if rate is not None:
                covered += edge.length_miles
                risk += rate * edge.length_miles
                fields.add(field)
            if edge.residential is not None:
                residential_known += edge.length_miles
                residential += edge.length_miles if edge.residential else 0
            age = (now - edge.traffic.observed_at).total_seconds() / 60 if edge.traffic else None
            fresh = age is not None and 0 <= age <= request.max_traffic_age_minutes
            travel += edge.traffic.travel_minutes if fresh else edge.baseline_minutes
            fresh_distance += edge.length_miles if fresh else 0
            if edge.capacity_vph is not None:
                def bpr(v):
                    return edge.baseline_minutes * (1 + .15 * (v / edge.capacity_vph) ** 4)
                scenario_baseline += bpr(edge.baseline_flow_vph)
                scenario_minutes += bpr(edge.baseline_flow_vph + edge.additional_flow_vph)
                scenario_distance += edge.length_miles
            edge_details.append({"edge_id": edge.edge_id, "segment_id": edge.segment_id,
                "risk_rate_field": field, "traffic_status": "fresh_caller_supplied" if fresh else
                "unavailable" if age is None else "future_timestamp_rejected" if age < 0 else "stale_ignored",
                "traffic_age_minutes": age, "traffic_source": edge.traffic.source if edge.traffic else None})
        full_risk, full_residential = math.isclose(covered, distance), math.isclose(residential_known, distance)
        rankable = eligible and (full_risk or not request.weights.risk) and (full_residential or not request.weights.residential)
        if request.weights.risk and not full_risk:
            reasons.append("Incomplete risk coverage: excluded from risk-weighted ranking")
        if request.weights.residential and not full_residential:
            reasons.append("Incomplete residential classification: excluded from residential-weighted ranking")
        results.append({"route_id": candidate.route_id, "source": candidate.source,
            "eligible": eligible, "rankable": rankable, "reasons": reasons,
            "distance_miles": distance, "travel_minutes": travel,
            "time_basis": "fresh_caller_supplied_traffic" if math.isclose(fresh_distance, distance) else
                "mixed_baseline_and_caller_traffic" if fresh_distance else "baseline_non_live",
            "risk_coverage_fraction": covered / distance, "historical_risk_index": risk if full_risk else None,
            "covered_historical_risk_index": risk, "risk_rate_fields": sorted(fields),
            "residential_miles": residential if full_residential else None,
            "residential_coverage_fraction": residential_known / distance,
            "traffic_coverage_fraction": fresh_distance / distance,
            "congestion_scenario_minutes": scenario_minutes if math.isclose(scenario_distance, distance) else None,
            "congestion_scenario_baseline_minutes": scenario_baseline if math.isclose(scenario_distance, distance) else None,
            "congestion_scenario_coverage_fraction": scenario_distance / distance,
            "score": None, "rank": None, "edges": edge_details})
    ranked = [r for r in results if r["rankable"]]
    for row in ranked:
        row["score"] = 0.
    for field, weight in [("travel_minutes", request.weights.time), ("historical_risk_index", request.weights.risk),
                          ("residential_miles", request.weights.residential)]:
        if not weight or not ranked:
            continue
        low, high = min(r[field] for r in ranked), max(r[field] for r in ranked)
        for row in ranked:
            row["score"] += weight * ((row[field] - low) / (high - low) if high > low else 0)
    ranked.sort(key=lambda r: (r["score"], r["travel_minutes"], r["route_id"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    return {"mode": "candidate_path_planning", "evaluated_at": now.isoformat(),
        "snapshot_built_at": snapshot.get("built_at"), "vehicle": request.vehicle.model_dump(),
        "weights": request.weights.model_dump(), "candidates": results,
        "preferred_candidate_id": ranked[0]["route_id"] if ranked else None,
        "score_method": "Weighted min-max among rankable candidates; lower preferred. Scores change with candidate set.",
        "risk_index_units": "Historical fatal-crash rate per 100 million VMT multiplied by traversed miles; not a probability.",
        "limitations": LIMITATIONS + snapshot.get("limitations", [])}


class Location(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class GenerateRequest(StrictModel):
    origin: Location
    destination: Location
    alternatives: bool = True
    weights: Weights = Field(default_factory=lambda: Weights(time=1, risk=0, residential=0))
    vehicle: Vehicle = Field(default_factory=Vehicle)

    @model_validator(mode="after")
    def supported_profile(self):
        if any(not -104.1 <= p.lng <= -95.2 or not 39.9 <= p.lat <= 43.1 for p in (self.origin, self.destination)):
            raise ValueError("Route planning is limited to Nebraska and its immediate boundary")
        if self.vehicle.type != "car" or self.vehicle.height_m is not None or self.vehicle.weight_tonnes is not None:
            raise ValueError("Provider route generation supports unrestricted car planning only; use supplied candidates for vehicle constraints")
        return self


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_provider(url, base_url):
    audience = os.getenv("SAFETY_ROUTING_AUTH_AUDIENCE")
    if not audience:
        return urlopen(url, timeout=8)
    if not audience.startswith("https://") or audience.rstrip("/") != base_url.rstrip("/"):
        raise HTTPException(503, "Private routing audience must equal the configured HTTPS provider URL")
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2.id_token import fetch_id_token
        transport = GoogleRequest()
        def bounded_request(url, method="GET", **kwargs):
            kwargs["timeout"] = 5
            return transport(url=url, method=method, **kwargs)
        token = fetch_id_token(bounded_request, audience)
    except Exception as exc:
        # Authentication exceptions may contain credential details; never expose them.
        raise HTTPException(503, "Private routing authentication is unavailable") from exc
    request = Request(url, headers={"Authorization": "Bearer " + token})
    # Never forward identity tokens to a redirect destination.
    return build_opener(_NoRedirect()).open(request, timeout=8)


def provider_routes(request, base_url):
    """Fixed operator provider; OSRM durations are not live ETAs."""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
        raise HTTPException(503, "Routing provider URL is invalid")
    a, b = request.origin, request.destination
    url = (base_url.rstrip("/") + f"/route/v1/driving/{a.lng},{a.lat};{b.lng},{b.lat}"
           f"?alternatives={'true' if request.alternatives else 'false'}&overview=full&geometries=geojson&steps=false&radiuses=1000;1000")
    try:
        with _open_provider(url, base_url) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Oversized provider response")
        data = json.loads(raw)
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError("Provider returned no route")
        routes = []
        for index, route in enumerate(data["routes"][:8]):
            distance, duration = float(route["distance"]), float(route["duration"])
            if route["geometry"].get("type") != "LineString":
                raise ValueError("Provider path must be a LineString")
            coordinates = route["geometry"]["coordinates"]
            if not math.isfinite(distance + duration) or distance <= 0 or duration <= 0 or not 2 <= len(coordinates) <= 100000:
                raise ValueError("Invalid route metrics")
            if any(len(p) != 2 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in p)
                   or not -180 <= p[0] <= 180 or not -90 <= p[1] <= 90 for p in coordinates):
                raise ValueError("Invalid route geometry")
            routes.append({"route_id": f"provider-{index+1}", "distance_miles": distance / 1609.344,
                "baseline_minutes": duration / 60, "geometry": {"type": "LineString", "coordinates": coordinates},
                "risk_coverage_fraction": 0, "historical_risk_index": None})
    except (URLError, OSError, ValueError, KeyError, TypeError, OverflowError, AttributeError, IndexError) as exc:
        raise HTTPException(502, "Routing provider unavailable or returned an invalid path") from exc
    return {"mode": "provider_baseline_planning", "routes": routes, "provider": parsed.hostname,
        "attribution": "Routing provider / OpenStreetMap contributors", "traffic_status": "unavailable",
        "time_basis": "provider_baseline_non_live", "vehicle_profile": "provider_default_driving",
        "risk_linkage_status": "unavailable_requires_audited_edge_crosswalk",
        "limitations": ["Evaluation only, no routing SLA. Not turn-by-turn navigation; validate access, closures and turn restrictions.",
            "No live congestion or vehicle-specific restrictions are included.",
            "This app does not persist trips; hosting/provider request logs may retain route coordinates."]}


def register_routing_routes(app, required_snapshot, root):
    calls, lock = deque(), threading.Lock()

    @app.get("/api/safety/routing/status")
    def status():
        return {"comparison_available": True, "route_generation_available": bool(os.getenv("SAFETY_ROUTING_OSRM_URL")),
            "provider": "private_self_hosted_osrm" if os.getenv("SAFETY_ROUTING_AUTH_AUDIENCE") else "operator_configured_osrm" if os.getenv("SAFETY_ROUTING_OSRM_URL") else None,
            "authentication": "google_identity_token" if os.getenv("SAFETY_ROUTING_AUTH_AUDIENCE") else "none",
            "coverage": "Nebraska and immediate boundary", "live_traffic_available": False, "navigation_ready": False,
            "risk_linkage": "caller_supplied_snapshot_segment_ids", "limitations": LIMITATIONS}

    @app.post("/api/safety/routing/compare")
    def compare(request: CompareRequest):
        return compare_routes(request, required_snapshot())

    @app.post("/api/safety/routing/routes")
    def routes(request: GenerateRequest):
        base_url = os.getenv("SAFETY_ROUTING_OSRM_URL")
        if not base_url:
            raise HTTPException(503, "Route generation requires an operator-configured OSRM provider (SAFETY_ROUTING_OSRM_URL). Local geometry caches lack directed topology and access restrictions.")
        with lock:
            current = time.monotonic()
            while calls and calls[0] < current - 60:
                calls.popleft()
            if len(calls) >= 6:
                raise HTTPException(429, "Routing evaluation is limited to six requests per minute per instance", headers={"Retry-After": "60"})
            calls.append(current)
        result = provider_routes(request, base_url)
        snapshot = required_snapshot()
        segments = {r["segment_id"]: r for r in snapshot["segments"]}
        from safety.road_geometry import match_route
        for route in result["routes"]:
            route.update({"covered_historical_risk_index": None, "score": None, "rank": None,
                          "risk_linkage_status": "unavailable", "residential_coverage_fraction": 0})
            try:
                linkage = match_route(route["geometry"]["coordinates"], snapshot, root)
                risk = covered = 0.
                fields = set()
                for leg in linkage["matched_legs"]:
                    rate, field = _rate(segments.get(leg["segment_id"]))
                    if rate is not None:
                        covered += leg["length_miles"]
                        risk += rate * leg["length_miles"]
                        fields.add(field)
                total = linkage["total_length_miles"]
                route.update({"risk_coverage_fraction": min(1., covered / total),
                    "historical_risk_index": risk if math.isclose(covered, total) else None,
                    "covered_historical_risk_index": risk, "risk_rate_fields": sorted(fields),
                    "risk_linkage_status": "experimental_sampled_geometry", "linkage": linkage})
            except (OSError, ValueError, KeyError, TypeError):
                route["risk_linkage_detail"] = "Source-bound geometry unavailable, invalid, or outside supported route coverage"
        ranked = [r for r in result["routes"] if not request.weights.residential and
                  (not request.weights.risk or r["historical_risk_index"] is not None)]
        for route in ranked:
            route["score"] = 0.
        for field, weight in (("baseline_minutes", request.weights.time), ("historical_risk_index", request.weights.risk)):
            if ranked and weight:
                low, high = min(r[field] for r in ranked), max(r[field] for r in ranked)
                for route in ranked:
                    route["score"] += weight * ((route[field]-low)/(high-low) if high > low else 0.)
        ranked.sort(key=lambda r: (r["score"], r["baseline_minutes"], r["route_id"]))
        for rank, route in enumerate(ranked, 1):
            route["rank"] = rank
        result.update({"weights": request.weights.model_dump(),
            "preferred_candidate_id": ranked[0]["route_id"] if ranked else None,
            "risk_linkage_status": "experimental_sampled_geometry" if any(
                r["risk_linkage_status"] == "experimental_sampled_geometry" for r in result["routes"]) else "unavailable",
            "snapshot_built_at": snapshot.get("built_at"),
            "risk_index_units": "Historical fatal-crash rate per 100 million VMT multiplied by traversed miles; not a probability.",
            "score_method": "Weighted min-max among covered alternatives. Risk-weighted ranking requires complete sampled risk coverage; residential-weighted ranking unavailable without classifications."})
        result["limitations"] += [
            "Proximity-based road linkage is experimental; direction and grade separation may remain unresolved.",
            "Partial covered risk indexes cannot be compared as whole-route risk. Unknown portions are not zero risk.",
            "Historical exposure proxies are not current predictions or calibrated per-trip crash probabilities."]
        return result

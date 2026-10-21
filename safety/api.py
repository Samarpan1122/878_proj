"""Small production API, serving only the independently built safety snapshot."""
import json
import math
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from safety.sources import SOURCES

ROOT = Path(__file__).resolve().parents[1]


async def validation_error_response(request, exc):
    # Do not echo nonfinite numbers or caller-supplied trip/review data into errors.
    return JSONResponse(status_code=422, content={"detail": [
        {k: error[k] for k in ("type", "loc", "msg") if k in error}
        for error in exc.errors()
    ]})


class BenefitCostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    segment_id: str = Field(min_length=1, max_length=100)
    countermeasure_id: str = Field(min_length=1, max_length=100)
    implementation_cost: float = Field(gt=0, le=1e10)
    annual_maintenance_cost: float = Field(default=0, ge=0, le=1e9)
    service_life_years: int = Field(default=10, ge=1, le=100)
    discount_rate: float = Field(default=0.03, ge=0, le=0.25)
    fatalities_per_crash: float = Field(ge=1, le=100)
    applicability_confirmed: bool = False
    eligible_fraction: float = Field(gt=0, le=1)
    fatal_transfer_assumption_confirmed: bool = False


class SegmentRecord(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False, strict=True)
    segment_id: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    observed: int = Field(ge=0)
    expected_annual: float = Field(ge=0)
    excess_annual: float
    rate_per_100m_vmt: float = Field(ge=0)


SEGMENTS_ADAPTER = TypeAdapter(list[SegmentRecord])


def strict_json(text):
    """Reject constants and exponent overflow, including untyped metadata fields."""
    def finite_float(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("Nonfinite JSON number")
        return value

    def invalid_constant(raw):
        raise ValueError("Nonfinite JSON constant")

    return json.loads(text, parse_float=finite_float, parse_constant=invalid_constant)


class Snapshot:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.Lock()
        self.stamp = None
        self.value = None

    def read(self):
        path = self.root / "snapshot.json"
        with self.lock:
            try:
                try:
                    info = path.stat()
                except FileNotFoundError:
                    self.value, self.stamp = None, None
                    return None
                stamp = (info.st_mtime_ns, info.st_size, info.st_ino)
                if self.stamp != stamp:
                    value = strict_json(path.read_text())
                    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("segments"), list):
                        raise ValueError("Unsupported snapshot schema")
                    if not isinstance(value.get("built_at"), str) or not value["built_at"]:
                        raise ValueError("Snapshot build timestamp is required")
                    validated = SEGMENTS_ADAPTER.validate_python(value["segments"])
                    if not validated:
                        raise ValueError("Snapshot must contain usable road segments")
                    if len({r.segment_id for r in validated}) != len(validated):
                        raise ValueError("Snapshot road IDs must be unique")
                    self.value, self.stamp = value, stamp
            except (OSError, ValueError, ValidationError):
                raise HTTPException(503, "Safety snapshot is invalid; rebuild with python -m safety.cli build")
            return self.value


def create_app(root=None, research=False):
    app = FastAPI(title="GeoCrashAI Safety Engine", version="1.0.0",
                  description="Experimental fatal-crash network screening with explicit exposure provenance.")
    app.add_exception_handler(RequestValidationError, validation_error_response)
    app.state.legacy_models_loaded = False
    store = Snapshot(root or os.getenv("SAFETY_DATA_DIR", os.getenv("GEOCRASH_SAFETY_DATA", "data/safety")))

    def required_snapshot():
        snapshot = store.read()
        if snapshot is None:
            raise HTTPException(503, "Safety data is not built. Run python -m safety.cli ingest, then build.")
        return snapshot

    from safety.planning import register_planning_routes
    from safety.routing import register_routing_routes
    from safety.linkage_audit import register_linkage_routes
    from safety.projection import register_projection_routes
    register_planning_routes(app, required_snapshot)
    register_routing_routes(app, required_snapshot, store.root)
    register_linkage_routes(app, required_snapshot, store.root)
    register_projection_routes(app, required_snapshot)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/healthz")
    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "service": "research_and_safety" if research else "safety",
                "legacy_models_loaded": app.state.legacy_models_loaded}

    @app.get("/readyz")
    @app.get("/ready", include_in_schema=False)
    def ready():
        snapshot = required_snapshot()
        return {"ready": True, "built_at": snapshot["built_at"], "segments": len(snapshot["segments"]),
                "revision": os.getenv("K_REVISION")}

    @app.get("/api/safety/status")
    def status():
        from safety.feeds import feed_status
        snapshot = store.read()
        value = {k: v for k, v in (snapshot or {}).items() if k != "segments"}
        try:
            feeds = feed_status(store.root)
            # Malformed optional feeds must not take the screening API offline.
            strict_json(json.dumps(feeds, allow_nan=False))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            feeds = {"status": "invalid", "stale": True, "detail": "Feed snapshot requires refresh"}
        synthetic = (snapshot or {}).get("data_mode") == "synthetic"
        sources = (snapshot or {}).get("sources", []) if synthetic else list(SOURCES.values())
        return {**value, "ready": snapshot is not None, "sources": sources,
                "data_mode": "synthetic" if synthetic else "official_source_experimental",
                "commercial_ready": False, "feeds": feeds,
                "public_portal_url": os.getenv("PUBLIC_PORTAL_URL"),
                "legacy_explorer_url": "/" if research else os.getenv("LEGACY_EXPLORER_URL")}

    @app.get("/api/safety/readiness")
    def readiness():
        from safety.release import assess_readiness
        return assess_readiness(store.root, verify_files=False)

    @app.get("/api/safety/segments")
    def segments(lat: float | None = Query(default=None, ge=-90, le=90),
                 lng: float | None = Query(default=None, ge=-180, le=180),
                 radius_km: float = Query(default=30, gt=0, le=1000),
                 limit: int = Query(default=100, ge=1, le=1000),
                 offset: int = Query(default=0, ge=0, le=1000000),
                 sort: str = Query(default="excess_annual", pattern="^(excess_annual|rate_per_100m_vmt|observed|expected_annual)$")):
        if (lat is None) != (lng is None):
            raise HTTPException(422, "Supply both lat and lng")
        snapshot = required_snapshot()
        rows = snapshot["segments"]
        if lat is not None:
            def distance(row):
                p1, p2 = math.radians(lat), math.radians(row["lat"])
                dp, dl = p2 - p1, math.radians(row["lng"] - lng)
                a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
                return 6371.0088 * 2 * math.asin(math.sqrt(min(1, a)))
            rows = [{**r, "distance_km": distance(r)} for r in rows]
            rows = [r for r in rows if r["distance_km"] <= radius_km]
        rows = sorted(rows, key=lambda r: (-(r.get(sort) if r.get(sort) is not None else -math.inf), r["segment_id"]))
        page = rows[offset:offset + limit]
        return {"segments": page, "total": len(rows), "returned": len(page), "offset": offset,
                "data_mode": snapshot.get("data_mode", "official_source_experimental"),
                "next_offset": offset + limit if offset + limit < len(rows) else None,
                "spatial_filter": "segment midpoint distance", "outcome": "fatal_crash",
                "limitations": snapshot.get("limitations", [])}

    @app.get("/api/safety/segments/{segment_id}")
    def segment(segment_id: str):
        for row in required_snapshot()["segments"]:
            if row["segment_id"] == segment_id:
                return row
        raise HTTPException(404, "Road segment not found")

    @app.get("/api/safety/segments/{segment_id}/prediction")
    def segment_prediction(segment_id: str):
        from safety.inference import predict_segment
        snapshot = required_snapshot()
        row = next((r for r in snapshot["segments"] if r["segment_id"] == segment_id), None)
        if row is None:
            raise HTTPException(404, "Road segment not found")
        try:
            return predict_segment(snapshot, row)
        except (ValueError, OverflowError) as exc:
            raise HTTPException(503, "Trained road inference is unavailable for this snapshot") from exc

    def evidence_artifact(filename):
        path = store.root / filename
        if not path.exists():
            raise HTTPException(503, "Analysis has not been built for this deployment")
        try:
            if path.stat().st_size > 8_000_000:
                raise ValueError("Oversized evidence artifact")
            result = strict_json(path.read_text())
            if not isinstance(result, dict) or result.get("schema_version") != 1:
                raise ValueError("Unsupported evidence schema")
            inputs = result.get("snapshot_inputs")
            expected_keys = {"crashes_sha256", "roads_sha256"} if filename == "advanced-benchmark.json" else {"crashes_sha256"}
            if not isinstance(inputs, dict) or set(inputs) != expected_keys:
                raise ValueError("Evidence input checksums required")
            if filename == "advanced-benchmark.json":
                if not all(isinstance(result.get(protocol), dict) and isinstance(result[protocol].get("models"), dict)
                           for protocol in ["temporal", "spatial"]) or not isinstance(result.get("decision"), dict):
                    raise ValueError("Benchmark evaluations are required")
            elif (result.get("kind") != "descriptive_fatal_crash_cohorts" or not isinstance(result.get("cohorts"), list)
                  or not isinstance(result.get("years"), list)):
                raise ValueError("Behavior cohorts and years are required")
        except (OSError, ValueError):
            raise HTTPException(503, "Analysis artifact is invalid; rebuild it before use")
        provenance = required_snapshot().get("provenance", {})
        if any(not value or provenance.get(key) != value for key, value in inputs.items()):
            raise HTTPException(409, "Analysis inputs differ from the active snapshot; rebuild the analysis")
        return result

    @app.get("/api/safety/model-evidence")
    def model_evidence():
        return evidence_artifact("advanced-benchmark.json")

    @app.get("/api/safety/behavior")
    def behavior_evidence():
        return evidence_artifact("behavior.json")

    @app.get("/api/safety/countermeasures")
    def countermeasures():
        from safety.economics import CATALOG
        return {"countermeasures": list(CATALOG.values()) if isinstance(CATALOG, dict) else CATALOG}

    @app.post("/api/safety/benefit-cost")
    def benefit_cost(request: BenefitCostRequest):
        from safety.economics import estimate_countermeasure
        snapshot = required_snapshot()
        row = next((r for r in snapshot["segments"] if r["segment_id"] == request.segment_id), None)
        if row is None:
            raise HTTPException(404, "Road segment not found")
        if not request.applicability_confirmed:
            raise HTTPException(422, "Confirm the CMF's road, crash-type and severity applicability before estimating benefits")
        try:
            result = estimate_countermeasure(
                expected_annual=row["expected_annual"], countermeasure_id=request.countermeasure_id,
                implementation_cost=request.implementation_cost,
                annual_maintenance_cost=request.annual_maintenance_cost,
                service_life_years=request.service_life_years, discount_rate=request.discount_rate,
                fatalities_per_crash=request.fatalities_per_crash,
                applicability_confirmed=request.applicability_confirmed,
                eligible_fraction=request.eligible_fraction,
                fatal_transfer_assumption_confirmed=request.fatal_transfer_assumption_confirmed,
            )
            mode = snapshot.get("data_mode", "official_source_experimental")
            result.update(data_mode=mode, segment_id=request.segment_id, snapshot_built_at=snapshot["built_at"])
            if mode == "synthetic":
                result["limitations"] = ["Synthetic workflow calculation on invented inputs; no real road benefit or safety effect is estimated.",
                                         *result.get("limitations", [])]
            return result
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/safety/export")
    def export(commercial: bool = False):
        if commercial:
            raise HTTPException(409, "NDOT redistribution/commercial terms remain unconfirmed; commercial export is disabled")
        snapshot = required_snapshot()
        filename = "geocrash-SYNTHETIC-demo.json" if snapshot.get("data_mode") == "synthetic" else "geocrash-safety-study.json"
        return Response(json.dumps(snapshot, allow_nan=False), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/safety.html", include_in_schema=False)
    def home():
        return FileResponse(ROOT / "web/static/safety.html")

    @app.get("/", include_in_schema=False)
    def landing():
        return FileResponse(ROOT / "web/static" / ("index.html" if research else "safety.html"))

    if research:
        from safety.legacy import add_research_routes
        add_research_routes(app)
        app.mount("/", StaticFiles(directory=ROOT / "web/static", html=True), name="research-static")
        return app

    @app.get("/{asset}", include_in_schema=False)
    def assets(asset: str):
        if asset not in {"safety.css", "safety.js", "safety-evidence.js", "tokens.css"}:
            raise HTTPException(404, "Asset not found")
        return FileResponse(ROOT / "web/static" / asset)

    return app


app = create_app()

"""Opt-in local research routes. Never enabled by the production safety app."""
import json
import threading
from pathlib import Path

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    records: list[dict[str, str | float | bool | None]] = Field(min_length=1, max_length=32)

    @field_validator("records")
    @classmethod
    def bounded_context(cls, records):
        if any(len(row) > 64 or any(len(key) > 64 or isinstance(value, str) and len(value) > 256
                                  for key, value in row.items()) for row in records):
            raise ValueError("Incident context fields exceed supported limits")
        return records


def add_research_routes(app):
    loaded = []
    lock = threading.Lock()

    def engine():
        with lock:
            if not loaded:
                from web.server import Engine
                loaded.append(Engine())
                app.state.legacy_models_loaded = True
            return loaded[0]

    @app.get("/api/config")
    def config():
        from web.server import _env
        return {"googleMapsKey": _env("GOOGLE_MAPS_API_KEY")}

    @app.get("/api/national")
    def national():
        return {"cells": engine().national_grid}

    @app.get("/api/research/advanced")
    def advanced_research():
        path = Path("outputs/research/advanced_benchmark.json")
        if not path.exists():
            raise HTTPException(503, "Run python -m src.advanced_benchmark to build the research comparison")
        try:
            value = json.loads(path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError("Invalid research report")
            return value
        except (OSError, ValueError):
            raise HTTPException(503, "Research comparison is invalid; rebuild the artifact")

    @app.post("/api/research/predict")
    def predict_research(request: ResearchPredictionRequest):
        from src.advanced_inference import predict_incidents
        try:
            return predict_incidents(request.records)
        except FileNotFoundError:
            raise HTTPException(503, "Research weights are not built; run the advanced benchmark first")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/api/research/metro")
    def metro_study():
        folder = Path("outputs/research/metro")
        reports = {}
        for name, filename in [("fixed", "benchmark.json"), ("online", "online.json"),
                               ("data_audit", "data_audit.json"), ("gis_correction", "gis_correction.json")]:
            path = folder / filename
            if not path.exists():
                reports[name] = None
                continue
            try:
                if path.stat().st_size > 8_000_000:
                    raise ValueError("Oversized report")
                value = json.loads(path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if not isinstance(value, dict):
                    raise ValueError("Invalid report")
                json.dumps(value, allow_nan=False)
                reports[name] = value
            except (ValueError, OSError):
                raise HTTPException(503, "Omaha study report is invalid or still being written; retry after the run finishes")
        if not any(reports.values()):
            raise HTTPException(503, "The corrected Omaha study has not been built")
        return {"research_only": True, "commercial_eligible": False, **reports}

    @app.get("/api/{operation}")
    def query(operation: str, request: Request, lat: float = Query(default=41.2565, ge=-90, le=90),
              lng: float = Query(default=-95.9345, ge=-180, le=180), r: float = Query(default=1, ge=.1, le=25)):
        from web.server import _clean
        files = {"eda": "eda.json", "model-plots": "model_plots.json", "leaderboard": "leaderboard.json"}
        if operation in files:
            path = Path("outputs/tables") / files[operation]
            if not path.exists():
                raise HTTPException(503, "Research artifact not built")
            return _clean(json.loads(path.read_text()))
        if operation not in {"report", "scenario", "live", "models"}:
            raise HTTPException(404, "Unknown research endpoint")
        e = engine()
        if operation == "models":
            import pandas as pd
            return _clean({"metrics": e.m["metrics"], "regimes": pd.read_csv("outputs/tables/engine_regimes.csv").to_dict("records"), "importance": e.importance})
        try:
            if operation == "report":
                return _clean(e.report(lat, lng, r))
            from web.report import SCENARIO_KEYS, live
            if operation == "scenario":
                params = {k: cast(request.query_params[k]) for k, cast in SCENARIO_KEYS.items() if k in request.query_params}
                return _clean(e.scenario(lat, lng, r, params))
            d = e.rows_near(lat, lng, r)
            if d.empty:
                raise ValueError("No research crashes in radius")
            return _clean(live(d, {**e.ctx, "r": r}, lat, lng))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

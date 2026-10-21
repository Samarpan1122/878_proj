"""GeoCrashAI research engine and integrated FastAPI entry point on localhost:8878.

  GET /api/report?lat&lng&r   full location report (see web/report.py)
  GET /api/models             engine evaluation metrics + national regimes
  GET /api/config             browser Maps key (from env / gitignored .env; restrict it by referrer)
Needs `python -m src.engine` first (models/engine.joblib, data/processed/engine_rows.parquet).
The main entry now uses safety.api.create_app(research=True); the retained Handler
is legacy compatibility code. Public deployments use safety.api:app, which never
loads this research engine or its noncommercial artifacts.
"""
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from src.engine import rows
from src.features import EARTH_KM
from src.engine import SEV_FEATURES, matrix
import web.report as report_mod
from web.report import SCENARIO_KEYS, build, live, scenario

DATA, OUT, STATIC = Path("data/processed"), Path("outputs/tables"), Path(__file__).parent / "static"
PORT = 8878
MAX_RADIUS_KM = 25.0
NATIONAL_CELL_DEG, NATIONAL_MIN_N = 0.1, 20   # ~10 km columns for the 3D overview
DENSITY_CELL_DEG = 0.01
SCORE_COLS = ["p_severe", "regime"]
REPORT_EXTRA_COLS = ["log_duration", "Temperature(F)", "Visibility(mi)", "Precipitation(in)", "Wind_Speed(mph)", "Humidity(%)"]


def _env(name: str) -> str:
    """Read a setting from the environment, else from a gitignored .env file."""
    if os.environ.get(name):
        return os.environ[name]
    env = Path(".env")
    lines = env.read_text().splitlines() if env.exists() else []
    return next((l.split("=", 1)[1].strip() for l in lines if l.startswith(name + "=")), "")


def load_rows() -> pd.DataFrame:
    saved = pd.read_parquet(DATA / "engine_rows.parquet")
    if all(c in saved for c in REPORT_EXTRA_COLS):
        return saved
    df = rows()  # older engine run: rebuild cleaned rows (same deterministic order) and attach saved scores
    if len(df) != len(saved) or not np.allclose(df.Start_Lat.to_numpy(), saved.Start_Lat.to_numpy()):
        raise RuntimeError("engine_rows.parquet is out of sync with the data; rerun `python -m src.engine`")
    return df.assign(**{c: saved[c].to_numpy() for c in SCORE_COLS})


class Engine:
    def __init__(self):
        self.df = load_rows()
        self.m = joblib.load("models/engine.joblib")
        report_mod.STATS[0] = self.m.get("cell_stats")
        self.tree = BallTree(np.radians(self.df[["Start_Lat", "Start_Lng"]].to_numpy()), metric="haversine")
        d, w = self.df, self.df.w
        # Density reference: weighted crashes per km^2 in every ~1 km cell that has any crash.
        cell = (d.Start_Lat // DENSITY_CELL_DEG).astype(int) * 100000 + (d.Start_Lng // DENSITY_CELL_DEG).astype(int)
        cell_km2 = (DENSITY_CELL_DEG * 111.32) ** 2 * np.cos(np.radians(d.Start_Lat.groupby(cell).mean()))
        by_state = d.groupby("State")
        self.ctx = {
            "engine": self.m,
            "cell_density": (w.groupby(cell).sum() / cell_km2).to_numpy(),
            "national": {"severe_rate": float(np.average(d.is_severe, weights=w)), "median_duration": float(d.duration_min.median()),
                         "night_share": float(np.average(d.is_night, weights=w))},
            "regime_share": (w.groupby(d.regime).sum() / w.sum()).to_dict(),
            "state_stats": {s: {"severe_rate": float(np.average(x.is_severe, weights=x.w)), "median_duration": float(x.duration_min.median()),
                                "night_share": float(np.average(x.is_night, weights=x.w))} for s, x in by_state},
        }
        print(f"engine ready: {len(d):,} rows (~{int(w.sum()):,} accidents)", flush=True)

        self.importance = importance(d, self.m["severity"], self.m.get("cell_stats"))
        g = d.assign(cx=(d.Start_Lat // NATIONAL_CELL_DEG), cy=(d.Start_Lng // NATIONAL_CELL_DEG), ws=d.w * d.is_severe).groupby(["cx", "cy"])
        grid = pd.DataFrame({"lat": g.Start_Lat.mean(), "lng": g.Start_Lng.mean(), "n": g.w.sum(), "severe": g.ws.sum()})
        self.national_grid = grid[grid.n >= NATIONAL_MIN_N].round(4).to_numpy().tolist()

    def rows_near(self, lat, lng, r_km) -> pd.DataFrame:
        return self.df.iloc[self.tree.query_radius(np.radians([[lat, lng]]), r=r_km / EARTH_KM)[0]]

    def report(self, lat, lng, r_km) -> dict:
        return build(self.rows_near(lat, lng, r_km), {**self.ctx, "r": r_km}, lat, lng)

    def scenario(self, lat, lng, r_km, params) -> dict:
        d = self.rows_near(lat, lng, r_km)
        if d.empty:
            raise ValueError("no crashes in radius")
        return scenario(d, self.ctx, lat, lng, params)


IMPORTANCE_N, IMPORTANCE_REPEATS = 30000, 3
IMPORTANCE_GROUPS = {"weather type": [c for c in SEV_FEATURES if c.startswith("wx_")], "location (lat/lng)": ["Start_Lat", "Start_Lng"]}


def importance(d: pd.DataFrame, model, stats=None) -> list[dict]:
    """Grouped permutation importance of the severity model (drop in severe-vs-not AUC), cached to CSV."""
    path = OUT / "engine_importance.csv"
    if path.exists():
        return pd.read_csv(path).to_dict("records")
    from sklearn.metrics import roc_auc_score
    s = d.sample(IMPORTANCE_N, random_state=0)
    X, y = matrix(s, stats)[SEV_FEATURES], s.is_severe.to_numpy()
    cls = list(model.classes_)
    auc = lambda X_: roc_auc_score(y, model.predict_proba(X_)[:, [cls.index(3), cls.index(4)]].sum(1))
    grouped = set(sum(IMPORTANCE_GROUPS.values(), []))
    groups = {**IMPORTANCE_GROUPS, **{c.replace("(", " (").replace("_", " ").lower(): [c] for c in SEV_FEATURES if c not in grouped}}
    ref, rng, rows = auc(X), np.random.default_rng(0), []
    for name, cols in groups.items():
        drops = []
        for _ in range(IMPORTANCE_REPEATS):
            Xp = X.copy()
            perm = rng.permutation(len(X))
            Xp[cols] = X[cols].to_numpy()[perm]
            drops.append(ref - auc(Xp))
        rows.append({"feature": name, "auc_drop": float(np.mean(drops))})
    out = pd.DataFrame(rows).sort_values("auc_drop", ascending=False)
    out.to_csv(path, index=False)
    print(f"permutation importance computed (base AUC {ref:.3f})", flush=True)
    return out.to_dict("records")


class Handler(SimpleHTTPRequestHandler):
    engine: Engine = None

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, default=float, allow_nan=False).encode() if code == 200 else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        try:
            if url.path == "/api/config":
                return self._json({"googleMapsKey": _env("GOOGLE_MAPS_API_KEY")})
            if url.path == "/api/national":
                return self._json({"cells": self.engine.national_grid})
            if url.path in ("/api/eda", "/api/model-plots"):
                path = OUT / ("eda.json" if url.path == "/api/eda" else "model_plots.json")
                return self._json(_clean(json.loads(path.read_text())) if path.exists() else {"missing": True})
            if url.path == "/api/leaderboard":
                path = OUT / "leaderboard.json"
                return self._json(_clean(json.loads(path.read_text())) if path.exists() else {"tasks": {}})
            if url.path == "/api/models":
                regimes = pd.read_csv(OUT / "engine_regimes.csv").to_dict("records")
                return self._json({"metrics": self.engine.m["metrics"], "regimes": regimes, "importance": self.engine.importance})
            if url.path == "/api/live":
                lat, lng = float(q["lat"][0]), float(q["lng"][0])
                r = min(max(float(q.get("r", ["1"])[0]), 0.1), MAX_RADIUS_KM)
                d = self.engine.rows_near(lat, lng, r)
                if d.empty:
                    raise ValueError("no crashes in radius")
                return self._json(_clean(live(d, {**self.engine.ctx, "r": r}, lat, lng)))
            if url.path == "/api/scenario":
                lat, lng = float(q["lat"][0]), float(q["lng"][0])
                r = min(max(float(q.get("r", ["1"])[0]), 0.1), MAX_RADIUS_KM)
                params = {k: t(q[k][0]) for k, t in SCENARIO_KEYS.items() if k in q}
                return self._json(_clean(self.engine.scenario(lat, lng, r, params)))
            if url.path != "/api/report":
                return super().do_GET()
            lat, lng = float(q["lat"][0]), float(q["lng"][0])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("lat/lng out of range")
            r = min(max(float(q.get("r", ["1"])[0]), 0.1), MAX_RADIUS_KM)
            return self._json(_clean(self.engine.report(lat, lng, r)))
        except (KeyError, ValueError) as e:
            return self._json({"error": f"bad query: {e}"}, 400)


def _clean(o):
    """NaN/inf -> None so the payload is valid JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    return o


if __name__ == "__main__":
    import uvicorn
    from safety.api import create_app
    print(f"GeoCrashAI explorer + safety workspace on http://localhost:{PORT}", flush=True)
    uvicorn.run(create_app(research=True), host="127.0.0.1", port=PORT)

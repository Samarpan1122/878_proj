import copy
import math
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from scipy.stats import gamma, nbinom

from safety.projection import ProjectionRequest, project_segment, register_projection_routes

SNAPSHOT = {"built_at": "2026-09-30", "model": {"kind": "experimental_local_nb2_spf", "outcome": "fatal_crash",
    "intercept": math.log(.1), "log_aadt_coefficient": .75, "alpha": .5, "training_years": [2021,2022,2023,2024]},
    "segments": [{"segment_id": "A", "observed_fatal_crashes": 3, "predicted_period": 2., "years_observed": 4.,
                  "length_miles": 5., "aadt": 10000., "aadt_year": 2025, "aadt_aligned": False}]}
NOW = datetime(2026,9,30,tzinfo=timezone.utc)


def request(**kwargs):
    return ProjectionRequest(segment_id="A", target_year=2027, aadt=12000., scenario_note="Planning traffic-volume assumption", **kwargs)


def client(snapshot=None):
    app = FastAPI()
    register_projection_routes(app, lambda: snapshot or SNAPSHOT)
    return TestClient(app)


def body(**kwargs):
    return {"segment_id": "A", "target_year": 2027, "aadt": 12000., "scenario_note": "Agency traffic scenario", **kwargs}


def test_calendar_year_spf_and_posterior_formula():
    result = project_segment(request(), SNAPSHOT, NOW)
    spf = 5 * 365 / 365.25 * .1 * 1.2**.75
    assert result["spf_annual_fatal_crashes"] == pytest.approx(spf)
    assert result["posterior"]["shape"] == 5
    assert result["posterior"]["rate"] == 4
    assert result["mean_annual_fatal_crashes"] == pytest.approx(5 / 4 * spf)
    assert result["future_vehicle_miles"] == 12000 * 5 * 365
    assert result["projected_rate_per_100m_vmt"] == pytest.approx(5 / 4 * spf / (12000 * 5 * 365) * 1e8)
    assert result["validated_forecast"] is False


def test_mean_and_predictive_intervals_are_different_distributions():
    result = project_segment(request(), SNAPSHOT, NOW)
    spf = result["spf_annual_fatal_crashes"]
    mean_interval = gamma.ppf([.025,.975], 5, scale=spf/4)
    count_interval = nbinom.ppf([.025,.975], 5, 4/(4+spf))
    assert list(result["conditional_mean_interval95"].values()) == pytest.approx(mean_interval)
    assert list(result["predictive_count_interval95"].values()) == pytest.approx(count_interval)
    assert all(isinstance(v,int) for v in result["predictive_count_interval95"].values())
    assert result["predictive_count_interval95"]["lower"] == 0
    assert result["conditional_mean_interval95"]["lower"] > 0


def test_leap_year_days_and_monotonic_exposure():
    ordinary = project_segment(ProjectionRequest(**body(target_year=2027)), SNAPSHOT, NOW)
    leap = project_segment(ProjectionRequest(**body(target_year=2028)), SNAPSHOT, NOW)
    assert leap["mean_annual_fatal_crashes"] / ordinary["mean_annual_fatal_crashes"] == pytest.approx(366/365)
    more = project_segment(ProjectionRequest(**body(aadt=24000)), SNAPSHOT, NOW)
    assert more["mean_annual_fatal_crashes"] / ordinary["mean_annual_fatal_crashes"] == pytest.approx(2**.75)
    # Nonlinear SPF means a volume increase is not a causal risk improvement.
    assert any("not a causal" in x for x in more["limitations"])


@pytest.mark.parametrize("changes", [{"aadt": 0}, {"aadt": True}, {"target_year": True}, {"target_year": 2040},
                                      {"aadt": "12000"}, {"scenario_note": ""}, {"segment_id": ""}])
def test_request_bounds_and_strict_types(changes):
    assert client().post("/api/safety/projection", json=body(**changes)).status_code == 422


def test_nan_and_infinity_rejected():
    for value in [float("nan"),float("inf")]:
        with pytest.raises(ValidationError):
            ProjectionRequest(**body(aadt=value))


def test_unknown_segment_and_training_year_gate():
    assert client().post("/api/safety/projection",json=body(segment_id="missing")).status_code == 404
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["model"]["training_years"].append(2027)
    assert client(snapshot).post("/api/safety/projection",json=body()).status_code == 422


@pytest.mark.parametrize("field,value", [("alpha",0), ("intercept",float("inf")), ("intercept",10000.), ("training_years",[])])
def test_invalid_model_fails_closed(field,value):
    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["model"][field] = value
    assert client(snapshot).post("/api/safety/projection",json=body()).status_code == 503


def test_missing_segment_history_cannot_use_annual_count_as_prior():
    snapshot = copy.deepcopy(SNAPSHOT)
    del snapshot["segments"][0]["predicted_period"]
    snapshot["segments"][0]["expected_annual"] = .5
    assert client(snapshot).post("/api/safety/projection",json=body()).status_code == 503


def test_projection_does_not_change_snapshot_and_reports_old_exposure():
    before = copy.deepcopy(SNAPSHOT)
    result = project_segment(ProjectionRequest(**body(target_year=2035)),SNAPSHOT,NOW)
    assert SNAPSHOT == before
    assert any("vintage proxy" in x for x in result["limitations"])
    assert any("Long-horizon" in x for x in result["limitations"])
    assert result["horizon_years"] == 11
    assert result["baseline_aadt_year"] == 2025


def test_past_posttraining_year_is_not_called_current_forecast():
    result = project_segment(ProjectionRequest(**body(target_year=2025)),SNAPSHOT,NOW)
    assert any("already ended" in x for x in result["limitations"])

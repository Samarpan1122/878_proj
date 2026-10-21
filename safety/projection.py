"""Conditional post-training traffic-exposure projections with the fitted NB SPF.

No model is trained here. A Gamma-Poisson posterior conditions a segment multiplier
on the recorded observation period, then projects one supplied calendar year's
fatal-crash counts. This is scenario analysis, not prospectively validated forecasting.
"""
import calendar
from datetime import datetime, timezone
import math

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from scipy.stats import gamma, nbinom


class ProjectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    segment_id: str = Field(min_length=1, max_length=100)
    target_year: int = Field(ge=2025, le=2035)
    aadt: float = Field(gt=0, le=1_000_000)
    scenario_note: str = Field(min_length=1, max_length=1000)


class _ModelInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    intercept: float
    log_aadt_coefficient: float
    alpha: float = Field(gt=0, le=1000)
    training_years: list[int] = Field(min_length=1, max_length=100)


class _SegmentInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    observed_fatal_crashes: int = Field(ge=0, le=1_000_000)
    predicted_period: float = Field(gt=0, le=100_000_000)
    years_observed: float = Field(gt=0, le=100)
    length_miles: float = Field(gt=0, le=10000)
    aadt: float = Field(gt=0, le=1_000_000)


LIMITATIONS = [
    "Conditional traffic-exposure projection using an existing fitted model; not a prospectively validated forecast.",
    "Assumes the segment's historical latent risk persists and roadway design, reporting, weather and driving behavior do not change.",
    "AADT is a user-supplied scenario assumption. Changing AADT in this model is not a causal estimate of a traffic intervention.",
    "Both intervals condition on fitted coefficients, matched crash counts and exposure. They exclude parameter estimation, road matching and AADT measurement uncertainty.",
    "The mean interval describes uncertain expected frequency; the predictive count interval additionally includes Poisson count variation.",
    "Fatal crashes are not fatalities, all-severity crashes or calibrated individual-driver crash probabilities.",
    "Experimental local SPF; not HSM calibrated. No new model training or future holdout validation is performed by this endpoint.",
]


def project_segment(request: ProjectionRequest, snapshot, now=None):
    row = next((r for r in snapshot["segments"] if r["segment_id"] == request.segment_id), None)
    if row is None:
        raise HTTPException(404, "Road segment is not in the active screening snapshot")
    model = snapshot.get("model", {})
    if model.get("kind") != "experimental_local_nb2_spf" or model.get("outcome") != "fatal_crash":
        raise HTTPException(503, "Projection requires the fitted local NB fatal-crash SPF")
    try:
        coefficients = _ModelInputs.model_validate({k: model[k] for k in _ModelInputs.model_fields})
        segment = _SegmentInputs.model_validate({k: row[k] for k in _SegmentInputs.model_fields})
    except (ValidationError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Active snapshot lacks valid fitted coefficients or segment exposure history") from exc
    training_years = sorted(set(coefficients.training_years))
    if any(year < 1900 or year > 2034 for year in training_years):
        raise HTTPException(503, "Active model training years are invalid")
    if request.target_year <= training_years[-1]:
        raise HTTPException(422, "Target year must be later than the model's last training year")
    if not request.scenario_note.strip():
        raise HTTPException(422, "Describe the source or rationale for the assumed traffic volume")
    days = 366 if calendar.isleap(request.target_year) else 365
    calendar_factor = days / 365.25
    try:
        spf = segment.length_miles * calendar_factor * math.exp(
            coefficients.intercept + coefficients.log_aadt_coefficient * math.log(request.aadt / 10000))
        baseline_spf = segment.length_miles * calendar_factor * math.exp(
            coefficients.intercept + coefficients.log_aadt_coefficient * math.log(segment.aadt / 10000))
        shape = 1 / coefficients.alpha + segment.observed_fatal_crashes
        rate = 1 / coefficients.alpha + segment.predicted_period
        mean = shape / rate * spf
        baseline_mean = shape / rate * baseline_spf
        mean_interval = gamma.ppf([.025, .975], a=shape, scale=spf / rate)
        probability = rate / (rate + spf)
        count_interval = nbinom.ppf([.025, .975], n=shape, p=probability)
        future_vmt = request.aadt * segment.length_miles * days
        risk_rate = mean / future_vmt * 100_000_000
        values = [spf, baseline_spf, shape, rate, mean, baseline_mean, future_vmt, risk_rate, *mean_interval, *count_interval]
        if not all(math.isfinite(float(value)) for value in values) or min(spf, future_vmt, mean) <= 0:
            raise ValueError("Nonfinite or underflowed projection")
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        raise HTTPException(503, "Active model coefficients cannot support this exposure projection") from exc
    now = now or datetime.now(timezone.utc)
    horizon = request.target_year - training_years[-1]
    limits = LIMITATIONS.copy()
    if not row.get("aadt_aligned", False):
        limits.append("Historical model exposure uses an AADT vintage proxy rather than year-aligned traffic measurements.")
    if horizon > 5:
        limits.append("Long-horizon extrapolation exceeds five years after training; structural changes are not modeled.")
    if request.target_year < now.year:
        limits.append("The target calendar year has already ended; this remains an unvalidated post-training scenario, not a current forecast.")
    if request.aadt > segment.aadt * 2 or request.aadt < segment.aadt / 2:
        limits.append("Assumed traffic differs by more than a factor of two from this segment's baseline; support for this extrapolation is unknown.")
    return {"mode": "conditional_post_training_exposure_projection", "validated_forecast": False,
        "segment_id": request.segment_id, "target_year": request.target_year, "horizon_years": horizon,
        "evaluated_at": now.isoformat(), "snapshot_built_at": snapshot.get("built_at"),
        "training_years": training_years, "model_kind": model["kind"], "outcome": "fatal_crash",
        "calendar_days": days, "calendar_year_factor": calendar_factor,
        "supplied_aadt": request.aadt, "baseline_aadt": segment.aadt, "baseline_aadt_year": row.get("aadt_year"),
        "aadt_ratio": request.aadt / segment.aadt, "scenario_note": request.scenario_note.strip(),
        "length_miles": segment.length_miles, "future_vehicle_miles": future_vmt,
        "spf_annual_fatal_crashes": spf, "mean_annual_fatal_crashes": mean,
        "baseline_aadt_mean_annual_fatal_crashes": baseline_mean,
        "conditional_mean_interval95": {"lower": float(mean_interval[0]), "upper": float(mean_interval[1])},
        "predictive_count_interval95": {"lower": int(count_interval[0]), "upper": int(count_interval[1])},
        "projected_rate_per_100m_vmt": risk_rate,
        "posterior": {"distribution": "Gamma multiplier / Poisson fatal-crash counts", "shape": shape, "rate": rate,
                      "observed_fatal_crashes": segment.observed_fatal_crashes,
                      "predicted_observation_period": segment.predicted_period, "years_observed": segment.years_observed},
        "method": "SPF = length_miles × calendar_days/365.25 × exp(intercept + coefficient × log(AADT/10000)); posterior Gamma multiplier shape=1/alpha+observed, rate=1/alpha+predicted_period.",
        "limitations": limits}


def register_projection_routes(app, required_snapshot):
    @app.post("/api/safety/projection")
    def projection(request: ProjectionRequest):
        return project_segment(request, required_snapshot())

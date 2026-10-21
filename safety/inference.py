"""Recompute a stored road's experimental NB/EB screening estimate from its model.

This is retrospective annualized screening, not a live collision forecast.
"""
import hashlib
import json
import math

from scipy.stats import gamma


def predict_segment(snapshot, row):
    if snapshot.get("data_mode") == "synthetic":
        raise ValueError("A synthetic fixture has no trained model")
    model = snapshot.get("model", {})
    if model.get("kind") != "experimental_local_nb2_spf":
        raise ValueError("Unsupported or missing trained road model")
    try:
        intercept, coefficient, alpha = (float(model[k]) for k in ["intercept", "log_aadt_coefficient", "alpha"])
        aadt, length, years, observed = (float(row[k]) for k in ["aadt", "length_miles", "years", "observed"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Stored road/model lacks inference inputs") from exc
    if not all(math.isfinite(v) for v in [intercept, coefficient, alpha, aadt, length, years, observed]):
        raise ValueError("Inference requires finite inputs")
    if min(alpha, aadt, length, years) <= 0 or observed < 0 or not observed.is_integer():
        raise ValueError("Invalid stored count or exposure")
    # Archived panel period is authoritative when annual traffic varies. The
    # selected release uses a constant 2025 proxy; verify its coefficient replay.
    annual = length * math.exp(intercept + coefficient * math.log(aadt / 10000))
    period = float(row.get("predicted_period", annual * years))
    if not math.isfinite(period) or period <= 0:
        raise ValueError("Invalid archived period prediction")
    # The serving snapshot was serialized by pandas at 10 decimal places.
    # Account for that quantization, particularly for very small annual means.
    if not math.isclose(period / years, annual, rel_tol=1e-8, abs_tol=1e-9):
        raise ValueError("Stored traffic varies by year; use the full panel for coefficient replay")
    shape, rate = 1 / alpha + observed, 1 / alpha + period
    expected = shape / rate * annual
    return {"segment_id": row["segment_id"], "data_mode": "official_source_experimental",
            "model": model["kind"], "model_sha256": hashlib.sha256(json.dumps(model, sort_keys=True, allow_nan=False).encode()).hexdigest(),
            "outcome": "annualized_fatal_crash_count", "inference": "recomputed_from_trained_coefficients_and_recorded_road_history",
            "input": {"aadt": aadt, "aadt_year": row.get("aadt_year"), "length_miles": length,
                      "observed_fatal_crashes": int(observed), "observed_year_equivalents": years},
            "spf_annual": annual, "eb_annual": expected, "excess_annual": expected - annual,
            "lower_annual": float(gamma.ppf(.025, shape, scale=1/rate) * annual),
            "upper_annual": float(gamma.ppf(.975, shape, scale=1/rate) * annual),
            "training_years": model.get("training_years"), "snapshot_built_at": snapshot.get("built_at"),
            "limitations": ["Retrospective fitted screening; not a current-year or individual-collision forecast.",
                            "AADT vintage is a historical exposure proxy; no facility-specific agency validation.",
                            "Intervals condition on the fitted model; matching, exposure and coefficient uncertainty are omitted."]}

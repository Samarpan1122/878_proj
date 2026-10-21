"""Distribution/coverage checks; drift is a review signal, never automatic model promotion."""
import numpy as np
import pandas as pd


def population_stability_index(reference, current, bins=10):
    if bins < 2:
        raise ValueError("At least two bins are required")
    before = pd.to_numeric(pd.Series(reference), errors="coerce").replace([np.inf, -np.inf], np.nan)
    after = pd.to_numeric(pd.Series(current), errors="coerce").replace([np.inf, -np.inf], np.nan)
    if not len(before) or not len(after) or not before.notna().any():
        raise ValueError("PSI requires nonempty cohorts and finite reference observations")
    edges = np.unique(np.quantile(before.dropna(), np.linspace(0, 1, bins + 1)))
    if len(edges) == 1:
        value = edges[0]
        edges = np.array([-np.inf, value, np.nextafter(value, np.inf), np.inf])
    else:
        edges[0], edges[-1] = -np.inf, np.inf
    def shares(values):
        counts = np.r_[np.histogram(values.dropna(), bins=edges)[0], values.isna().sum()]
        probabilities = (counts + 0.5) / (len(values) + 0.5 * len(counts))
        return probabilities
    a, b = shares(before), shares(after)
    return float(np.sum((b - a) * np.log(b / a)))


def drift_report(reference, current, features=None):
    if reference.empty or current.empty:
        raise ValueError("Drift comparison requires two nonempty snapshots")
    features = list(features) if features is not None else [c for c in ["aadt", "length_miles", "observed_crashes"] if c in reference and c in current]
    scores, reasons = {}, []
    for feature in features:
        if feature not in reference or feature not in current:
            raise ValueError(f"Missing drift feature: {feature}")
        try:
            scores[feature] = population_stability_index(reference[feature], current[feature])
        except ValueError:
            scores[feature] = None
            reasons.append(f"{feature}: insufficient finite reference data")
        if scores[feature] is not None and scores[feature] >= 0.2:
            reasons.append(f"{feature}: PSI >= 0.2")
    ratio = len(current) / len(reference)
    if ratio < 0.8 or ratio > 1.2:
        reasons.append("Row coverage changed by more than 20%")
    missingness = {}
    for feature in features:
        change = float(current[feature].isna().mean() - reference[feature].isna().mean())
        missingness[feature] = change
        if change > 0.05:
            reasons.append(f"{feature}: missingness increased by more than 5 percentage points")
    return {"psi": scores, "missingness_change": missingness, "reference_rows": len(reference),
            "current_rows": len(current), "coverage_ratio": ratio, "review_required": bool(reasons),
            "reasons": reasons, "recommendation": "Investigate data coverage and evaluate a candidate refit" if reasons else "Continue monitoring",
            "promotion": "manual_review_required", "threshold_note": "Operational heuristics, not statistical significance tests."}

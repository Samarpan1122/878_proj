import math

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from safety.api import create_app
from safety.inference import predict_segment
from safety.io import write_json
from safety.models import screen_network


def inputs():
    model = {"kind": "experimental_local_nb2_spf", "intercept": -3., "log_aadt_coefficient": .8,
             "alpha": .4, "training_years": [2021, 2022]}
    panel = pd.DataFrame([{"segment_id": "R1", "year": year, "aadt": 6000., "length_miles": .7,
                           "days": 365., "fatal_crashes": count, "fatalities": count,
                           "vehicle_miles": 6000*.7*365, "model_eligible": True, "aadt_aligned": False,
                           "lat": 41., "lng": -96.} for year, count in [(2021, 0), (2022, 2)]])
    row = screen_network(panel, model).iloc[0].to_dict()
    row.update(years=row["years_observed"], observed=int(row["observed_fatal_crashes"]), aadt_year=2025,
               expected_annual=row["eb_annual_fatal_crashes"], excess_annual=row["excess_annual_fatal_crashes"],
               rate_per_100m_vmt=row["observed_fatal_crashes_per_100m_vmt"])
    return {"schema_version": 1, "built_at": "2026-09-30T00:00:00Z", "model": model, "segments": [row]}, row


def test_inference_replays_original_panel_engine():
    snapshot, row = inputs()
    result = predict_segment(snapshot, row)
    for actual, expected in [("spf_annual", "predicted_annual_fatal_crashes"), ("eb_annual", "eb_annual_fatal_crashes"),
                             ("lower_annual", "eb_annual_lower95"), ("upper_annual", "eb_annual_upper95")]:
        assert result[actual] == pytest.approx(row[expected], rel=1e-12)
    assert result["data_mode"] == "official_source_experimental"
    assert "Retrospective" in result["limitations"][0]


def test_endpoint_serves_recomputed_model_and_rejects_unavailable(tmp_path):
    snapshot, row = inputs()
    write_json(tmp_path / "snapshot.json", snapshot)
    client = TestClient(create_app(tmp_path))
    result = client.get("/api/safety/segments/R1/prediction")
    assert result.status_code == 200 and result.json()["eb_annual"] > 0
    assert client.get("/api/safety/segments/unknown/prediction").status_code == 404
    snapshot["data_mode"] = "synthetic"
    write_json(tmp_path / "snapshot.json", snapshot)
    assert client.get("/api/safety/segments/R1/prediction").status_code == 503


@pytest.mark.parametrize("field,value", [("aadt", 0), ("length_miles", math.inf), ("years", -1), ("observed", 1.5), ("predicted_period", 900)])
def test_inference_rejects_invalid_or_varying_exposure(field, value):
    snapshot, row = inputs()
    row[field] = value
    with pytest.raises(ValueError):
        predict_segment(snapshot, row)

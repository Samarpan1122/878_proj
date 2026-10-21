import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from safety.economics import estimate_countermeasure
from safety.exposure import build_segment_years, match_crashes
from safety.models import fit_spf, predict_spf, screen_network, validate_spf


def roads():
    g = gpd.GeoDataFrame({"segment_id": ["A", "B", "C"], "aadt": [1000., 1000., 0.],
        "aadt_year": [2020, 2020, 2020], "length_miles": [1., 1., 1.],
        "route": ["A", "B", "C"], "facility_type": ["unknown"] * 3},
        geometry=[LineString([(500000, 4500000), (501000, 4500000)]),
                  LineString([(500000, 4500004), (501000, 4500004)]),
                  LineString([(500000, 4501000), (501000, 4501000)])], crs=26914).to_crs(4326)
    g["lat"] = 40.6
    g["lng"] = -99.
    return g


def crashes():
    pts = gpd.GeoSeries([Point(500500, 4500002), Point(500500, 4501000),
                        Point(500500, 4501200), Point(500500, 4500200)], crs=26914).to_crs(4326)
    return pd.DataFrame({"crash_id": ["one", "two", "three", "four"], "year": [2020] * 4,
                         "lat": [pts.y.iloc[0], pts.y.iloc[1], pts.y.iloc[2], np.nan],
                         "lng": pts.x.to_list(), "fatalities": [1, 2, 1, 1], "outcome": "fatal_crash"})


def test_matching_withholds_parallel_roads_and_preserves_coverage():
    matches, report = match_crashes(crashes(), roads())
    assert matches.match_status.to_list() == ["ambiguous", "matched", "outside_tolerance", "unlocated"]
    assert matches.segment_id.notna().sum() == 1
    assert matches.loc[1, "segment_id"] == "C"
    assert report["matched"] == report["ambiguous"] == report["outside_tolerance"] == report["unlocated"] == 1
    assert report["matched_fraction"] == .25
    with pytest.raises(ValueError, match="<=50m"):
        match_crashes(crashes(), roads(), max_distance_m=100)


def test_panel_keeps_zeroes_leap_years_invalid_exposure_and_proxy_status():
    panel, report = build_segment_years(crashes(), roads(), [2020, 2021])
    assert len(panel) == 6 and report["zero_crash_segment_years"] == 5
    a = panel[panel.segment_id.eq("A")].set_index("year")
    assert a.loc[2020, "vehicle_miles"] == 366000
    assert a.loc[2021, "vehicle_miles"] == 365000
    assert a.loc[2021, "exposure_status"] == "aadt_vintage_proxy"
    assert panel[panel.segment_id.eq("C")].vehicle_miles.isna().all()
    strict, _ = build_segment_years(crashes(), roads(), [2020, 2021], allow_aadt_proxy=False)
    assert strict.model_eligible.sum() == 2
    assert strict.fatalities.sum() == 2  # one crash, two fatalities, not two crashes


def synthetic_panel():
    rng = np.random.default_rng(73)
    records = []
    for i in range(60):
        aadt = 1000 + i * 500
        for year in [2020, 2021, 2022]:
            count = rng.poisson(.25 * aadt / 10000)
            records.append({"segment_id": str(i), "year": year, "aadt": aadt, "length_miles": 1.,
                "days": 366 if year == 2020 else 365, "fatal_crashes": count, "fatalities": 2 * count,
                "model_eligible": True, "aadt_aligned": False, "vehicle_miles": aadt * 365,
                "lat": 40 + (i // 10) * .3, "lng": -98.5, "route": str(i), "facility_type": "unknown"})
    return pd.DataFrame(records)


def test_eb_uses_period_dispersion_and_separates_fatalities():
    panel = synthetic_panel().iloc[:3].copy()
    panel["fatal_crashes"] = [1, 0, 3]
    panel["fatalities"] = [2, 0, 6]
    panel["days"] = 365.25
    model = {"intercept": 0., "log_aadt_coefficient": 0., "alpha": .5}
    result = screen_network(panel, model).iloc[0]
    # M=3, N=4, alpha=.5 => w=.4, posterior count=.4*3+.6*4=3.6.
    assert result.spf_weight == pytest.approx(.4)
    assert result.eb_annual_fatal_crashes == pytest.approx(1.2)
    assert result.excess_annual_fatal_crashes == pytest.approx(.2)
    assert result.eb_annual_lower95 < result.eb_annual_fatal_crashes < result.eb_annual_upper95
    assert result.observed_fatalities == 8 and result.fatalities_per_crash == 2
    assert 0 < result.probability_above_spf < 1


def test_zero_crashes_have_nonzero_eb_estimate_but_no_fabricated_fatality_ratio():
    panel = synthetic_panel().iloc[:3].copy()
    panel[["fatal_crashes", "fatalities"]] = 0
    result = screen_network(panel, {"intercept": 0., "log_aadt_coefficient": 0., "alpha": .5}).iloc[0]
    assert result.eb_annual_fatal_crashes > 0
    assert np.isnan(result.fatalities_per_crash)
    with pytest.raises(ValueError, match="at least one"):
        fit_spf(panel)


def test_fit_and_disjoint_spatial_temporal_validation():
    panel = synthetic_panel()
    model = fit_spf(panel)
    assert model["alpha"] > 0
    assert np.isfinite(predict_spf(panel, model)).all()
    validation = validate_spf(panel)
    assert validation["temporal"]["holdout_year"] == 2022
    assert validation["temporal"]["rows"] == 60
    assert validation["temporal"]["exposure_only_baseline"]["rows"] == 60
    assert validation["spatial"]["status"] == "evaluated"
    assert sum(f["rows"] for f in validation["spatial"]["folds"]) == len(panel)
    with pytest.raises(ValueError, match="Duplicate"):
        fit_spf(pd.concat([panel, panel.iloc[:1]]))


CMF = {"id": "test-only", "name": "Analytic fixture, not a recommendation", "cmf": .8,
       "source_url": "https://example.org/fixture", "outcome": "fatal_crash", "conditions": "test fixture"}


def appraisal(**kwargs):
    defaults = dict(expected_annual=2., fatalities_per_crash=1.5, countermeasure=CMF,
                    countermeasure_id="test-only", eligible_fraction=1.,
                    implementation_cost=100., annual_maintenance_cost=10., service_life_years=5,
                    discount_rate=0., applicability_confirmed=True, value_statistical_life=1000.)
    defaults.update(kwargs)
    return estimate_countermeasure(**defaults)


def test_economic_analytic_zero_discount_and_harm():
    r = appraisal()
    assert r["annual_fatal_crashes_prevented"] == pytest.approx(.4)
    assert r["annual_statistical_fatalities_prevented"] == pytest.approx(.6)
    assert r["present_value_benefits"] == pytest.approx(3000)
    assert r["present_value_costs"] == 150 and r["benefit_cost_ratio"] == pytest.approx(20)
    assert appraisal(countermeasure={**CMF, "cmf": 1.1})["net_present_value"] < 0
    assert appraisal(implementation_cost=0., annual_maintenance_cost=0.)["benefit_cost_ratio"] is None


def test_economic_applicability_and_finite_inputs():
    with pytest.raises(ValueError, match="Confirm"):
        appraisal(applicability_confirmed=False)
    with pytest.raises(ValueError, match="severity transfer"):
        appraisal(countermeasure={**CMF, "outcome": "fatal_and_injury"})
    assert appraisal(countermeasure={**CMF, "outcome": "fatal_and_injury"},
                     fatal_transfer_assumption_confirmed=True)["fatal_transfer_assumption_confirmed"]
    for kwargs in [{"fatalities_per_crash": 0}, {"expected_annual": float("nan")},
                   {"implementation_cost": -1}, {"service_life_years": 2.5}, {"discount_rate": float("inf")}]:
        with pytest.raises(ValueError):
            appraisal(**kwargs)


def test_catalog_requires_transfer_and_scales_only_eligible_crashes():
    with pytest.raises(ValueError, match="severity transfer"):
        appraisal(countermeasure_id="4737", countermeasure=None)
    result = appraisal(countermeasure_id="4737", countermeasure=None,
                       eligible_fraction=.25, fatal_transfer_assumption_confirmed=True)
    assert result["expected_eligible_annual_fatal_crashes"] == .5
    assert result["annual_fatal_crashes_prevented"] == pytest.approx(.5 * .365)
    assert "winter" in result["applicability_conditions"]
    with pytest.raises(ValueError, match="Unknown"):
        appraisal(countermeasure=None, countermeasure_id="not-a-study")
    with pytest.raises(ValueError, match="fraction"):
        appraisal(eligible_fraction=1.2)


def test_discounting_occurs_at_end_of_each_year():
    result = appraisal(discount_rate=.1)
    factor = sum(1 / 1.1 ** year for year in range(1, 6))
    assert result["present_value_benefits"] == pytest.approx(600 * factor)
    assert result["present_value_costs"] == pytest.approx(100 + 10 * factor)


def test_reject_invalid_inputs_before_matching_or_modeling():
    with pytest.raises(ValueError, match="unique"):
        match_crashes(pd.concat([crashes(), crashes().iloc[:1]]), roads())
    with pytest.raises(ValueError, match="years"):
        build_segment_years(crashes(), roads(), [])
    with pytest.raises(ValueError, match="outside"):
        build_segment_years(crashes(), roads(), [2021])
    wrong = crashes().copy()
    wrong["outcome"] = "injury"
    with pytest.raises(ValueError, match="fatal-crash"):
        build_segment_years(wrong, roads(), [2020])
    panel = synthetic_panel()
    panel["fatal_crashes"] = -.5
    with pytest.raises(ValueError, match="Invalid"):
        fit_spf(panel)
    with pytest.raises(ValueError, match="dispersion"):
        screen_network(synthetic_panel(), {"alpha": 0})


def test_validation_reports_insufficient_data_instead_of_false_scores():
    panel = synthetic_panel().iloc[:3]
    result = validate_spf(panel)
    assert result["temporal"]["status"] == "not_evaluable"
    assert result["spatial"]["status"] == "unavailable"
    one_year = synthetic_panel().query("year == 2020").copy()
    assert validate_spf(one_year)["temporal"]["status"] == "insufficient_years"

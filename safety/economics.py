"""Transparent, user-confirmed countermeasure appraisal, not a causal forecast.

Counts represent fatal crashes; VSL values a statistical fatality. The separate
fatalities-per-crash assumption is therefore mandatory. No generic treatment is
assumed applicable to every road or severity group.
"""
import math

USDOT_VSL = {
    "value": 14_200_000.0,
    "dollar_year": 2025,
    "source_url": "https://www.transportation.gov/office-policy/transportation-policy/revised-departmental-guidance-on-valuation-of-a-statistical-life-in-economic-analysis",
    "interpretation": "USDOT value of a statistical life; per statistical fatality, not per crash",
}

CATALOG = {
    "4737": {
        "id": "4737", "name": "Widen edgelines from 4 to 6 inches", "cmf": 0.635,
        "standard_error": 0.052,
        "source_url": "https://cmfclearinghouse.fhwa.dot.gov/detail.php?facid=4737",
        "outcome": "fatal_and_injury_KABC", "study": "Park et al. 2012; Kansas 2001–2007",
        "conditions": "Rural two-lane roads; widen edgelines from 4 to 6 inches. "
                      "Fatal and injury crashes (KABC); excludes intersection/interchange and winter-month crashes. "
                      "Requires verified existing width and road eligibility, an explicit eligible-crash fraction, "
                      "and a separate assumption transferring the combined fatal/injury CMF to fatal crashes.",
    }
}


def estimate_countermeasure(expected_annual, countermeasure_id, implementation_cost,
                            annual_maintenance_cost, service_life_years, fatalities_per_crash,
                            eligible_fraction, discount_rate=0.03, applicability_confirmed=False,
                            fatal_transfer_assumption_confirmed=False,
                            value_statistical_life=USDOT_VSL["value"],
                            vsl_dollar_year=USDOT_VSL["dollar_year"], countermeasure=None):
    """Appraise one sourced CMF using constant real annual benefits/costs.

    ``countermeasure_id`` selects CATALOG; custom ``countermeasure`` dictionaries
    need id, name, cmf, source_url, outcome, conditions. ``expected_annual`` is the
    baseline annual fatal-crash frequency; eligible_fraction selects only crashes
    matching the CMF study (not a fraction inferred automatically from FARS).
    CMF effects for combined injury/fatal outcomes require an additional explicit
    severity-transfer assumption; an all-crash CMF never silently becomes a
    fatal-crash CMF. User-entered costs must use the VSL dollar year. No stacking,
    growth, residual value or causal certainty is assumed. CMF >1 is allowed and
    yields negative benefits; zero costs produce an undefined (None) BCR.
    """
    if countermeasure is None:
        if str(countermeasure_id) not in CATALOG:
            raise ValueError("Unknown countermeasure ID")
        countermeasure = CATALOG[str(countermeasure_id)]
    required = {"id", "name", "cmf", "source_url", "outcome", "conditions"}
    if required - set(countermeasure) or not all(countermeasure[k] for k in required - {"cmf"}):
        raise ValueError("A sourced CMF and documented applicability conditions are required")
    if not str(countermeasure["source_url"]).startswith("https://"):
        raise ValueError("CMF requires an HTTPS source URL")
    if applicability_confirmed is not True:
        raise ValueError("Confirm that the study's facility and treatment conditions apply")
    if countermeasure["outcome"] != "fatal_crash" and fatal_transfer_assumption_confirmed is not True:
        raise ValueError("CMF is not fatal-crash-specific; explicitly confirm severity transfer assumption")
    values = {"expected_annual_fatal_crashes": expected_annual, "eligible_fraction": eligible_fraction,
              "fatalities_per_crash": fatalities_per_crash, "cmf": countermeasure["cmf"],
              "implementation_cost": implementation_cost, "annual_maintenance_cost": annual_maintenance_cost,
              "discount_rate": discount_rate, "value_statistical_life": value_statistical_life,
              "service_life_years": service_life_years}
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite nonnegative number")
    if fatalities_per_crash < 1 or value_statistical_life <= 0:
        raise ValueError("Fatal crashes require >=1 fatality/crash and a positive VSL")
    if eligible_fraction > 1:
        raise ValueError("Eligible fraction must be between zero and one")
    if int(service_life_years) != service_life_years or not 1 <= service_life_years <= 100:
        raise ValueError("Service life must be 1–100 whole years")
    if discount_rate > 1 or not isinstance(vsl_dollar_year, int) or not 2000 <= vsl_dollar_year <= 2100:
        raise ValueError("Use a fractional real discount rate <=1 and a valid dollar year")
    horizon = int(service_life_years)
    annuity = horizon if discount_rate == 0 else -math.expm1(-horizon * math.log1p(discount_rate)) / discount_rate
    annual_crashes_prevented = expected_annual * eligible_fraction * (1 - countermeasure["cmf"])
    annual_fatalities_prevented = annual_crashes_prevented * fatalities_per_crash
    annual_benefit = annual_fatalities_prevented * value_statistical_life
    pv_benefit = annual_benefit * annuity
    pv_cost = implementation_cost + annual_maintenance_cost * annuity
    return {"countermeasure_id": countermeasure["id"], "countermeasure_name": countermeasure["name"],
            "cmf": countermeasure["cmf"], "cmf_outcome": countermeasure["outcome"],
            "cmf_source_url": countermeasure["source_url"], "applicability_conditions": countermeasure["conditions"],
            "applicability_confirmed": True,
            "fatal_transfer_assumption_confirmed": bool(fatal_transfer_assumption_confirmed),
            "expected_annual_fatal_crashes": expected_annual, "eligible_fraction": eligible_fraction,
            "expected_eligible_annual_fatal_crashes": expected_annual * eligible_fraction,
            "fatalities_per_crash": fatalities_per_crash,
            "annual_fatal_crashes_prevented": annual_crashes_prevented,
            "annual_statistical_fatalities_prevented": annual_fatalities_prevented,
            "annual_safety_benefit": annual_benefit, "present_value_benefits": pv_benefit,
            "present_value_costs": pv_cost, "net_present_value": pv_benefit - pv_cost,
            "benefit_cost_ratio": pv_benefit / pv_cost if pv_cost else None,
            "implementation_cost": implementation_cost, "annual_maintenance_cost": annual_maintenance_cost,
            "service_life_years": horizon, "discount_rate": discount_rate,
            "vsl": value_statistical_life, "dollar_year": vsl_dollar_year,
            "vsl_source_url": USDOT_VSL["source_url"],
            "vsl_is_usdot_default": value_statistical_life == USDOT_VSL["value"] and vsl_dollar_year == USDOT_VSL["dollar_year"],
            "limitations": ["Scenario appraisal, not a guaranteed causal reduction or engineering recommendation",
                            "Costs and benefits must use the stated constant-dollar year",
                            "No injury/property-damage benefits; no CMF stacking; no residual value",
                            "Baseline, CMF, severity transfer and fatalities-per-crash uncertainty are not quantified"]}

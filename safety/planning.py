"""Reproducible agency scenarios, not engineering or grant certification.

Appraisal baselines come only from the active snapshot. Agency cash and societal
VSL valuations stay separate; submitted workflow/outcome data remain unverified.
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator

from safety.economics import CATALOG, estimate_countermeasure


class PlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
Money = Annotated[float, Field(ge=0, le=1e10)]
Note = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


class Candidate(PlanningInput):
    candidate_id: Identifier
    segment_id: Identifier
    countermeasure_id: Identifier
    implementation_cost: float = Field(gt=0, le=1e10)
    annual_maintenance_cost: Money = 0
    service_life_years: int = Field(default=10, ge=1, le=100)
    discount_rate: float = Field(default=0.03, ge=0, le=0.25)
    fatalities_per_crash: float = Field(ge=1, le=100)
    eligible_fraction: float = Field(gt=0, le=1)
    applicability_confirmed: bool = False
    fatal_transfer_assumption_confirmed: bool = False


class PortfolioRequest(PlanningInput):
    budget: Money
    dollar_year: Literal[2025] = 2025
    candidates: list[Candidate] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def consistent_appraisal(self):
        if len({c.candidate_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Candidate IDs must be unique")
        if len({(c.service_life_years, c.discount_rate) for c in self.candidates}) > 1:
            raise ValueError("Use the same appraisal horizon and discount rate for every candidate")
        for value in [self.budget] + [c.implementation_cost for c in self.candidates]:
            if Decimal(str(value)) * 100 != (Decimal(str(value)) * 100).to_integral_value():
                raise ValueError("Budget and implementation costs require at most two decimal places")
        return self


class WorkflowRequest(PlanningInput):
    annual_cases: int = Field(ge=0, le=1000000)
    before_hours_per_case: float = Field(ge=0, le=10000)
    after_hours_per_case: float = Field(ge=0, le=10000)
    hourly_cost: float = Field(gt=0, le=100000)
    annual_software_cost: Money
    annual_other_cost: Money = 0
    first_year_setup_cost: Money = 0
    cash_realization_fraction: float = Field(default=0, ge=0, le=1)
    dollar_year: int = Field(default=2025, ge=2000, le=2100)
    source_note: Note = "User-entered scenario; not independently measured"


class OutcomePeriod(PlanningInput):
    crashes: int = Field(ge=0, le=10000000)
    exposure_vmt: float = Field(ge=1, le=1e15)
    start_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None
    end_date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None

    @model_validator(mode="after")
    def dates(self):
        from datetime import date
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Provide both period dates or neither")
        if self.start_date is not None:
            start, end = date.fromisoformat(self.start_date), date.fromisoformat(self.end_date)
            if end < start:
                raise ValueError("Period end precedes its start")
        return self


class OutcomesRequest(PlanningInput):
    before: OutcomePeriod
    after: OutcomePeriod
    comparison_before: OutcomePeriod | None = None
    comparison_after: OutcomePeriod | None = None
    outcome: Literal["fatal_crash", "injury_crash", "all_crash"] = "fatal_crash"
    source_note: Note

    @model_validator(mode="after")
    def comparison(self):
        if (self.comparison_before is None) != (self.comparison_after is None):
            raise ValueError("Both comparison periods are required")
        for before, after in [(self.before, self.after), (self.comparison_before, self.comparison_after)]:
            if before and after and before.end_date and after.start_date and before.end_date >= after.start_date:
                raise ValueError("Before and after periods must not overlap")
        if self.comparison_before:
            for treated, comparison in [(self.before, self.comparison_before), (self.after, self.comparison_after)]:
                if (treated.start_date, treated.end_date) != (comparison.start_date, comparison.end_date):
                    raise ValueError("Dated comparison periods must match the treatment periods")
        return self


class EvidenceRequest(PlanningInput):
    project_name: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
    agency_name: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
    project_description: Note
    segment_ids: list[Identifier] = Field(min_length=1, max_length=100)
    assumptions: list[Note] = Field(default_factory=list, max_length=30)
    supporting_sources: list[Annotated[str, Field(max_length=1000, pattern=r"^https://\S+$")]] = Field(default_factory=list, max_length=30)
    portfolio: PortfolioRequest | None = None
    workflow: WorkflowRequest | None = None
    outcomes: OutcomesRequest | None = None

    @model_validator(mode="after")
    def project_scope(self):
        if len(set(self.segment_ids)) != len(self.segment_ids):
            raise ValueError("Project segment IDs must be unique")
        if self.portfolio and any(c.segment_id not in self.segment_ids for c in self.portfolio.candidates):
            raise ValueError("Portfolio candidates must be included in the project segment IDs")
        return self


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _snapshot_context(snapshot):
    return {
        "snapshot_built_at": snapshot["built_at"], "snapshot_sha256": _sha(snapshot),
        "hash_method": "SHA-256 of canonical JSON (sorted keys, compact separators, UTF-8)",
        "data_mode": snapshot.get("data_mode", "official_source_experimental"),
        "scope": snapshot.get("scope"), "years": snapshot.get("years", []),
        "provenance": snapshot.get("provenance", {}),
        "commercial_ready": snapshot.get("commercial_ready", False) is True,
        "limitations": snapshot.get("limitations", []),
    }


def _exact_selection(candidates, budget):
    """Exact multiple-choice knapsack by meet in the middle (<=30 candidates).

    Groups prevent stacking on a segment. Halves balance combination counts;
    one enumerated half is Pareto-pruned. Budget feasibility uses exact cents.
    """
    grouped = defaultdict(list)
    for index, item in enumerate(candidates):
        if item["appraisal"]["net_present_value"] > 0:
            grouped[item["segment_id"]].append(index)
    halves, sizes = [[], []], [1, 1]
    for group in sorted(grouped.values(), key=lambda g: (-len(g), g[0])):
        target = 0 if sizes[0] <= sizes[1] else 1
        halves[target].append(group)
        sizes[target] *= len(group) + 1
    cents = [int(Decimal(str(c["appraisal"]["implementation_cost"])) * 100) for c in candidates]
    budget_cents = int(Decimal(str(budget)) * 100)

    def combinations(groups):
        states = [(0, 0.0, ())]
        for group in groups:
            following = list(states)
            for cost, value, picked in states:
                for index in group:
                    new_cost = cost + cents[index]
                    if new_cost <= budget_cents:
                        following.append((new_cost, value + candidates[index]["appraisal"]["net_present_value"], picked + (index,)))
            states = following
        return states

    left, right = combinations(halves[0]), combinations(halves[1])
    frontier, best = [], -math.inf
    for state in sorted(right, key=lambda s: (s[0], -s[1], s[2])):
        if state[1] > best:
            frontier.append(state)
            best = state[1]
    costs = [s[0] for s in frontier]
    winner = (0, 0.0, ())
    for cost, value, picked in left:
        other = frontier[bisect_right(costs, budget_cents - cost) - 1]
        proposal = (cost + other[0], value + other[1], picked + other[2])
        if proposal[1] > winner[1] or (proposal[1] == winner[1] and proposal[0] < winner[0]):
            winner = proposal
    return sorted(winner[2]), len(left) + len(right)


def _cmf_sensitivity(picks):
    """Change the sourced CMF only; this is not a portfolio confidence interval."""
    rows, low_benefits, high_benefits = [], [], []
    unavailable = []
    for item in picks:
        appraisal = item["appraisal"]
        cmf = CATALOG.get(str(appraisal["countermeasure_id"]), {})
        standard_error = cmf.get("standard_error")
        if not isinstance(standard_error, (float, int)) or not math.isfinite(standard_error) or standard_error < 0:
            unavailable.append(item["candidate_id"])
            continue
        low_cmf = max(0, appraisal["cmf"] - 1.96 * standard_error)
        high_cmf = appraisal["cmf"] + 1.96 * standard_error
        # Re-evaluate rather than divide by (1-CMF), which may be zero.
        inputs = {k: appraisal[k] for k in ["implementation_cost", "annual_maintenance_cost", "service_life_years",
                                           "fatalities_per_crash", "eligible_fraction", "discount_rate",
                                           "applicability_confirmed", "fatal_transfer_assumption_confirmed"]}
        lower = estimate_countermeasure(expected_annual=appraisal["expected_annual_fatal_crashes"],
                                        countermeasure_id=cmf["id"], countermeasure={**cmf, "cmf": high_cmf}, **inputs)
        upper = estimate_countermeasure(expected_annual=appraisal["expected_annual_fatal_crashes"],
                                        countermeasure_id=cmf["id"], countermeasure={**cmf, "cmf": low_cmf}, **inputs)
        low_benefits.append(lower["present_value_benefits"])
        high_benefits.append(upper["present_value_benefits"])
        rows.append({"candidate_id": item["candidate_id"], "cmf_source_url": cmf["source_url"],
                     "published_cmf_standard_error": standard_error, "cmf_scenario_low": low_cmf,
                     "cmf_scenario_high": high_cmf, "lower_benefit_present_value": lower["present_value_benefits"],
                     "upper_benefit_present_value": upper["present_value_benefits"]})
    cost = math.fsum(p["appraisal"]["present_value_costs"] for p in picks)
    return {
        "method": "Published CMF plus/minus 1.96 standard errors, lower CMF truncated at zero",
        "status": "incomplete" if unavailable else "computed", "candidates": rows,
        "unavailable_candidate_ids": unavailable,
        "same_selected_portfolio": True, "selection_reoptimized": False,
        "societal_benefits_present_value_lower": None if unavailable else math.fsum(low_benefits),
        "societal_benefits_present_value_upper": None if unavailable else math.fsum(high_benefits),
        "societal_npv_lower": None if unavailable else math.fsum(low_benefits) - cost,
        "societal_npv_upper": None if unavailable else math.fsum(high_benefits) - cost,
        "limitations": [
            "Scenario envelope only, not a joint 95% confidence interval or probability of return.",
            "Moves each selected treatment's CMF to the same less/more favorable bound; does not assume independent CMF errors.",
            "Excludes baseline, severity-transfer, road-matching, exposure, applicability and cost uncertainty.",
            "The portfolio is not reoptimized under these scenarios; a different selection may be preferred.",
        ],
    }


def appraise_portfolio(request: PortfolioRequest, snapshot):
    roads = {r["segment_id"]: r for r in snapshot["segments"]}
    candidates = []
    for candidate in request.candidates:
        if candidate.segment_id not in roads:
            raise HTTPException(404, f"Road segment not found: {candidate.segment_id}")
        try:
            inputs = candidate.model_dump(exclude={"candidate_id", "segment_id"})
            appraisal = estimate_countermeasure(expected_annual=roads[candidate.segment_id]["expected_annual"], **inputs)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if any(isinstance(v, float) and not math.isfinite(v) for v in appraisal.values()):
            raise HTTPException(503, "Snapshot baseline is outside the supported appraisal range")
        candidates.append({"candidate_id": candidate.candidate_id, "segment_id": candidate.segment_id,
                           "route": roads[candidate.segment_id].get("route"), "appraisal": appraisal})
    selected, states = _exact_selection(candidates, request.budget)
    picks = [candidates[i] for i in selected]
    fields = ["implementation_cost", "present_value_costs", "present_value_benefits", "net_present_value",
              "annual_fatal_crashes_prevented", "annual_statistical_fatalities_prevented"]
    totals = {key: math.fsum(c["appraisal"][key] for c in picks) for key in fields}
    totals["unallocated_implementation_budget"] = float(Decimal(str(request.budget)) - sum(
        (Decimal(str(c["appraisal"]["implementation_cost"])) for c in picks), Decimal(0)))
    totals["societal_safety_benefits_present_value"] = totals.pop("present_value_benefits")
    totals["agency_cash_savings"] = None
    totals["benefit_cost_ratio"] = (totals["societal_safety_benefits_present_value"] / totals["present_value_costs"]
                                    if totals["present_value_costs"] else None)
    return {
        "schema_version": 1, "kind": "conditional_treatment_portfolio", **_snapshot_context(snapshot),
        "request_sha256": _sha(request.model_dump()), "budget": request.budget, "dollar_year": request.dollar_year,
        "candidates": candidates, "selected_candidate_ids": [c["candidate_id"] for c in picks], "totals": totals,
        "cmf_sensitivity": _cmf_sensitivity(picks),
        "solver": {"method": "exact_multiple_choice_meet_in_the_middle", "optimal_for_supplied_scenarios": True,
                   "enumerated_states": states, "objective": "maximum societal net present value",
                   "budget_basis": "upfront implementation costs only; maintenance included in NPV",
                   "constraints": ["At most one candidate per road segment", "No negative-NPV selections",
                                   "Common horizon and discount rate; constant 2025 USD"]},
        "interpretation": [
            "VSL benefits are societal valuations, not cash available to an agency or revenue.",
            "No emergency-response, property-damage, travel-time or fiscal savings are invented or added to VSL.",
            "Benefits assume separate segment crash populations; spillovers, adjacent-road overlaps and interactions require engineering review.",
            "Input costs, eligible fractions and confirmations are user assumptions, not verified project evidence.",
            "Optimality concerns only the supplied scenarios, not the best real-world engineering intervention.",
        ],
    }


def _break_even(cost, unit_value):
    if unit_value <= 0:
        return None
    ratio = cost / unit_value
    return math.ceil(ratio) if math.isfinite(ratio) else None


def compare_workflow(request: WorkflowRequest):
    saved_per_case = request.before_hours_per_case - request.after_hours_per_case
    hours = request.annual_cases * saved_per_case
    capacity_value = hours * request.hourly_cost
    cash_savings = max(0, capacity_value) * request.cash_realization_fraction
    annual_cost = request.annual_software_cost + request.annual_other_cost
    unit_value = saved_per_case * request.hourly_cost
    cash_unit = max(0, unit_value) * request.cash_realization_fraction
    return {
        "schema_version": 1, "kind": "user_supplied_workflow_scenario", "inputs": request.model_dump(),
        "annual_hours_released": hours, "annual_staff_capacity_value": capacity_value,
        "annual_cash_savings_scenario": cash_savings, "annual_software_and_other_cost": annual_cost,
        "annual_net_capacity_value": capacity_value - annual_cost,
        "first_year_net_capacity_value": capacity_value - annual_cost - request.first_year_setup_cost,
        "annual_net_cash_scenario": cash_savings - annual_cost,
        "first_year_net_cash_scenario": cash_savings - annual_cost - request.first_year_setup_cost,
        "annual_capacity_break_even_cases": _break_even(annual_cost, unit_value),
        "annual_cash_break_even_cases": _break_even(annual_cost, cash_unit),
        "first_year_capacity_break_even_cases": _break_even(annual_cost + request.first_year_setup_cost, unit_value),
        "annual_software_price_ceiling_capacity": capacity_value - request.annual_other_cost,
        "annual_software_price_ceiling_cash": cash_savings - request.annual_other_cost,
        "limitations": [
            "User-entered estimates; no agency time study, payroll reduction or realized savings is asserted.",
            "Staff capacity value is not budget cash savings; realization fraction requires an agency-supported staffing or avoided-cost plan.",
            "Capacity value and cash savings describe overlapping benefits and must not be added together.",
            "If workload increases, additional staffing/overtime costs require separate review; negative hours indicate an operational loss.",
            "No crash or societal safety benefit is included in this workflow comparison.",
        ],
    }


def _period_summary(period):
    from scipy.stats import chi2
    count = period.crashes
    scale = 100000000 / period.exposure_vmt
    interval = [0.0 if count == 0 else float(chi2.ppf(.025, 2 * count) / 2) * scale,
                float(chi2.ppf(.975, 2 * (count + 1)) / 2) * scale]
    return {**period.model_dump(), "rate_per_100m_vmt": count * scale,
            "rate_interval95": interval, "interval_method": "exact Poisson count interval scaled by fixed exposure"}


def _rate_comparison(before, after):
    b, a = before.crashes / before.exposure_vmt, after.crashes / after.exposure_vmt
    ratio = a / b if b else None
    interval = None
    if before.crashes > 0 and after.crashes > 0:
        se = math.sqrt(1 / before.crashes + 1 / after.crashes)
        interval = [math.exp(math.log(ratio) - 1.96 * se), math.exp(math.log(ratio) + 1.96 * se)]
    return {"rate_ratio_after_to_before": ratio,
            "rate_change_percent": (ratio - 1) * 100 if ratio is not None else None,
            "rate_difference_per_100m_vmt": (a - b) * 1e8,
            "rate_ratio_interval95": interval,
            "ratio_interval_method": "approximate independent Poisson log-rate-ratio; omitted when a count is zero",
            "expected_after_count_at_before_rate": b * after.exposure_vmt,
            "observed_minus_before_rate_expected_after": after.crashes - b * after.exposure_vmt}


def compare_outcomes(request: OutcomesRequest):
    result = {
        "schema_version": 1, "kind": "descriptive_before_after", "outcome": request.outcome,
        "source_note": request.source_note, "input_verification": "user_submitted_not_independently_verified",
        "before": _period_summary(request.before), "after": _period_summary(request.after),
        **_rate_comparison(request.before, request.after), "comparison_adjusted": None,
        "causal_effect_established": False,
        "limitations": [
            "Descriptive association, not attribution of a change to a treatment; no prevented-crash claim.",
            "Intervals assume independent Poisson counts and fixed, accurately measured VMT; overdispersion, exposure error and matching uncertainty are excluded.",
            "Selection of high-crash sites can produce regression to the mean; this is not an Empirical Bayes before/after evaluation.",
            "Exposure, crash definitions, reporting coverage and geography must be comparable across periods.",
            "A comparison group does not establish exchangeability, parallel trends or absence of confounding.",
        ],
    }
    if not request.before.start_date or not request.after.start_date:
        result["limitations"].append("Period dates were not supplied; chronology and non-overlap cannot be checked.")
    if request.comparison_before is not None:
        comparison = _rate_comparison(request.comparison_before, request.comparison_after)
        treatment_rr = result["rate_ratio_after_to_before"]
        comparison_rr = comparison["rate_ratio_after_to_before"]
        ratio_of_ratios = treatment_rr / comparison_rr if treatment_rr is not None and comparison_rr else None
        counts = [p.crashes for p in [request.before, request.after, request.comparison_before, request.comparison_after]]
        interval = None
        if all(counts):
            se = math.sqrt(sum(1 / c for c in counts))
            interval = [math.exp(math.log(ratio_of_ratios) - 1.96 * se), math.exp(math.log(ratio_of_ratios) + 1.96 * se)]
        result["comparison_adjusted"] = {
            "before": _period_summary(request.comparison_before), "after": _period_summary(request.comparison_after),
            "comparison_rate_ratio": comparison_rr, "ratio_of_rate_ratios": ratio_of_ratios,
            "relative_change_percent": (ratio_of_ratios - 1) * 100 if ratio_of_ratios is not None else None,
            "ratio_of_rate_ratios_interval95": interval,
            "interval_method": "approximate independent Poisson log ratio-of-ratios; omitted when any count is zero",
        }
    return result


def build_evidence(request: EvidenceRequest, snapshot):
    roads = {r["segment_id"]: r for r in snapshot["segments"]}
    missing = [s for s in request.segment_ids if s not in roads]
    if missing:
        raise HTTPException(404, f"Road segment not found: {missing[0]}")
    portfolio = appraise_portfolio(request.portfolio, snapshot) if request.portfolio else None
    selected = [roads[s] for s in request.segment_ids]
    evidence = {
        "schema_version": 1, "kind": "project_evidence_workbook", "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": request.model_dump(exclude={"portfolio", "workflow", "outcomes"}),
        "snapshot": _snapshot_context(snapshot), "quality": snapshot.get("quality", {}),
        "segments": selected, "segment_evidence_sha256": _sha(selected), "request_sha256": _sha(request.model_dump()),
        "portfolio": portfolio,
        "workflow": compare_workflow(request.workflow) if request.workflow else None,
        "outcomes": compare_outcomes(request.outcomes) if request.outcomes else None,
        "financial_interpretation": {
            "societal_benefits": "Only conditional VSL-based safety valuation in the portfolio; not agency revenue or cash savings.",
            "agency_operating_benefits": "Workflow staff capacity and explicitly assumed cash realization are separate overlapping views, not additive benefits.",
            "costs": "Implementation, maintenance and software costs remain explicit; dollar years must be reconciled before combined appraisal.",
            "aggregate_cross_module_benefit": None,
        },
        "missing_requirements": [
            "Agency authorization and named engineering reviewer; agency_name is supplied by the user and does not imply endorsement.",
            "Commercial data-use and redistribution rights confirmation for the proposed delivery.",
            "Location and crash-linkage audit, historical traffic exposure and facility eligibility verification.",
            "Site investigation, treatment design, defensible cost estimates and uncertainty/sensitivity analysis.",
            "Independent appraisal of treatment applicability and fatal-outcome CMF transfer.",
            "Program-specific eligibility, current funding notice, match commitments and application requirements review.",
            "Community engagement, equity/accessibility analysis, environmental review and procurement requirements as applicable.",
            "Agency-approved baseline, outcome definitions, evaluation periods and comparison protocol.",
            "Measured analyst workflow times and evidence of actual cash realization before claiming budget savings.",
        ],
        "certification": {"grant_eligible": None, "grant_compliant": None, "engineering_approved": False,
                          "agency_endorsed": False, "submission_ready": False},
        "limitations": [
            "Evidence organization only; not a grant application, compliance certification or funding recommendation.",
            "Caller notes, source URLs, costs and measurements are not independently verified; no external URLs are fetched.",
            "This workbook does not establish treatment effectiveness or realized government savings.",
        ],
    }
    report = [
        "GeoCrash project evidence workbook",
        f"Project: {request.project_name}",
        f"Agency name (user supplied, not an endorsement): {request.agency_name}",
        f"Description: {request.project_description}",
        f"Snapshot: {snapshot['built_at']}",
        f"Snapshot canonical SHA-256: {evidence['snapshot']['snapshot_sha256']}",
        f"Request canonical SHA-256: {evidence['request_sha256']}",
        f"Data mode: {evidence['snapshot']['data_mode']}",
        "Scope: Historical fatal-crash screening; not all-crash risk or a certified engineering design.",
        "Project road segments:",
    ]
    for road in selected:
        report.append(f"  {road['segment_id']}: expected annual fatal crashes {road['expected_annual']:.6g}; "
                      f"route {road.get('route', 'not supplied')}; exposure {road.get('exposure_status', 'review required')}")
    if portfolio:
        totals = portfolio["totals"]
        report.extend([
            "Treatment scenario (constant 2025 USD):",
            f"  Selected candidates: {', '.join(portfolio['selected_candidate_ids']) or 'None'}",
            f"  Upfront implementation cost: {totals['implementation_cost']:.2f}",
            f"  Life-cycle cost present value: {totals['present_value_costs']:.2f}",
            f"  Conditional societal safety benefit present value: {totals['societal_safety_benefits_present_value']:.2f}",
            f"  Societal net present value: {totals['net_present_value']:.2f}",
            "  Agency cash savings: not established. Societal VSL valuation is not budget cash.",
            "  CMF sensitivity is a scenario envelope, not a joint confidence interval.",
        ])
    if evidence["workflow"]:
        work = evidence["workflow"]
        report.extend([
            f"Workflow scenario ({request.workflow.dollar_year} USD, unverified user inputs):",
            f"  Annual hours released: {work['annual_hours_released']:.2f}",
            f"  Annual staff capacity value: {work['annual_staff_capacity_value']:.2f}",
            f"  Assumed annual cash realization: {work['annual_cash_savings_scenario']:.2f}",
            "  Capacity value and cash realization overlap and must not be added.",
        ])
    if evidence["outcomes"]:
        report.append("Outcome comparison: descriptive user-supplied records; no causal treatment effect established.")
    report.extend(["Unresolved review requirements:"] + [f"  - {item}" for item in evidence["missing_requirements"]])
    report.extend(["Snapshot limitations:"] + [f"  - {item}" for item in snapshot.get("limitations", [])])
    report.append("Not a grant application, funding eligibility determination or engineering approval.")
    evidence["report_text"] = "\n".join(report)
    evidence["artifact_sha256"] = _sha(evidence)
    evidence["artifact_hash_excludes"] = ["artifact_sha256", "artifact_hash_excludes"]
    return evidence


class PlanningRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                # FastAPI otherwise echoes inf/nan inputs into strict JSON and
                # converts a validation error to HTTP 500. Never echo user data.
                return JSONResponse(status_code=422, content={"detail": [
                    {k: error[k] for k in ("type", "loc", "msg") if k in error}
                    for error in exc.errors()
                ]})
        return handler


def register_planning_routes(app, required_snapshot):
    """Register on the safety app; outer serving stack supplies auth/rate limits."""
    router = APIRouter(route_class=PlanningRoute)
    @router.post("/api/safety/planning/portfolio")
    def portfolio(request: PortfolioRequest):
        return appraise_portfolio(request, required_snapshot())

    @router.post("/api/safety/planning/workflow")
    def workflow(request: WorkflowRequest):
        return compare_workflow(request)

    @router.post("/api/safety/planning/outcomes")
    def outcomes(request: OutcomesRequest):
        return compare_outcomes(request)

    @router.post("/api/safety/planning/evidence")
    def evidence(request: EvidenceRequest):
        from fastapi.responses import JSONResponse
        return JSONResponse(build_evidence(request, required_snapshot()), headers={
            "Content-Disposition": 'attachment; filename="geocrash-project-evidence.json"', "Cache-Control": "no-store",
        })

    # Keep concrete APIRoutes visible to the public app's safety-only allowlist.
    app.router.routes.extend(router.routes)

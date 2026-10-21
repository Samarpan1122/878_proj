"""Decision arithmetic and boundary tests; fixtures are explicitly synthetic."""
import hashlib
import itertools
import json
import random

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from safety.planning import _exact_selection, register_planning_routes


@pytest.fixture
def snapshot():
    return {'schema_version': 1, 'built_at': '2026-09-30T00:00:00Z',
            'data_mode': 'synthetic', 'commercial_ready': False, 'years': [2024],
            'provenance': {'roads_sha256': 'test-roads', 'crashes_sha256': 'test-crashes'},
            'limitations': ['Synthetic arithmetic fixture'],
            'segments': [{'segment_id': s, 'expected_annual': frequency, 'route': s}
                         for s, frequency in [('A', .2), ('B', .1), ('C', 0)]]}


@pytest.fixture
def client(snapshot):
    app = FastAPI()
    register_planning_routes(app, lambda: snapshot)
    return TestClient(app)


def candidate(cid='A1', sid='A', **kwargs):
    return {'candidate_id': cid, 'segment_id': sid, 'countermeasure_id': '4737',
            'implementation_cost': 10000, 'annual_maintenance_cost': 100,
            'service_life_years': 10, 'discount_rate': 0,
            'fatalities_per_crash': 1, 'eligible_fraction': .5,
            'applicability_confirmed': True, 'fatal_transfer_assumption_confirmed': True, **kwargs}


def workflow(**kwargs):
    return {'annual_cases': 100, 'before_hours_per_case': 4, 'after_hours_per_case': 1,
            'hourly_cost': 50, 'annual_software_cost': 5000, 'annual_other_cost': 1000,
            'first_year_setup_cost': 2000, **kwargs}


def outcome(**kwargs):
    return {'before': {'crashes': 20, 'exposure_vmt': 100000000},
            'after': {'crashes': 10, 'exposure_vmt': 200000000},
            'source_note': 'Synthetic arithmetic test', **kwargs}


def evidence(**kwargs):
    return {'project_name': 'Test project', 'agency_name': 'Example agency, no endorsement',
            'project_description': 'Test evidence export', 'segment_ids': ['A'], **kwargs}


def test_portfolio_arithmetic_separates_societal_from_fiscal(client):
    response = client.post('/api/safety/planning/portfolio', json={'budget': 10000, 'candidates': [candidate()]})
    assert response.status_code == 200, response.text
    result = response.json()
    totals = result['totals']
    annual_crashes = .2 * .5 * (1 - .635)
    assert totals['annual_fatal_crashes_prevented'] == pytest.approx(annual_crashes)
    assert totals['societal_safety_benefits_present_value'] == pytest.approx(annual_crashes * 14200000 * 10)
    assert totals['present_value_costs'] == 11000
    assert totals['agency_cash_savings'] is None
    assert totals['unallocated_implementation_budget'] == 0
    assert result['selected_candidate_ids'] == ['A1']
    assert result['data_mode'] == 'synthetic' and not result['commercial_ready']


def test_portfolio_no_stacking_or_negative_npv(client):
    items = [candidate('expensive', implementation_cost=12000), candidate('cheaper'), candidate('no-benefit', 'C')]
    result = client.post('/api/safety/planning/portfolio', json={'budget': 100000, 'candidates': items}).json()
    assert result['selected_candidate_ids'] == ['cheaper']
    assert result['totals']['implementation_cost'] == 10000
    assert result['solver']['optimal_for_supplied_scenarios']


def test_zero_budget_selects_nothing(client):
    result = client.post('/api/safety/planning/portfolio', json={'budget': 0, 'candidates': [candidate()]}).json()
    assert result['selected_candidate_ids'] == []
    assert result['totals']['benefit_cost_ratio'] is None


def test_exact_selection_beats_greedy_and_respects_cents():
    # Highest value/cost selects A alone; exact optimum is B+C.
    items = [{'segment_id': s, 'appraisal': {'implementation_cost': c, 'net_present_value': v}}
             for s, c, v in [('A', 60, 120), ('B', 50, 95), ('C', 50, 95)]]
    assert _exact_selection(items, 100)[0] == [1, 2]
    items = [{'segment_id': s, 'appraisal': {'implementation_cost': .1, 'net_present_value': 1}} for s in ['A', 'B', 'C']]
    assert _exact_selection(items, .3)[0] == [0, 1, 2]
    assert len(_exact_selection(items, .29)[0]) == 2


def test_exact_solver_matches_exhaustive_search_with_exclusions():
    rng = random.Random(781)
    for _ in range(40):
        items = [{'segment_id': str(rng.randrange(4)),
                  'appraisal': {'implementation_cost': rng.randint(1, 20), 'net_present_value': rng.randint(-10, 100)}}
                 for _ in range(9)]
        budget = rng.randint(1, 70)
        actual, _ = _exact_selection(items, budget)
        best = 0
        for mask in itertools.product([False, True], repeat=len(items)):
            chosen = [c for c, use in zip(items, mask) if use]
            if len({c['segment_id'] for c in chosen}) != len(chosen):
                continue
            if sum(c['appraisal']['implementation_cost'] for c in chosen) <= budget:
                best = max(best, sum(c['appraisal']['net_present_value'] for c in chosen))
        assert sum(items[i]['appraisal']['net_present_value'] for i in actual) == best


def test_maximum_solver_size_is_bounded():
    items = [{'segment_id': str(i), 'appraisal': {'implementation_cost': 1, 'net_present_value': i + 1}} for i in range(30)]
    picked, states = _exact_selection(items, 15)
    assert picked == list(range(15, 30))
    assert states <= 65536


@pytest.mark.parametrize('changes', [
    {'applicability_confirmed': False}, {'fatal_transfer_assumption_confirmed': False},
    {'countermeasure_id': 'invented'}, {'eligible_fraction': 1.1}, {'implementation_cost': .001},
    {'implementation_cost': True}, {'fatalities_per_crash': '1'}, {'applicability_confirmed': 'true'},
    {'service_life_years': 1000}, {'discount_rate': -.01}, {'segment_id': '   '},
])
def test_portfolio_bad_inputs_fail(client, changes):
    response = client.post('/api/safety/planning/portfolio', json={'budget': 100000, 'candidates': [candidate(**changes)]})
    assert response.status_code == 422, response.text


def test_portfolio_rejects_unknowns_duplicate_ids_and_mixed_horizons(client):
    url = '/api/safety/planning/portfolio'
    assert client.post(url, json={'budget': 10000, 'candidates': [candidate(sid='missing')]}).status_code == 404
    for candidates in [[candidate(), candidate()], [candidate(), candidate('B1', 'B', service_life_years=5)],
                       [candidate() for _ in range(31)]]:
        assert client.post(url, json={'budget': 10000, 'candidates': candidates}).status_code == 422
    assert client.post(url, json={'budget': 10000, 'candidates': [candidate()], 'claimed_savings': 1e9}).status_code == 422


def test_workflow_capacity_is_not_automatically_cash(client):
    r = client.post('/api/safety/planning/workflow', json=workflow()).json()
    assert r['annual_hours_released'] == 300
    assert r['annual_staff_capacity_value'] == 15000
    assert r['annual_cash_savings_scenario'] == 0
    assert r['annual_net_cash_scenario'] == -6000
    assert r['annual_net_capacity_value'] == 9000
    assert r['first_year_net_capacity_value'] == 7000
    assert r['annual_capacity_break_even_cases'] == 40
    assert r['annual_cash_break_even_cases'] is None
    r = client.post('/api/safety/planning/workflow', json=workflow(cash_realization_fraction=.5)).json()
    assert r['annual_cash_savings_scenario'] == 7500
    assert r['annual_cash_break_even_cases'] == 80


def test_workflow_negative_and_tiny_improvements(client):
    r = client.post('/api/safety/planning/workflow', json=workflow(after_hours_per_case=5)).json()
    assert r['annual_hours_released'] == -100
    assert r['annual_capacity_break_even_cases'] is None
    r = client.post('/api/safety/planning/workflow', json=workflow(before_hours_per_case=1e-300, after_hours_per_case=0, hourly_cost=1e-300))
    assert r.status_code == 200 and r.json()['annual_capacity_break_even_cases'] is None


def test_outcome_adjusts_for_exposure_and_reports_conditional_interval(client):
    r = client.post('/api/safety/planning/outcomes', json=outcome()).json()
    assert r['before']['rate_per_100m_vmt'] == 20
    assert r['after']['rate_per_100m_vmt'] == 5
    assert r['rate_ratio_after_to_before'] == .25
    assert r['rate_change_percent'] == -75
    assert r['expected_after_count_at_before_rate'] == 40
    assert r['observed_minus_before_rate_expected_after'] == -30
    lo, hi = r['rate_ratio_interval95']
    assert 0 < lo < .25 < hi
    assert r['causal_effect_established'] is False
    assert r['input_verification'] == 'user_submitted_not_independently_verified'


def test_comparison_group_ratio_of_ratios(client):
    body = outcome(comparison_before={'crashes': 40, 'exposure_vmt': 100000000},
                   comparison_after={'crashes': 40, 'exposure_vmt': 200000000})
    r = client.post('/api/safety/planning/outcomes', json=body).json()['comparison_adjusted']
    assert r['comparison_rate_ratio'] == .5
    assert r['ratio_of_rate_ratios'] == .5
    assert r['relative_change_percent'] == -50
    assert r['ratio_of_rate_ratios_interval95'][0] < .5 < r['ratio_of_rate_ratios_interval95'][1]


def test_zero_counts_do_not_create_infinite_or_certain_effects(client):
    body = outcome(before={'crashes': 0, 'exposure_vmt': 1e8}, after={'crashes': 0, 'exposure_vmt': 1e8})
    r = client.post('/api/safety/planning/outcomes', json=body).json()
    assert r['rate_ratio_after_to_before'] is None
    assert r['rate_ratio_interval95'] is None
    assert r['after']['rate_interval95'][1] == pytest.approx(3.688879454)
    body['before']['crashes'] = 10
    r = client.post('/api/safety/planning/outcomes', json=body).json()
    assert r['rate_ratio_after_to_before'] == 0
    assert r['rate_ratio_interval95'] is None


def test_outcomes_require_comparable_valid_periods(client):
    before = {'crashes': 1, 'exposure_vmt': 1e8, 'start_date': '2024-01-01', 'end_date': '2024-12-31'}
    after = {**before, 'start_date': '2024-06-01'}
    assert client.post('/api/safety/planning/outcomes', json=outcome(before=before, after=after)).status_code == 422
    before['start_date'] = '2024-02-30'
    assert client.post('/api/safety/planning/outcomes', json=outcome(before=before)).status_code == 422
    assert client.post('/api/safety/planning/outcomes', json=outcome(comparison_before={'crashes': 1, 'exposure_vmt': 1e8})).status_code == 422
    assert client.post('/api/safety/planning/outcomes', json=outcome(before={'crashes': -1, 'exposure_vmt': 1e8})).status_code == 422
    assert client.post('/api/safety/planning/outcomes', json=outcome(before={'crashes': 1, 'exposure_vmt': 0})).status_code == 422


def test_evidence_binds_snapshot_inputs_and_recomputes_financials(client, snapshot):
    body = evidence(portfolio={'budget': 10000, 'candidates': [candidate()]}, workflow=workflow(), outcomes=outcome())
    response = client.post('/api/safety/planning/evidence', json=body)
    assert response.status_code == 200, response.text
    assert 'attachment' in response.headers['content-disposition']
    r = response.json()
    assert r['snapshot']['provenance'] == snapshot['provenance']
    assert r['portfolio']['selected_candidate_ids'] == ['A1']
    assert r['workflow']['annual_cash_savings_scenario'] == 0
    assert not r['certification']['submission_ready']
    assert not r['certification']['agency_endorsed']
    assert r['financial_interpretation']['aggregate_cross_module_benefit'] is None
    assert r['snapshot']['data_mode'] == 'synthetic'
    assert any('Commercial data-use' in v for v in r['missing_requirements'])
    digest = r.pop('artifact_sha256')
    del r['artifact_hash_excludes']
    assert hashlib.sha256(json.dumps(r, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == digest
    old_hash = r['snapshot']['snapshot_sha256']
    snapshot['segments'][0]['expected_annual'] = .3
    r = client.post('/api/safety/planning/evidence', json=body).json()
    assert r['snapshot']['snapshot_sha256'] != old_hash


def test_evidence_rejects_foreign_projects_and_fabricated_totals(client):
    body = evidence(portfolio={'budget': 10000, 'candidates': [candidate('B1', 'B')]})
    assert client.post('/api/safety/planning/evidence', json=body).status_code == 422
    assert client.post('/api/safety/planning/evidence', json=evidence(segment_ids=['missing'])).status_code == 404
    assert client.post('/api/safety/planning/evidence', json=evidence(agency_endorsed=True)).status_code == 422
    assert client.post('/api/safety/planning/evidence', json=evidence(supporting_sources=['file:///etc/passwd'])).status_code == 422


@pytest.mark.parametrize('endpoint,body', [('portfolio', {'budget': 10000, 'candidates': [candidate()]}),
                                         ('workflow', workflow()), ('outcomes', outcome())])
def test_nonfinite_json_inputs_rejected(client, endpoint, body):
    field = {'portfolio': 'budget', 'workflow': 'hourly_cost', 'outcomes': None}[endpoint]
    if field:
        body[field] = 'NONFINITE'
    else:
        body['before']['exposure_vmt'] = 'NONFINITE'
    raw = json.dumps(body).replace('"NONFINITE"', '1e999')
    # Existing app's validation handler must safely serialize nonfinite errors.
    response = client.post('/api/safety/planning/' + endpoint, content=raw, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422


def test_sensitivity_varies_only_cmf_and_keeps_selection(client):
    response = client.post('/api/safety/planning/portfolio', json={'budget': 10000, 'candidates': [candidate()]})
    result = response.json()
    sensitivity = result['cmf_sensitivity']
    row = sensitivity['candidates'][0]
    assert row['cmf_scenario_low'] == pytest.approx(.635 - 1.96 * .052)
    assert row['cmf_scenario_high'] == pytest.approx(.635 + 1.96 * .052)
    assert sensitivity['societal_benefits_present_value_lower'] == pytest.approx(.2 * .5 * (1 - row['cmf_scenario_high']) * 14200000 * 10)
    assert sensitivity['societal_benefits_present_value_lower'] < result['totals']['societal_safety_benefits_present_value'] < sensitivity['societal_benefits_present_value_upper']
    assert sensitivity['same_selected_portfolio'] and not sensitivity['selection_reoptimized']
    assert 'not a joint 95%' in sensitivity['limitations'][0]


def test_evidence_readable_report_keeps_money_categories_separate(client):
    body = evidence(portfolio={'budget': 10000, 'candidates': [candidate()]}, workflow=workflow())
    result = client.post('/api/safety/planning/evidence', json=body).json()
    report = result['report_text']
    assert result['snapshot']['snapshot_sha256'] in report
    assert 'Agency cash savings: not established' in report
    assert 'Capacity value and cash realization overlap' in report
    assert 'not an endorsement' in report
    assert 'Commercial data-use' in report


def test_extreme_but_valid_outcomes_still_return_finite_json(client):
    body = outcome(before={'crashes': 1, 'exposure_vmt': 1e15}, after={'crashes': 10000000, 'exposure_vmt': 1},
                   comparison_before={'crashes': 10000000, 'exposure_vmt': 1}, comparison_after={'crashes': 1, 'exposure_vmt': 1e15})
    result = client.post('/api/safety/planning/outcomes', json=body)
    assert result.status_code == 200
    json.dumps(result.json(), allow_nan=False)

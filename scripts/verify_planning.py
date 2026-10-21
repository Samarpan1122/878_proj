"""Anonymous release smoke: real snapshots plus clearly hypothetical inputs.

POSTs perform calculations only. No agency observations or actual savings are
claimed by this verification. One optional provider request computes a real path.
"""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def verify(base, include_routing=True):
    checks = []

    def call(path, payload=None):
        encoded = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        request = urllib.request.Request(base.rstrip('/') + path, data=encoded,
                                         headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        value = json.loads(raw)
        checks.append({'path':path,'status':200})
        return value

    ready = call('/ready')
    with urllib.request.urlopen(base.rstrip('/')+'/planning/',timeout=30) as response:
        assert b'Plan the next safety investment' in response.read()
    checks.append({'path':'/planning/','status':200})
    roads = call('/api/safety/segments?limit=1')['segments']
    road = roads[0]
    projection = call('/api/safety/projection',{'segment_id':road['segment_id'],'target_year':2027,
                  'aadt':float(road['aadt'])*1.05,'scenario_note':'Release verification hypothetical +5% traffic; not measured future traffic'})
    assert projection['validated_forecast'] is False and projection['mean_annual_fatal_crashes']>0
    assert projection['predictive_count_interval95']['lower']>=0
    portfolio_request = {'budget':50000.,'candidates':[{'candidate_id':'verification-only','segment_id':road['segment_id'],
        'countermeasure_id':'4737','implementation_cost':10000.,'annual_maintenance_cost':500.,
        'service_life_years':10,'discount_rate':.03,'fatalities_per_crash':1.,'eligible_fraction':.5,
        'applicability_confirmed':True,'fatal_transfer_assumption_confirmed':True}]}
    portfolio = call('/api/safety/planning/portfolio',portfolio_request)
    assert portfolio['totals']['implementation_cost']<=50000 and portfolio['totals']['agency_cash_savings'] is None
    work_request={'annual_cases':100,'before_hours_per_case':4.,'after_hours_per_case':2.,'hourly_cost':50.,
                  'annual_software_cost':5000.,'cash_realization_fraction':0.}
    work=call('/api/safety/planning/workflow',work_request)
    assert work['annual_hours_released']==200 and work['annual_cash_savings_scenario']==0
    outcome_request={'before':{'crashes':10,'exposure_vmt':10000000.},'after':{'crashes':5,'exposure_vmt':10000000.},
                     'source_note':'Arithmetic verification fixture, not an agency outcome'}
    outcome=call('/api/safety/planning/outcomes',outcome_request)
    assert outcome['rate_ratio_after_to_before']==.5 and outcome['causal_effect_established'] is False
    evidence=call('/api/safety/planning/evidence',{'project_name':'Release verification fixture','agency_name':'No agency; software verification',
                 'project_description':'Hypothetical arithmetic check only. No real road eligibility is asserted.',
                 'segment_ids':[road['segment_id']],'portfolio':portfolio_request,'workflow':work_request,'outcomes':outcome_request})
    assert evidence['certification']['submission_ready'] is False and evidence['report_text']
    expected=evidence.pop('artifact_sha256'); evidence.pop('artifact_hash_excludes')
    assert hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==expected
    match=call('/api/safety/linkage/match',{'records':[{'case_id':'verification-location','lat':41.2565,'lng':-95.9345}]})
    assert len(match['results'])==1
    review=call('/api/safety/linkage/review',{'reviews':[{'case_id':'verification-label','proposed_segment_id':'A',
                 'reviewed_segment_id':'A','decision':'correct','notes':'Arithmetic fixture; no independently reviewed real case.'}]})
    assert review['precision_among_resolved']==1 and review['precision_wilson95'][0]<1
    routing=call('/api/safety/routing/status')
    route_metrics=None
    if include_routing:
        assert routing['route_generation_available'] is True and routing['live_traffic_available'] is False
        # Bounded retries address first-request cold starts only; no state is written.
        for attempt in range(3):
            try:
                routes=call('/api/safety/routing/routes',{'origin':{'lat':41.2565,'lng':-95.9345},
                            'destination':{'lat':41.26,'lng':-96.02},'alternatives':True})
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in (502,503,504) or attempt==2:raise
                time.sleep(3)
        assert routes['routes'] and routes['time_basis']=='provider_baseline_non_live'
        for route in routes['routes']:
            assert route['distance_miles']>0 and route['baseline_minutes']>0
            if route['risk_coverage_fraction']<.999999:
                assert route['historical_risk_index'] is None
        route_metrics=[{k:r.get(k) for k in ['route_id','distance_miles','baseline_minutes','risk_coverage_fraction']} for r in routes['routes']]
    return {'verified_at':datetime.now(timezone.utc).isoformat(),'base_url':base,'ready':ready,'checks':checks,
            'real_road_segment':road['segment_id'],'route_metrics':route_metrics,'hypothetical_inputs_only':True,
            'agency_validation':False,'status':'passed'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url')
    parser.add_argument('--output',default='outputs/releases/agency-planning-cloud-smoke.json')
    parser.add_argument('--skip-routing',action='store_true')
    args=parser.parse_args()
    result=verify(args.base_url,not args.skip_routing)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({'status':result['status'],'checks':len(result['checks']),'revision':result['ready'].get('revision')}))

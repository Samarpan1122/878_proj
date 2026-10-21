"""Verify the public website, historical data, live model inference and API guards.

Uses unauthenticated read requests and calculation-only POSTs; never changes data.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


def verify(origin):
    def fetch(path, body=None):
        request = Request(origin.rstrip('/') + path, data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'} if body is not None else {})
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise RuntimeError('Response exceeds smoke-check size limit')
            return response.status, response.headers, raw

    def get(path, body=None):
        code, headers, raw = fetch(path, body)
        if code != 200 or 'application/json' not in headers.get('Content-Type', ''):
            raise RuntimeError(f'Expected public JSON response from {path}; received {code}')
        value = json.loads(raw)
        json.dumps(value, allow_nan=False)
        return value

    for path in ['/', '/explore/', '/assets/home.js', '/assets/home.css', '/assets/deckgl.js', '/assets/DECKGL-LICENSE.txt',
                 '/assets/app.js', '/assets/app.css', '/assets/states.json', '/assets/US-ATLAS-LICENSE.txt',
                 '/screening/', '/screening/safety.js', '/screening/safety-evidence.js', '/docs']:
        code, headers, raw = fetch(path)
        if code != 200 or not raw:
            raise RuntimeError(f'Public page or asset failed: {path} ({code})')
        if headers.get('X-Content-Type-Options') != 'nosniff':
            raise RuntimeError('Missing security header')
    ready, meta = get('/ready'), get('/api/public/meta')
    summary = get('/api/public/summary')
    if not ready.get('ready') or summary['fatal_crashes'] != meta['total_crashes']:
        raise RuntimeError('Public release is not ready or totals differ')
    if meta['data_mode'] != 'real_federal_historical_aggregates':
        raise RuntimeError('Public service is not the real-data release')
    features = get('/api/public/map')
    if sum(features['coverage'].values()) != summary['fatal_crashes']:
        raise RuntimeError('Map suppression and location accounting differ from source totals')
    model = get('/api/public/model')
    prediction = get('/api/public/forecast', {'state': 31, 'year': model['prediction_year']})
    p = model['parameters']
    expected = math.exp(p['state_intercepts']['31'] + p['year_coefficient'] * (model['prediction_year'] - p['year_origin']))
    if not math.isclose(prediction['expected_fatal_crashes'], expected, rel_tol=1e-12):
        raise RuntimeError('Deployed state inference differs from the published parameters')
    behavior = get('/api/public/behaviors')
    if behavior['cohort']['fatal_crashes'] != summary['fatal_crashes']:
        raise RuntimeError('Recorded-factor denominator differs from source totals')
    page = get('/api/safety/segments?limit=1')
    road = page['segments'][0]
    inference = get('/api/safety/segments/' + quote(road['segment_id'], safe='') + '/prediction')
    if not math.isclose(inference['eb_annual'], road['expected_annual'], rel_tol=1e-7, abs_tol=1e-9):
        raise RuntimeError('Road inference differs from the recorded screening output')
    get('/api/safety/model-evidence')
    get('/api/safety/behavior')
    get('/api/safety/benefit-cost', {'segment_id': road['segment_id'], 'countermeasure_id': '4737',
        'implementation_cost': 100000, 'annual_maintenance_cost': 1000, 'service_life_years': 10,
        'discount_rate': .03, 'fatalities_per_crash': 1, 'eligible_fraction': .5,
        'applicability_confirmed': True, 'fatal_transfer_assumption_confirmed': True})
    if fetch('/api/safety/export?commercial=true')[0] != 409:
        raise RuntimeError('Commercial export boundary missing')
    if fetch('/api/public/forecast', {'state':31,'year':2026})[0] != 422:
        raise RuntimeError('Unsupported forecast horizon accepted')
    if fetch('/api/public/forecast', {'state':31,'padding':'x'*20000})[0] != 413:
        raise RuntimeError('Request size guard missing')
    for path in ['/.env', '/data/safety/snapshot.json', '/api/research/predict', '/api/research/advanced', '/models.html']:
        if fetch(path)[0] != 404:
            raise RuntimeError(f'Unexpected restricted route: {path}')
    schema = get('/openapi.json')
    if '/api/public/forecast' not in schema['paths'] or '/api/safety/benefit-cost' not in schema['paths']:
        raise RuntimeError('Incomplete API documentation')
    return {'status':'passed','url':origin,'verified_at':datetime.now(timezone.utc).isoformat(),
            'unauthenticated_public_access':True,'revision':ready.get('revision'),
            'fatal_crashes':summary['fatal_crashes'],'fatalities':summary['fatalities'],
            'road_segments':page['total'],'data_years':meta['years'],'artifact_sha256':meta['artifact_sha256'],
            'map_coverage':features['coverage'],'state_inference':'matches published coefficients',
            'road_inference':'matches recorded screening','scenario':'passed with test assumptions only',
            'api_guards':'passed','research_isolation':'passed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output', default='outputs/releases/public-verification.json')
    args = parser.parse_args()
    url = urlsplit(args.url)
    if url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
        parser.error('Supply a service origin without credentials or path')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ['localhost','127.0.0.1']):
        parser.error('Use HTTPS except for local verification')
    result = verify(args.url)
    target = Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

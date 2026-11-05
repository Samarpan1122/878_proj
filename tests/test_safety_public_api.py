import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from safety.public_api import BoundedRequests, create_app
from test_safety_public_data import public_artifact


@pytest.fixture
def client(tmp_path,public_artifact):
    (tmp_path/'snapshot.json').write_text(json.dumps(public_artifact))
    return TestClient(create_app(root=tmp_path,enable_screening=False))


def test_real_aggregate_contract_filter_and_map_coverage(client):
    assert client.get('/ready').status_code==200
    summary=client.get('/api/public/summary?state=31&year=2024').json()
    assert summary['fatal_crashes']==92 and summary['fatalities']==94
    assert len(summary['states'])==1 and len(summary['years'])==1
    mapped=client.get('/api/public/map?state=31&year=2024').json()
    assert mapped['coverage']=={'mapped_crashes':7,'suppressed_crashes':84,'unlocated_crashes':1}
    assert mapped['features'][0]['geometry']['coordinates']==[-97.125,41.125]
    assert client.get('/api/public/summary?state=3').status_code==422
    assert client.get('/api/public/map?year=2026').status_code==422
    assert client.get('/api/public/meta').headers['x-data-release']


def test_forecast_get_post_parity_and_bounded_inputs(client):
    a=client.get('/api/public/forecast?state=31')
    b=client.post('/api/public/forecast',json={'state':31})
    assert a.json()==b.json()
    assert a.json()['year']==2025
    assert a.json()['expected_fatal_crashes']>0
    for payload in [{'state':3},{'state':31,'year':2026},{'state':'31'},{'state':31,'file':'/etc/passwd'},{'state':True}]:
        assert client.post('/api/public/forecast',json=payload).status_code==422
    assert client.post('/api/public/forecast',content='x'*16385).status_code==413


def test_behavior_denominators_and_export(client):
    evidence=client.get('/api/public/behaviors?state=31&year=2024').json()
    assert evidence['cohort']['fatal_crashes']==92
    f=evidence['cohort']['factors']['speeding']
    assert f['yes']+f['no']+f['unknown']+f['not_applicable']==92
    export=client.get('/api/public/export?state=31')
    assert len(export.json()['summary_rows'])==4
    assert 'attachment' in export.headers['content-disposition']


def test_only_public_routes_and_safe_headers(client):
    for url in ['/api/research/predict','/.cloud-config','/data/safety/crashes.parquet','/snapshot.json','/assets/../../.cloud-config']:
        assert client.get(url).status_code==404
    r=client.get('/api/public/model')
    assert r.headers['x-frame-options']=='DENY'
    assert r.headers['x-content-type-options']=='nosniff'
    assert 'max-age=300' in r.headers['cache-control']
    assert len(r.json()['evaluation']['rows'])==2


def test_missing_and_invalid_release_fail_closed(tmp_path):
    client=TestClient(create_app(tmp_path,enable_screening=False))
    assert client.get('/health').status_code==200
    assert client.get('/ready').status_code==503
    (tmp_path/'snapshot.json').write_text('{"schema_version":1,"kind":"public_fars_aggregate_release","value":1e999}')
    client=TestClient(create_app(tmp_path,enable_screening=False))
    assert client.get('/api/public/summary').status_code==503


def test_streamed_body_cap_and_rate_limit_without_trusting_forwarded_ip():
    async def run():
        called=[]
        async def downstream(scope,receive,send):called.append(True)
        middleware=BoundedRequests(downstream,burst=1,requests_per_second=0)
        scope={'type':'http','path':'/api/public/forecast','method':'POST','headers':[(b'x-forwarded-for',b'1.2.3.4')]}
        messages=iter([{'type':'http.request','body':b'a'*9000,'more_body':True},{'type':'http.request','body':b'b'*9000,'more_body':False}])
        async def receive():return next(messages)
        sent=[]
        async def send(m):sent.append(m)
        await middleware(scope,receive,send)
        assert sent[0]['status']==413 and not called
        sent.clear()
        scope['headers']=[(b'x-forwarded-for',b'9.9.9.9')]
        await middleware(scope,receive,send)
        assert sent[0]['status']==429 and not called
    asyncio.run(run())


def test_screening_integration_stays_separate_and_guarded(tmp_path,public_artifact):
    public=tmp_path/'public';public.mkdir()
    (public/'snapshot.json').write_text(json.dumps(public_artifact))
    screening=tmp_path/'screening';screening.mkdir()
    (screening/'snapshot.json').write_text(json.dumps({'schema_version':1,'built_at':'2026-09-30T00:00:00Z',
        'segments':[{'segment_id':'A','lat':41.,'lng':-97.,'observed':3,'expected_annual':.2,'excess_annual':.1,'rate_per_100m_vmt':4.}]}))
    client=TestClient(create_app(public,screening_root=screening))
    assert client.get('/ready').status_code==200
    assert client.get('/api/safety/segments?limit=1').json()['segments'][0]['segment_id']=='A'
    assert client.get('/api/safety/export?commercial=true').status_code==409
    assert client.get('/screening/').status_code==200
    assert client.get('/screening/safety.css').status_code==200
    assert client.get('/screening/models.html').status_code==404
    assert client.get('/api/research/metro').status_code==404
    assert client.post('/api/safety/benefit-cost',content='a'*16385).status_code==413
    (screening/'snapshot.json').unlink()
    assert client.get('/ready').status_code==503


def test_notebook_page_served_when_built_and_503_when_missing(tmp_path,public_artifact):
    (tmp_path/'snapshot.json').write_text(json.dumps(public_artifact))
    static=tmp_path/'static';static.mkdir()
    client=TestClient(create_app(root=tmp_path,static_root=static,enable_screening=False))
    assert client.get('/notebook/').status_code==503
    (static/'notebook.html').write_text('<!doctype html><title>Analysis notebook</title>')
    page=client.get('/notebook/')
    assert page.status_code==200 and 'Analysis notebook' in page.text


def test_planning_page_redirects_and_schema_lists_only_advertised_routes(tmp_path,public_artifact):
    public=tmp_path/'public';public.mkdir()
    (public/'snapshot.json').write_text(json.dumps(public_artifact))
    screening=tmp_path/'screening';screening.mkdir()
    (screening/'snapshot.json').write_text(json.dumps({'schema_version':1,'built_at':'2026-09-30T00:00:00Z',
        'segments':[{'segment_id':'A','lat':41.,'lng':-97.,'observed':3,'expected_annual':.2,'excess_annual':.1,'rate_per_100m_vmt':4.}]}))
    client=TestClient(create_app(public,screening_root=screening))
    moved=client.get('/planning/',follow_redirects=False)
    assert moved.status_code==308 and moved.headers['location']=='/screening/'
    schema=client.get('/openapi.json').json()['paths']
    advertised={'/api/public/meta':'get','/api/public/states':'get','/api/public/summary':'get','/api/public/map':'get',
                '/api/public/model':'get','/api/public/forecast':'get','/api/public/behaviors':'get','/api/public/crashes':'get',
                '/api/safety/status':'get','/api/safety/segments':'get','/api/safety/countermeasures':'get','/api/safety/benefit-cost':'post'}
    assert set(schema)==set(advertised)
    for path,method in advertised.items():
        assert method in schema[path]
    assert 'post' not in schema['/api/public/forecast']
    # Hidden routes keep serving the screening page and API callers.
    assert client.get('/api/safety/segments/A').status_code==200
    assert client.get('/api/safety/readiness').status_code in {200,503}
    engines=[e.get('endpoint') for e in client.get('/api/public/meta').json()['engines']]
    assert all(e is None or e in schema for e in engines)

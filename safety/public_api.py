"""Public historical-data portal, bounded model inference and screening APIs.

Launch with uvicorn safety.public_api:app. Only aggregate artifacts are loaded;
no pickle, user-selected file paths, database credentials or external fetches.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from safety.api import strict_json, validation_error_response
from safety.public_data import predict_count, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


class BoundedRequests:
    """Cap all bodies, including chunked requests, and bound total API throughput.

    The bucket is per process, not per claimed client IP; X-Forwarded-For is never
    trusted. Cloud instance/concurrency limits remain a separate deployment control.
    """
    def __init__(self, app, max_body=16384, burst=180, requests_per_second=6):
        self.app, self.max_body = app, max_body
        self.burst, self.rate = burst, requests_per_second
        self.tokens, self.last = float(burst), time.monotonic()
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async def reject(status, detail):
            response = JSONResponse({'detail':detail},status_code=status,
                                    headers={'Retry-After':'1'} if status==429 else {})
            await response(scope, receive, send)
        if '/api/' in scope['path']:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.burst, self.tokens + (now-self.last)*self.rate)
                self.last = now
                allowed = self.tokens >= 1
                if allowed: self.tokens -= 1
            if not allowed:
                return await reject(429,'Public API capacity reached; retry shortly')
        headers = dict(scope.get('headers',[]))
        try:
            if int(headers.get(b'content-length',b'0')) > self.max_body:
                return await reject(413,'Request body exceeds 16 KiB')
        except ValueError:
            return await reject(400,'Invalid Content-Length')
        if scope['method'] in {'POST','PUT','PATCH'}:
            parts, size = [], 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body',b'')
                size += len(chunk)
                if size > self.max_body:
                    return await reject(413,'Request body exceeds 16 KiB')
                parts.append(chunk)
                if not message.get('more_body',False): break
            delivered = False
            async def bounded_receive():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {'type':'http.request','body':b''.join(parts),'more_body':False}
            return await self.app(scope,bounded_receive,send)
        return await self.app(scope,receive,send)


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    state: int = Field(ge=1,le=56)
    year: int = Field(default=2025,ge=2025,le=2025)


def create_app(root=None, screening_root=None, static_root=None, enable_screening=True):
    app = FastAPI(title='GeoCrash Public Data & Safety API',version='1.0.0',
                  description='Real historical FARS aggregates, evaluated state count projections, and experimental Nebraska screening. No live incident or foundation-model claim.')
    app.add_middleware(BoundedRequests)
    app.add_exception_handler(RequestValidationError, validation_error_response)
    path = Path(root or os.getenv('GEOCRASH_PUBLIC_DATA','data/public'))/'snapshot.json'
    value, artifact_hash, load_error = None, None, None
    try:
        raw = path.read_bytes()
        if len(raw)>8_000_000: raise ValueError('Artifact exceeds release size limit')
        value = validate_snapshot(strict_json(raw.decode()))
        artifact_hash = hashlib.sha256(raw).hexdigest()
    except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
        load_error = type(exc).__name__
    app.state.public_artifact_sha256 = artifact_hash
    screening_store = None

    @app.middleware('http')
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        response.headers['Cache-Control']='public, max-age=300' if request.method=='GET' and response.status_code==200 and request.url.path.startswith('/api/public/') else 'no-store'
        if artifact_hash and request.url.path.startswith('/api/public/'):
            response.headers['X-Data-Release']=artifact_hash
        return response

    def required():
        if value is None:
            raise HTTPException(503,'Public data release is unavailable or invalid')
        return value

    def select(state,year):
        data = required()
        if state is not None and state not in {s['state_fips'] for s in data['states']}:
            raise HTTPException(422,'State must be a supported FIPS code')
        if year is not None and year not in data['meta']['years']:
            raise HTTPException(422,'Year is outside the published source coverage')
        return [r for r in data['summary_rows'] if (state is None or r['state_fips']==state) and (year is None or r['year']==year)]

    @app.get('/health',include_in_schema=False)
    def health():
        return {'status':'ok','service':'geocrash_public','data_loaded':value is not None}

    @app.get('/ready',include_in_schema=False)
    def ready():
        data = required()
        if screening_store is not None and screening_store.read() is None:
            raise HTTPException(503,'Screening snapshot is unavailable')
        return {'ready':True,'fatal_crashes':data['meta']['total_crashes'],'artifact_sha256':artifact_hash,
                'revision':os.getenv('K_REVISION')}

    @app.get('/api/public/meta')
    def metadata():
        return {**required()['meta'],'artifact_sha256':artifact_hash,
                'engines':[
                    {'id':'fars-state-poisson-v1','status':'serving','scope':'51 jurisdictions, annual fatal-crash count projection','endpoint':'/api/public/forecast'},
                    *([{'id':'nebraska-nb-eb','status':'serving','scope':'Experimental Nebraska segment screening with 2025 AADT proxies','endpoint':'/api/safety/segments'},
                       {'id':'countermeasure-economics','status':'serving','scope':'Guarded sourced CMF cost-benefit scenarios','endpoint':'/api/safety/benefit-cost'}] if enable_screening else []),
                    *([{'id':'agency-planning','status':'serving','scope':'Budget portfolios, workflow economics, descriptive outcomes and traceable evidence','endpoint':'/api/safety/planning/portfolio'},
                       {'id':'conditional-road-projection','status':'serving','scope':'Future-year traffic-exposure scenarios; not validated forecasts','endpoint':'/api/safety/projection'},
                       {'id':'route-comparison','status':'serving','scope':'Baseline route generation when configured; bounded personalized candidate comparison','endpoint':'/api/safety/routing/status'},
                       {'id':'road-linkage-audit','status':'serving','scope':'Conservative coordinate matching and user-supplied independent label reviews','endpoint':'/api/safety/linkage/summary'}] if enable_screening else []),
                    {'id':'roadworld-foundation','status':'architecture_only_not_trained','scope':'Research design; no inference endpoint'}],
                'screening_source_policy':'https://dot.nebraska.gov/policies-and-disclaimers/' if enable_screening else None}

    @app.get('/api/public/states')
    def states():
        return {'states':required()['states']}

    @app.get('/api/public/summary')
    def summary(state: int|None=Query(default=None,ge=1,le=56),year: int|None=Query(default=None,ge=2000,le=2100)):
        rows = select(state,year)
        names = {s['state_fips']:s for s in required()['states']}
        def totals(subset):
            return {k:sum(r[k] for r in subset) for k in ['fatal_crashes','fatalities','located_crashes']}
        return {**totals(rows),'state_fips':state,'year':year,
                'years':[{'year':y,**totals([r for r in rows if r['year']==y])} for y in sorted({r['year'] for r in rows})],
                'states':[{**names[s],**totals([r for r in rows if r['state_fips']==s])} for s in sorted({r['state_fips'] for r in rows})]}

    @app.get('/api/public/map')
    def map_data(state: int|None=Query(default=None,ge=1,le=56),year: int|None=Query(default=None,ge=2000,le=2100)):
        rows = select(state,year)
        data = required()
        cells = [c for c in data['cells'] if (state is None or c['state_fips']==state) and (year is None or c['year']==year)]
        # Merge visible cells across selected years for a legible pooled map.
        pooled = {}
        for cell in cells:
            key = (cell['state_fips'],cell['lat'],cell['lng'])
            item = pooled.setdefault(key,{'state_fips':cell['state_fips'],'lat':cell['lat'],'lng':cell['lng'],
                                         'year':year,'fatal_crashes':0,'fatalities':0})
            item['fatal_crashes'] += cell['fatal_crashes']
            item['fatalities'] += cell['fatalities']
        mapped = sum(c['fatal_crashes'] for c in cells)
        located = sum(r['located_crashes'] for r in rows)
        total = sum(r['fatal_crashes'] for r in rows)
        features = [{'type':'Feature','geometry':{'type':'Point','coordinates':[c['lng'],c['lat']]},
                     'properties':{k:v for k,v in c.items() if k not in {'lat','lng'}}} for c in pooled.values()]
        return {'type':'FeatureCollection','features':features,**data['meta']['map'],
                'coverage':{'mapped_crashes':mapped,'suppressed_crashes':located-mapped,'unlocated_crashes':total-located},
                'aggregation_note':'Suppression is applied separately to each state-year cell before pooling; pooled map counts can omit sparse years.'}

    @app.get('/api/public/model')
    def model():
        return required()['model']

    def forecast_result(state,year=None):
        rows = select(state,None)
        data = required()
        model = data['model']
        year = model['prediction_year'] if year is None else year
        try: prediction = predict_count(model['parameters'],state,year)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        latest = max(rows,key=lambda r:r['year'])
        name = next(s['state_name'] for s in data['states'] if s['state_fips']==state)
        return {'state_fips':state,'state_name':name,'year':year,'expected_fatal_crashes':prediction,
                'last_observed_year':latest['year'],'last_observed_crashes':latest['fatal_crashes'],
                'model_id':model['model_id'],'trained_years':model['trained_years'],
                'interpretation':'Frozen annual fatal-crash count projection from historical data; not a current forecast, per-mile risk or guaranteed outcome.',
                'limitations':model['limitations']}

    @app.get('/api/public/forecast')
    def forecast(state: int=Query(ge=1,le=56)):
        return forecast_result(state)

    @app.post('/api/public/forecast')
    def forecast_post(request:ForecastRequest):
        return forecast_result(request.state,request.year)

    @app.get('/api/public/behaviors')
    def behaviors(state: int|None=Query(default=None,ge=1,le=56),year: int|None=Query(default=None,ge=2000,le=2100)):
        select(state,year)
        evidence = required()['behaviors']
        cohort = next((c for c in evidence['cohorts'] if c['state_fips']==state and c['year']==year),None)
        if cohort is None: raise HTTPException(503,'Requested evidence cohort is unavailable')
        return {'cohort':cohort,'definitions':evidence['definitions'],'limitations':evidence['limitations']}

    @app.get('/api/public/export')
    def export(state: int|None=Query(default=None,ge=1,le=56),year: int|None=Query(default=None,ge=2000,le=2100)):
        rows = select(state,year)
        result = {'meta':required()['meta'],'summary_rows':rows,'filters':{'state_fips':state,'year':year},
                  'artifact_sha256':artifact_hash,'export_type':'FARS aggregated state-year counts'}
        return Response(json.dumps(result,allow_nan=False),media_type='application/json',
                        headers={'Content-Disposition':'attachment; filename="geocrash-fars-aggregates.json"'})

    if enable_screening:
        from safety.api import Snapshot, create_app as create_screening
        active_screening_root = screening_root or os.getenv('GEOCRASH_SCREENING_DATA','data/safety')
        screening_store = Snapshot(active_screening_root)
        screening = create_screening(root=active_screening_root)
        # The established workbench uses absolute API URLs. Expose only its safety
        # endpoints at the portal root; its static allowlist stays under /screening/.
        app.router.routes.extend(route for route in screening.router.routes if getattr(route,'path','').startswith('/api/safety/'))
        app.mount('/screening',screening,name='screening')

    static = Path(static_root) if static_root else ROOT/'web/public'
    @app.get('/',include_in_schema=False)
    def home():
        if not (static/'home.html').is_file():
            raise HTTPException(503,'Public homepage is not installed')
        return FileResponse(static/'home.html')

    @app.get('/explore/',include_in_schema=False)
    def explorer():
        if not (static/'index.html').is_file():
            raise HTTPException(503,'Public interface is not installed')
        return FileResponse(static/'index.html')

    @app.get('/planning/',include_in_schema=False)
    def planning():
        if not (static/'planning.html').is_file():
            raise HTTPException(503,'Agency planning workspace is not installed')
        return FileResponse(static/'planning.html')
    if static.is_dir():
        app.mount('/assets',StaticFiles(directory=static),name='public-assets')
    return app


app = create_app()

"""Build a FARS-only public aggregate release and an auditable count projection.

Runtime inference consumes JSON parameters, never serialized executable objects.
No road exposure, Kaggle rows, NDOT geometry or individual crash records are emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

STATE_NAMES = {
    1:'Alabama',2:'Alaska',4:'Arizona',5:'Arkansas',6:'California',8:'Colorado',
    9:'Connecticut',10:'Delaware',11:'District of Columbia',12:'Florida',13:'Georgia',
    15:'Hawaii',16:'Idaho',17:'Illinois',18:'Indiana',19:'Iowa',20:'Kansas',21:'Kentucky',
    22:'Louisiana',23:'Maine',24:'Maryland',25:'Massachusetts',26:'Michigan',27:'Minnesota',
    28:'Mississippi',29:'Missouri',30:'Montana',31:'Nebraska',32:'Nevada',33:'New Hampshire',
    34:'New Jersey',35:'New Mexico',36:'New York',37:'North Carolina',38:'North Dakota',
    39:'Ohio',40:'Oklahoma',41:'Oregon',42:'Pennsylvania',44:'Rhode Island',45:'South Carolina',
    46:'South Dakota',47:'Tennessee',48:'Texas',49:'Utah',50:'Vermont',51:'Virginia',
    53:'Washington',54:'West Virginia',55:'Wisconsin',56:'Wyoming',
}
LIMITATIONS = [
    'Historical FARS fatal-crash records for 2021–2024; this is not a live incident feed.',
    'Fatal crashes and fatalities are different measures. Nonfatal crashes are absent.',
    'Counts are not normalized by traffic exposure or population and do not measure individual driving risk.',
    'Map cells show aggregated crash locations, not road segments; cells with fewer than five crashes per state and year are withheld.',
    'The annual model is a simple statistical projection, not a validated local safety model or a trained foundation model.',
    'The frozen 2025 projection uses data through 2024. It is not a current-year forecast; source releases were retrieved in 2026.',
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def predict_count(parameters, state_fips, year):
    """Evaluate the persisted Poisson mean; state and one-year horizon are bounded."""
    state = str(state_fips)
    if state not in parameters['state_intercepts']:
        raise ValueError('Unsupported state')
    if year != parameters['prediction_year']:
        raise ValueError('Only the documented one-year projection is supported')
    return math.exp(parameters['state_intercepts'][state] + parameters['year_coefficient'] *
                    (year - parameters['year_origin']))


def fit_count_model(panel, years):
    """Poisson maximum likelihood: state intercepts and one common linear year trend.

    Profile out state intercepts. Fit the common slope using only supplied years.
    Fixed optimizer bounds prevent explosive extrapolation; no test-set selection.
    """
    import numpy as np
    from scipy.optimize import minimize_scalar
    frame = panel[panel.year.isin(years)].copy()
    states = sorted(frame.state_fips.unique().tolist())
    expected = {(s, y) for s in states for y in years}
    if set(zip(frame.state_fips, frame.year)) != expected or len(frame) != len(expected):
        raise ValueError('Training panel must have exactly one row per state and year')
    t = np.array(sorted(years), dtype=float) - min(years)
    totals = frame.groupby('year').fatal_crashes.sum().reindex(sorted(years)).to_numpy(dtype=float)
    if (totals <= 0).any():
        raise ValueError('Each training year must contain fatal crashes')
    def objective(beta):
        return float(totals.sum() * np.log(np.exp(beta*t).sum()) - beta * np.dot(totals, t))
    fit = minimize_scalar(objective, bounds=(-0.5, 0.5), method='bounded', options={'xatol':1e-12})
    if not fit.success:
        raise ValueError('Poisson fit failed')
    denominator = float(np.exp(fit.x*t).sum())
    intercepts = {}
    for state in states:
        total = float(frame[frame.state_fips == state].fatal_crashes.sum())
        if total <= 0:
            raise ValueError('State requires positive training support')
        intercepts[str(state)] = math.log(total / denominator)
    return {'state_intercepts':intercepts, 'year_coefficient':float(fit.x),
            'year_origin':int(min(years)), 'prediction_year':int(max(years)+1),
            'trained_years':[int(y) for y in sorted(years)]}


def count_metrics(actual, predicted):
    import numpy as np
    y, p = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if not np.isfinite(p).all() or (p <= 0).any() or (y < 0).any():
        raise ValueError('Invalid count predictions')
    term = np.zeros_like(y)
    positive = y > 0
    term[positive] = y[positive] * np.log(y[positive] / p[positive])
    return {'mae':float(np.abs(y-p).mean()), 'rmse':float(np.sqrt(np.square(y-p).mean())),
            'poisson_deviance':float((2*(term-y+p)).mean())}


def build_model(panel, years):
    train, test = years[:-1], years[-1]
    if len(train) < 2:
        raise ValueError('At least three complete years required for evaluation')
    heldout = fit_count_model(panel, train)
    rows = []
    for state in sorted(panel.state_fips.unique()):
        state_rows = panel[panel.state_fips == state].set_index('year')
        rows.append({'state_fips':int(state), 'state_name':STATE_NAMES[int(state)],
                     'actual':int(state_rows.loc[test, 'fatal_crashes']),
                     'predicted':predict_count(heldout, int(state), test),
                     'baseline':int(state_rows.loc[max(train), 'fatal_crashes'])})
    actual = [r['actual'] for r in rows]
    model_metrics = count_metrics(actual, [r['predicted'] for r in rows])
    baseline_metrics = count_metrics(actual, [r['baseline'] for r in rows])
    parameters = fit_count_model(panel, years)
    return {'model_id':'fars-state-poisson-v1', 'method':'Poisson count regression with state intercepts and a shared linear year trend',
            'target':'annual fatal crashes per state', 'trained_years':years,
            'prediction_year':parameters['prediction_year'], 'parameters':parameters,
            'evaluation':{'protocol':'retrospective temporal holdout; fixed specification, no holdout tuning',
                          'train_years':train, 'test_year':test, 'states_count':len(rows),
                          'model':model_metrics, 'baseline':baseline_metrics,
                          'baseline_method':'previous-year count per state', 'rows':rows,
                          'model_better_mae':model_metrics['mae'] < baseline_metrics['mae'],
                          'availability_note':'All input archives were retrieved in 2026; this is a reconstructed historical split, not a forecast issued in 2023.'},
            'limitations':['Only four annual observations per state; common trend cannot capture local changes.',
                           '2025 projection is frozen historical extrapolation, not a current-year prediction.',
                           'No traffic exposure denominator, causal interpretation, operational safety certification or calibrated prediction interval.',
                           'The held-out baseline comparison is reported even when the model loses; no performance guarantee.']}


def build_snapshot(source_root, destination):
    import numpy as np
    import pandas as pd
    source_root, destination = Path(source_root), Path(destination)
    crash_path = source_root / 'crashes.parquet'
    manifest_path = source_root / 'fars-manifest.json'
    behavior_path = source_root / 'behavior.json'
    crashes = pd.read_parquet(crash_path)
    if crashes.empty or crashes.crash_id.duplicated().any():
        raise ValueError('Missing or duplicate crash identities')
    if set(crashes.source) != {'fars'} or set(crashes.outcome) != {'fatal_crash'}:
        raise ValueError('Public release accepts only FARS fatal crashes')
    if not set(crashes.state_fips).issubset(STATE_NAMES) or (crashes.fatalities < 1).any():
        raise ValueError('Invalid state or fatality count')
    years = sorted(int(y) for y in crashes.year.unique())
    if years != list(range(years[0], years[-1]+1)):
        raise ValueError('Annual source coverage must be contiguous')
    sources = json.loads(manifest_path.read_text())
    if sorted(s['year'] for s in sources) != years:
        raise ValueError('Source years do not match data')
    for source in sources:
        if source['source'] != 'fars' or int(source['rows']) != int((crashes.year == source['year']).sum()):
            raise ValueError('Source row counts do not match data')
        if not source['url'].startswith('https://static.nhtsa.gov/nhtsa/downloads/FARS/'):
            raise ValueError('Unexpected public source URL')
    crash_hash = digest(crash_path)
    behavior = json.loads(behavior_path.read_text())
    if behavior['snapshot_inputs']['crashes_sha256'] != crash_hash:
        raise ValueError('Behavior cohorts have stale crash lineage')
    if behavior['years'] != years or [(s['year'],s['sha256']) for s in behavior['sources']] != [(s['year'],s['sha256']) for s in sources]:
        raise ValueError('Behavior source archives do not match')
    located = crashes.lat.between(-90,90) & crashes.lng.between(-180,180) & np.isfinite(crashes.lat) & np.isfinite(crashes.lng)
    crashes['located'] = located
    panel = crashes.groupby(['state_fips','year']).agg(fatal_crashes=('crash_id','size'), fatalities=('fatalities','sum'),located_crashes=('located','sum')).reset_index()
    panel = panel.sort_values(['state_fips','year'])
    centroids = crashes[located].groupby('state_fips')[['lat','lng']].mean()
    states = [{'state_fips':int(s), 'state_name':STATE_NAMES[int(s)],
               'lat':round(float(centroids.loc[s,'lat']),4), 'lng':round(float(centroids.loc[s,'lng']),4)} for s in sorted(crashes.state_fips.unique())]
    valid = crashes[located].copy()
    cell_degrees, min_count = .25, 5
    valid['lat_bin'] = np.floor(valid.lat / cell_degrees).astype(int)
    valid['lng_bin'] = np.floor(valid.lng / cell_degrees).astype(int)
    grid = valid.groupby(['state_fips','year','lat_bin','lng_bin']).agg(fatal_crashes=('crash_id','size'), fatalities=('fatalities','sum')).reset_index()
    visible = grid[grid.fatal_crashes >= min_count]
    cells = [{'state_fips':int(r.state_fips), 'year':int(r.year),
              'lat':float((r.lat_bin+.5)*cell_degrees), 'lng':float((r.lng_bin+.5)*cell_degrees),
              'fatal_crashes':int(r.fatal_crashes), 'fatalities':int(r.fatalities)} for r in visible.itertuples()]
    model = build_model(panel, years)
    for cohort in behavior['cohorts']:
        selected = crashes
        if cohort['state_fips'] is not None:
            selected = selected[selected.state_fips == cohort['state_fips']]
        if cohort['year'] is not None:
            selected = selected[selected.year == cohort['year']]
        if cohort['fatal_crashes'] != len(selected):
            raise ValueError('Behavior cohort count mismatch')
        for factor in cohort['factors'].values():
            if sum(factor[k] for k in ['yes','no','unknown','not_applicable']) != len(selected):
                raise ValueError('Behavior factor denominator mismatch')
    artifact = {
        'schema_version':1, 'kind':'public_fars_aggregate_release',
        'built_at':datetime.now(timezone.utc).isoformat(),
        'meta':{'schema_version':1, 'years':years, 'total_crashes':len(crashes),
                'total_fatalities':int(crashes.fatalities.sum()), 'states_count':len(states),
                'data_as_of':f'{years[-1]}-12-31', 'sources':[dict(s,name='NHTSA FARS') for s in sources],
                'source_documentation':'https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars',
                'limitations':LIMITATIONS, 'map':{'cell_degrees':cell_degrees,'min_count':min_count},
                'model_id':model['model_id'], 'data_mode':'real_federal_historical_aggregates',
                'source_sha256':crash_hash, 'behavior_sha256':digest(behavior_path)},
        'states':states, 'summary_rows':json.loads(panel.to_json(orient='records')), 'cells':cells,
        'model':model,
        'behaviors':{'cohorts':behavior['cohorts'], 'definitions':behavior['definitions'], 'limitations':behavior['limitations']},
    }
    artifact['meta']['built_at'] = artifact['built_at']
    validate_snapshot(artifact)
    destination.mkdir(parents=True,exist_ok=True)
    target = destination / 'snapshot.json'
    target.write_text(json.dumps(artifact,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
    return artifact


def validate_snapshot(value):
    """Fail closed on wrong product, inconsistent totals or unsafe model parameters."""
    if value.get('schema_version') != 1 or value.get('kind') != 'public_fars_aggregate_release':
        raise ValueError('Not a public FARS release')
    def finite(item):
        if isinstance(item,float) and not math.isfinite(item):
            raise ValueError('Nonfinite artifact number')
        if isinstance(item,dict):
            for child in item.values(): finite(child)
        if isinstance(item,list):
            for child in item: finite(child)
    finite(value)
    meta, states, rows, model = value['meta'],value['states'],value['summary_rows'],value['model']
    years = meta['years']
    ids = {s['state_fips'] for s in states}
    if not ids or len(ids) != len(states) or meta['states_count'] != len(ids):
        raise ValueError('Invalid state coverage')
    if not ids.issubset(STATE_NAMES) or years != sorted(set(years)) or len(years)<3:
        raise ValueError('Invalid state or year domain')
    expected = {(s,y) for s in ids for y in years}
    if set((r['state_fips'],r['year']) for r in rows) != expected or len(rows)!=len(expected):
        raise ValueError('Incomplete annual panel')
    for r in rows:
        if any(type(r[k]) is not int or r[k]<0 for k in ['fatal_crashes','fatalities','located_crashes']):
            raise ValueError('Counts must be nonnegative integers')
        if r['fatalities']<r['fatal_crashes'] or r['located_crashes']>r['fatal_crashes']:
            raise ValueError('Inconsistent fatal-crash counts')
    if sum(r['fatal_crashes'] for r in rows)!=meta['total_crashes'] or sum(r['fatalities'] for r in rows)!=meta['total_fatalities']:
        raise ValueError('Inconsistent national totals')
    min_count = meta['map']['min_count']
    if min_count != 5 or meta['map']['cell_degrees'] != .25:
        raise ValueError('Unsupported map aggregation')
    for cell in value['cells']:
        if (cell['state_fips'],cell['year']) not in expected or cell['fatal_crashes']<min_count or cell['fatalities']<cell['fatal_crashes']:
            raise ValueError('Invalid or insufficiently aggregated map cell')
        if not (-90<=cell['lat']<=90 and -180<=cell['lng']<=180):
            raise ValueError('Invalid map coordinate')
    for r in rows:
        mapped = sum(c['fatal_crashes'] for c in value['cells'] if c['state_fips']==r['state_fips'] and c['year']==r['year'])
        if mapped>r['located_crashes']:
            raise ValueError('Map totals exceed source coverage')
    p = model['parameters']
    if set(p['state_intercepts']) != {str(s) for s in ids} or p['trained_years']!=years or p['prediction_year']!=max(years)+1 or p['year_origin']!=min(years):
        raise ValueError('Invalid model lineage')
    if abs(p['year_coefficient'])>.5:
        raise ValueError('Unsupported trend coefficient')
    for s in ids:
        if not 0<predict_count(p,s,p['prediction_year'])<1e7:
            raise ValueError('Invalid count mean')
    evaluation = model['evaluation']
    if evaluation['train_years'] != years[:-1] or evaluation['test_year']!=years[-1]:
        raise ValueError('Invalid holdout lineage')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='data/safety')
    parser.add_argument('--output',default='data/public')
    args = parser.parse_args()
    snapshot = build_snapshot(args.source,args.output)
    print(json.dumps({'fatal_crashes':snapshot['meta']['total_crashes'],'states':snapshot['meta']['states_count'],
                      'map_cells':len(snapshot['cells']),'evaluation':{k:v for k,v in snapshot['model']['evaluation'].items() if k!='rows'}},indent=2))


if __name__ == '__main__':
    main()

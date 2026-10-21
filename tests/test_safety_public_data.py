import copy
import json
import math

import pandas as pd
import pytest

from safety.public_data import build_model, count_metrics, fit_count_model, predict_count, validate_snapshot


@pytest.fixture
def public_artifact():
    rows = [{'state_fips':s,'year':y,'fatal_crashes':n,'fatalities':n+2,'located_crashes':n-1}
            for s,counts in [(31,[80,84,88,92]),(19,[100,105,110,115])]
            for y,n in zip([2021,2022,2023,2024],counts)]
    model = build_model(pd.DataFrame(rows),[2021,2022,2023,2024])
    cohorts = []
    for s in [None,19,31]:
        for y in [None,2021,2022,2023,2024]:
            n=sum(r['fatal_crashes'] for r in rows if (s is None or r['state_fips']==s) and (y is None or r['year']==y))
            cohorts.append({'scope':'national' if s is None else 'state','state_fips':s,'year':y,
                            'fatal_crashes':n,'factors':{'speeding':{'yes':10,'no':n-20,'unknown':10,'not_applicable':0,'total_cases':n,'known_cases':n-10,'fraction_among_known':10/(n-10)}}})
    return {'schema_version':1,'kind':'public_fars_aggregate_release','built_at':'2026-09-30T00:00:00Z',
            'meta':{'years':[2021,2022,2023,2024],'total_crashes':sum(r['fatal_crashes'] for r in rows),
                    'total_fatalities':sum(r['fatalities'] for r in rows),'states_count':2,
                    'map':{'cell_degrees':.25,'min_count':5},'limitations':['Test artifact']},
            'states':[{'state_fips':31,'state_name':'Nebraska','lat':41.,'lng':-97.},
                      {'state_fips':19,'state_name':'Iowa','lat':42.,'lng':-93.}],
            'summary_rows':rows,'cells':[{'state_fips':31,'year':2024,'lat':41.125,'lng':-97.125,'fatal_crashes':7,'fatalities':8}],
            'model':model,'behaviors':{'cohorts':cohorts,'definitions':{'speeding':{'label':'Recorded speeding'}},'limitations':['Not causal']}}


def test_fit_uses_only_explicit_training_years_and_positive_json_inference():
    panel=pd.DataFrame([{'state_fips':s,'year':y,'fatal_crashes':n} for s in [19,31]
                        for y,n in [(2021,100),(2022,110),(2023,121),(2024,99999)]])
    p=fit_count_model(panel,[2021,2022,2023])
    assert p['year_coefficient']==pytest.approx(math.log(1.1),abs=1e-6)
    assert predict_count(json.loads(json.dumps(p)),31,2024)==pytest.approx(133.1,abs=.001)
    panel.loc[panel.year==2024,'fatal_crashes']=1
    assert fit_count_model(panel,[2021,2022,2023])==p
    with pytest.raises(ValueError): predict_count(p,31,2026)
    with pytest.raises(ValueError): predict_count(p,99,2024)


def test_holdout_metrics_are_reproducible_and_not_refit_training_scores(public_artifact):
    model=public_artifact['model'];e=model['evaluation']
    assert e['train_years']==[2021,2022,2023] and e['test_year']==2024
    assert model['parameters']['trained_years']==[2021,2022,2023,2024]
    assert count_metrics([r['actual'] for r in e['rows']],[r['predicted'] for r in e['rows']])==e['model']
    assert e['baseline']==count_metrics([92,115],[88,110])
    assert '2026' in e['availability_note']


def test_counts_include_zero_without_log_nan():
    assert count_metrics([0,10],[1,10])['poisson_deviance']==pytest.approx(1)
    with pytest.raises(ValueError):count_metrics([1],[0])


@pytest.mark.parametrize('mutation',[
    lambda d:d.update(kind='private_safety_snapshot'),
    lambda d:d['meta'].update(total_crashes=999),
    lambda d:d['cells'][0].update(fatal_crashes=1),
    lambda d:d['cells'][0].update(lat=float('inf')),
    lambda d:d['model']['parameters'].update(prediction_year=2026),
    lambda d:d['model']['parameters'].update(year_coefficient=1),
    lambda d:d['model']['evaluation'].update(train_years=[2021,2022,2023,2024]),
    lambda d:d['summary_rows'].append(copy.deepcopy(d['summary_rows'][0])),
])
def test_artifact_fails_closed_on_wrong_provenance_or_counts(public_artifact,mutation):
    validate_snapshot(public_artifact)
    mutation(public_artifact)
    with pytest.raises(ValueError):validate_snapshot(public_artifact)


def test_fit_rejects_missing_years():
    panel=pd.DataFrame([{'state_fips':31,'year':2021,'fatal_crashes':2},{'state_fips':31,'year':2023,'fatal_crashes':3}])
    with pytest.raises(ValueError):fit_count_model(panel,[2021,2022,2023])

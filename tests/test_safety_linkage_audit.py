import gzip
import json
import math

import pytest
from pydantic import ValidationError
from shapely.geometry import LineString, Point
from shapely import to_wkb
from shapely.strtree import STRtree

from safety.linkage_audit import Reviews, Points, summarize_reviews
from safety.road_geometry import nearest, match_points, match_route, load_geometry, _PROJECT


SNAPSHOT = {'built_at':'2026-09-30','provenance':{'roads_sha256':'source'},'segments':[{'segment_id':'A'}]}


def test_review_precision_includes_uncertainty_and_unresolved_denominator():
    rows = [dict(case_id='a',proposed_segment_id='1',reviewed_segment_id='1',decision='correct'),
            dict(case_id='b',proposed_segment_id='1',reviewed_segment_id='2',decision='incorrect'),
            dict(case_id='c',decision='unresolved')]
    r = summarize_reviews(Reviews(reviews=rows),SNAPSHOT)
    assert r['precision_among_resolved'] == .5
    assert r['unresolved_fraction'] == pytest.approx(1/3)
    assert r['precision_wilson95'][0] < .5 < r['precision_wilson95'][1]
    rows[0]['case_id']='b'
    with pytest.raises(ValueError,match='Duplicate'):
        summarize_reviews(Reviews(reviews=rows),SNAPSHOT)


def test_unknown_reviews_are_not_accuracy_zero():
    r=summarize_reviews(Reviews(reviews=[dict(case_id='a',decision='unresolved')]),SNAPSHOT)
    assert r['precision_among_resolved'] is None and r['precision_wilson95'] is None


@pytest.mark.parametrize('row',[
    dict(case_id='a',decision='correct'),
    dict(case_id='a',decision='correct',proposed_segment_id='1',reviewed_segment_id='2'),
    dict(case_id='a',decision='incorrect',proposed_segment_id='1',reviewed_segment_id='1')])
def test_contradictory_manual_labels_rejected(row):
    with pytest.raises(ValidationError): Reviews(reviews=[row])


def test_parallel_roads_withheld_and_distance_bounded():
    roads=[LineString([(0,0),(100,0)]),LineString([(0,8),(100,8)])]
    idx=(['A','B'],roads,STRtree(roads))
    assert nearest(Point(40,4),idx)['status']=='ambiguous'
    assert nearest(Point(40,-1),idx)['segment_id']=='A'
    assert nearest(Point(40,100),idx)['status']=='outside_tolerance'


@pytest.fixture
def geometry(tmp_path):
    line=LineString([_PROJECT(-96.,41.),_PROJECT(-95.99,41.)])
    data={'schema_version':1,'metric_crs':'EPSG:26914','roads_sha256':'source',
          'simplification_tolerance_m':.5,'roads':[{'segment_id':'A','wkb':to_wkb(line,hex=True)}]}
    with gzip.open(tmp_path/'road-geometry.json.gz','wt') as f:json.dump(data,f)
    return tmp_path


def test_real_geometry_point_and_route_matching(geometry):
    result=match_points([{'case_id':'x','lat':41.,'lng':-95.995}],SNAPSHOT,geometry)
    assert result['results'][0]['segment_id']=='A'
    result=match_route([[-96.,41.],[-95.99,41.]],SNAPSHOT,geometry)
    assert result['coverage_fraction']==pytest.approx(1)
    assert result['matched_legs'][0]['length_miles'] > .5
    assert result['sample_spacing_m']<=50
    unknown=match_route([[-96.,41.01],[-95.99,41.01]],SNAPSHOT,geometry)
    assert unknown['coverage_fraction']==0 and unknown['unmatched_length_miles']>0


def test_geometry_lineage_guard(geometry):
    bad={**SNAPSHOT,'provenance':{'roads_sha256':'other'}}
    with pytest.raises(ValueError,match='bound'):
        load_geometry(geometry,bad)
    bad={**SNAPSHOT,'segments':[{'segment_id':'B'}]}
    # A new source identity with mismatched segment identities cannot load.
    from safety.road_geometry import _CACHE
    _CACHE.clear()
    with pytest.raises(ValueError,match='identities'):
        load_geometry(geometry,bad)


@pytest.mark.parametrize('coords',[[],[[0,0],[1,1]],[[True,41],[-96,41]],[[-96,41],[-96,41]],[[math.nan,41],[-96,41]]])
def test_invalid_or_out_of_region_route_rejected(geometry,coords):
    with pytest.raises(ValueError):match_route(coords,SNAPSHOT,geometry)


def test_point_request_rejects_nonfinite_coordinates():
    with pytest.raises(ValidationError):Points(records=[dict(case_id='x',lat=math.nan,lng=-96.)])

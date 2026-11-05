import gzip
import json

import pytest
from fastapi.testclient import TestClient

from safety import crash_points
from safety.public_api import create_app
from test_safety_public_data import public_artifact

FIELDS = ['id', 'year', 'month', 'day', 'day_week', 'hour', 'minute', 'state_fips', 'state', 'county', 'city', 'lat', 'lng',
          'fatals', 'persons', 'peds', 'vehicles', 'road', 'road2', 'route', 'area', 'func_sys', 'first_event', 'collision',
          'junction', 'intersection', 'relation', 'work_zone', 'light', 'weather', 'ems_notify_min', 'ems_arrive_min',
          'speeding', 'drinking', 'hit_run', 'rollover', 'vehicle_list']
CENTER = (41.2587, -96.0266)  # Omaha, 72nd & Dodge


def crash(n, lat, lng, year=2024, month=1, day=1, hour=12, fatals=1, peds=0, light='Daylight', speeding=False, drinking=False):
    values = {'id': f'{year}-{n}', 'year': year, 'month': month, 'day': day, 'day_week': 'Monday', 'hour': hour, 'minute': 0,
              'state_fips': 31, 'state': 'Nebraska', 'county': 'Douglas', 'city': 'Omaha', 'lat': lat, 'lng': lng,
              'fatals': fatals, 'persons': 2, 'peds': peds, 'vehicles': 1, 'light': light, 'speeding': speeding,
              'drinking': drinking, 'hit_run': False, 'rollover': False,
              'vehicle_list': [{'year': 2019, 'make': 'Ford', 'model': 'F-150', 'body': 'Pickup', 'speed_mph': None}]}
    return [values.get(f) for f in FIELDS]


def write_artifact(folder, rows):
    meta = {'source': 'synthetic test', 'years': [2021, 2022, 2023, 2024], 'count': len(rows), 'unlocated': 0,
            'built_at': '2026-11-05T00:00:00Z', 'fields': FIELDS}
    with gzip.open(folder/'crashes.jsonl.gz', 'wt', encoding='utf-8') as handle:
        handle.write(json.dumps(meta) + '\n')
        handle.writelines(json.dumps(r) + '\n' for r in rows)
    return folder/'crashes.jsonl.gz'


@pytest.fixture
def client(tmp_path, public_artifact):
    (tmp_path/'snapshot.json').write_text(json.dumps(public_artifact))
    write_artifact(tmp_path, [
        crash(1, *CENTER, year=2021, peds=1, light='Dark - Not Lighted'),
        crash(2, CENTER[0] + 0.01, CENTER[1], year=2024, month=6, fatals=2, speeding=True),   # ~1.1 km north
        crash(3, CENTER[0] + 0.05, CENTER[1], year=2023, drinking=True),                       # ~5.5 km north
        crash(4, 40.8136, -96.7026),                                                           # Lincoln, ~80 km
    ])
    return TestClient(create_app(root=tmp_path, enable_screening=False))


def test_radius_returns_only_crashes_inside_with_correct_distances(client):
    # Act
    body = client.get('/api/public/crashes', params={'lat': CENTER[0], 'lng': CENTER[1], 'r': 3}).json()

    # Assert
    assert body['total'] == 2 and {c['id'] for c in body['crashes']} == {'2021-1', '2024-2'}
    distances = {c['id']: c['distance_km'] for c in body['crashes']}
    assert distances['2021-1'] == 0 and distances['2024-2'] == pytest.approx(1.11, abs=0.01)
    assert body['crashes'][0]['vehicle_list'][0]['make'] == 'Ford'


def test_summary_counts_peds_speeding_drinking_dark_and_years(client):
    # Act
    summary = client.get('/api/public/crashes', params={'lat': CENTER[0], 'lng': CENTER[1], 'r': 10}).json()['summary']

    # Assert
    assert summary == {'fatal_crashes': 3, 'fatalities': 4, 'with_pedestrians': 1, 'speeding': 1, 'drinking': 1, 'dark': 1,
                       'by_year': {'2021': 1, '2022': 0, '2023': 1, '2024': 1}}


def test_crashes_are_sorted_newest_first(client):
    # Act
    ids = [c['id'] for c in client.get('/api/public/crashes', params={'lat': CENTER[0], 'lng': CENTER[1], 'r': 10}).json()['crashes']]

    # Assert
    assert ids == ['2024-2', '2023-3', '2021-1']


def test_summary_covers_all_hits_while_returning_only_500_nearest(tmp_path):
    # Arrange: 520 crashes on a line heading north, 0.001° (~111 m) apart
    rows = [crash(i, CENTER[0] + i * 0.0001, CENTER[1], year=2021 + i % 4) for i in range(520)]
    index = crash_points.load(write_artifact(tmp_path, rows))

    # Act
    body = crash_points.query(index, *CENTER, 25)

    # Assert
    assert body['total'] == 520 and body['summary']['fatal_crashes'] == 520
    assert body['returned'] == 500 and body['truncated'] is True
    assert max(c['distance_km'] for c in body['crashes']) < 520 * 0.0001 * 111.2


def test_radius_is_clamped_to_25_km_and_0_1_km(client):
    # Act
    wide = client.get('/api/public/crashes', params={'lat': CENTER[0], 'lng': CENTER[1], 'r': 500}).json()
    tiny = client.get('/api/public/crashes', params={'lat': CENTER[0], 'lng': CENTER[1], 'r': 0}).json()

    # Assert
    assert wide['radius_km'] == 25 and wide['total'] == 3
    assert tiny['radius_km'] == 0.1 and tiny['total'] == 1


@pytest.mark.parametrize('params', [{'lat': 91, 'lng': 0}, {'lat': 0, 'lng': -181}, {'lat': 'nan', 'lng': 0}, {'lng': 0}, {'lat': 1, 'lng': 2, 'r': 'inf'}])
def test_invalid_coordinates_are_rejected_with_422(client, params):
    assert client.get('/api/public/crashes', params=params).status_code == 422


def test_missing_artifact_is_503_on_endpoint_only_and_ready_still_works(tmp_path, public_artifact):
    # Arrange
    (tmp_path/'snapshot.json').write_text(json.dumps(public_artifact))
    client = TestClient(create_app(root=tmp_path, enable_screening=False))

    # Act / Assert
    missing = client.get('/api/public/crashes', params={'lat': 41, 'lng': -96})
    assert missing.status_code == 503
    assert missing.json() == {'detail': 'Crash point artifact is unavailable'}
    assert client.get('/ready').status_code == 200
    engines = {e['id']: e['status'] for e in client.get('/api/public/meta').json()['engines']}
    assert engines['fars-crash-points'] == 'unavailable'


def test_malformed_artifact_fails_load_with_value_error(tmp_path):
    with gzip.open(tmp_path/'crashes.jsonl.gz', 'wt') as handle:
        handle.write(json.dumps({'fields': ['id']}) + '\n')
    with pytest.raises(ValueError):
        crash_points.load(tmp_path/'crashes.jsonl.gz')


def test_config_returns_maps_key_from_environment(client, monkeypatch):
    # Arrange
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY', 'test-key-123')

    # Act / Assert
    assert client.get('/api/public/config').json() == {'googleMapsKey': 'test-key-123'}
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY')
    assert client.get('/api/public/config').json() == {'googleMapsKey': ''}


def test_by_year_lists_every_covered_year_including_zero_years(tmp_path):
    # Arrange: all three crashes in one year
    index = crash_points.load(write_artifact(tmp_path, [crash(i, *CENTER, year=2022) for i in range(3)]))

    # Act
    by_year = crash_points.query(index, *CENTER, 1)['summary']['by_year']

    # Assert: per-year rates divide by four years, not one
    assert by_year == {'2021': 0, '2022': 3, '2023': 0, '2024': 0}


def test_config_is_never_cached_so_key_changes_apply_immediately(client):
    # Act
    response = client.get('/api/public/config')

    # Assert
    assert response.headers['cache-control'] == 'no-store'

"""Build data/public/crashes.jsonl.gz, the per-crash FARS records behind place search.

    python3 scripts/build_crash_points.py <dir-with-FARS2021.zip..FARS2024.zip>

Reads accident.csv and vehicle.csv straight out of NHTSA's national CSV zips (no extraction).
Contract: docs/CRASH_POINTS.md. Stdlib only.
"""
import csv
import gzip
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/public/crashes.jsonl.gz'
YEARS = [2021, 2022, 2023, 2024]
FIELDS = ['id', 'year', 'month', 'day', 'day_week', 'hour', 'minute', 'state_fips', 'state', 'county', 'city', 'lat', 'lng',
          'fatals', 'persons', 'peds', 'vehicles', 'road', 'road2', 'route', 'area', 'func_sys', 'first_event', 'collision',
          'junction', 'intersection', 'relation', 'work_zone', 'light', 'weather', 'ems_notify_min', 'ems_arrive_min',
          'speeding', 'drinking', 'hit_run', 'rollover', 'vehicle_list']
UNKNOWN = {'', 'not reported', 'unknown', 'reported as unknown', 'not applicable'}
CODE_SUFFIX = re.compile(r'\s*\(\d+\)$')
MAX_VEHICLES, MAX_EMS_GAP_MIN = 6, 720
SPEEDING, ROLLED = {'2', '3', '4', '5'}, {'1', '2', '9'}


def rows(archive, year, table):
    with zipfile.ZipFile(archive) as z, z.open(f'FARS{year}NationalCSV/{table}.csv') as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding='latin-1'))
        reader.fieldnames = [name.removeprefix('\xef\xbb\xbf') for name in reader.fieldnames]  # UTF-8 BOM read as latin-1
        yield from reader


def clean(value, extra=()):
    value = value.strip()
    return None if value.lower() in UNKNOWN or value in extra else value


def place(value, extra=()):
    value = clean(CODE_SUFFIX.sub('', value), extra)
    return value.title() if value else None


def clock(hour, minute):
    """Minutes after midnight, or None for FARS unknown codes (88/98/99)."""
    h, m = int(hour), int(minute)
    return h * 60 + m if h < 24 and m < 60 else None


def gap(start, end):
    if start is None or end is None:
        return None
    minutes = (end - start) % 1440  # handles a midnight wrap
    return minutes if minutes <= MAX_EMS_GAP_MIN else None


def located(lat, lng):
    return lat != 0 and lng != 0 and abs(lat) < 77 and abs(lng) < 777  # 77.7777/88.8888/99.9999 = not reported/unknown


def vehicles(archive, year):
    """Per ST_CASE: involvement flags and up to MAX_VEHICLES vehicle summaries."""
    out = defaultdict(lambda: {'speeding': False, 'drinking': False, 'hit_run': False, 'rollover': False, 'list': []})
    for v in rows(archive, year, 'vehicle'):
        case = out[v['ST_CASE']]
        case['speeding'] |= v['SPEEDREL'] in SPEEDING
        case['drinking'] |= v['DR_DRINK'] == '1'
        case['hit_run'] |= v['HIT_RUN'] == '1'
        case['rollover'] |= v['ROLLOVER'] in ROLLED
        if len(case['list']) < MAX_VEHICLES:
            model_year, speed = int(v['MOD_YEAR']), int(v['TRAV_SP'])
            case['list'].append({'year': None if model_year >= 9998 else model_year,
                                 'make': clean(v['VPICMAKENAME']) or clean(v['MAKENAME']), 'model': clean(v['VPICMODELNAME']),
                                 'body': clean(v['BODY_TYPNAME']), 'speed_mph': None if speed >= 997 else speed})
    return out


def crash(a, year, v):
    start = clock(a['HOUR'], a['MINUTE'])
    hour, minute = int(a['HOUR']), int(a['MINUTE'])
    return [f'{year}-{a["ST_CASE"]}', year, int(a['MONTH']), int(a['DAY']), clean(a['DAY_WEEKNAME']),
            hour if hour < 24 else None, minute if minute < 60 else None,
            int(a['STATE']), place(a['STATENAME']), place(a['COUNTYNAME']), place(a['CITYNAME'], extra={'Other'}),
            round(float(a['LATITUDE']), 5), round(float(a['LONGITUD']), 5),
            int(a['FATALS']), int(a['PERSONS']), int(a['PEDS']), int(a['VE_TOTAL']),
            clean(a['TWAY_ID'], {'NONE'}), clean(a['TWAY_ID2'], {'NONE'}), clean(a['ROUTENAME']),
            clean(a['RUR_URBNAME']), clean(a['FUNC_SYSNAME']), clean(a['HARM_EVNAME']), clean(a['MAN_COLLNAME']),
            clean(a['RELJCT2NAME']), clean(a['TYP_INTNAME']), clean(a['REL_ROADNAME']), clean(a['WRK_ZONENAME']),
            clean(a['LGT_CONDNAME']), clean(a['WEATHERNAME']),
            gap(start, clock(a['NOT_HOUR'], a['NOT_MIN'])), gap(start, clock(a['ARR_HOUR'], a['ARR_MIN'])),
            v['speeding'], v['drinking'], v['hit_run'], v['rollover'], v['list']]


def build(source):
    crashes, unlocated = [], 0
    for year in YEARS:
        archive = source / f'FARS{year}.zip'
        involved = vehicles(archive, year)
        for a in rows(archive, year, 'accident'):
            if not located(float(a['LATITUDE']), float(a['LONGITUD'])):
                unlocated += 1
                continue
            crashes.append(crash(a, year, involved[a['ST_CASE']]))
    return crashes, unlocated


def main():
    crashes, unlocated = build(Path(sys.argv[1]))
    meta = {'source': 'NHTSA FARS 2021–2024 national CSV (accident + vehicle) · US public domain · fatal crashes only',
            'years': YEARS, 'count': len(crashes), 'unlocated': unlocated,
            'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'fields': FIELDS}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, 'wt', encoding='utf-8') as f:
        f.write(json.dumps(meta, ensure_ascii=False) + '\n')
        for row in crashes:
            f.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')

    lat, lng = FIELDS.index('lat'), FIELDS.index('lng')
    assert all(len(r) == len(FIELDS) for r in crashes)
    assert all(17 < r[lat] < 72 and -180 < r[lng] < -64 for r in crashes), '50 states + DC only'
    assert len({r[0] for r in crashes}) == len(crashes), 'ids unique'
    assert len(crashes) + unlocated == 153_273, 'FARS 2021–2024 national crash total'
    print(f'{OUT.relative_to(ROOT)}: {len(crashes):,} crashes, {unlocated:,} unlocated, {OUT.stat().st_size / 1e6:.1f} MB')


if __name__ == '__main__':
    main()

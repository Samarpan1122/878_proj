# Crash points: per-crash FARS records behind place search

Source: NHTSA FARS 2021–2024 national CSV (`accident.csv` + `vehicle.csv`), US federal public-domain data.
Fatal crashes only. Coordinates are as recorded by FARS; unlocated crashes are counted but not served.

## Artifact — `data/public/crashes.jsonl.gz`

Built by `scripts/build_crash_points.py <dir-with-FARS{year}.zip>`. Gzipped JSON Lines:

- line 1: meta object `{"source", "years": [2021,2022,2023,2024], "count", "unlocated", "built_at" (ISO-8601 UTC), "fields": [...]}`
- every further line: one crash as a JSON array, values in `fields` order.

`fields` (in this exact order):

| field | type | meaning |
|---|---|---|
| id | str | `"{year}-{ST_CASE}"` (ST_CASE is unique only within a year) |
| year, month, day | int | crash date |
| day_week | str | e.g. `"Monday"` |
| hour, minute | int\|null | null when FARS reports unknown (98/99) |
| state_fips | int | |
| state, county, city | str\|null | names, title case, FARS code suffix like `" (125)"` stripped; `NOT APPLICABLE`/unknown → null |
| lat, lng | float | 5 decimals |
| fatals, persons, peds, vehicles | int | FATALS, PERSONS, PEDS, VE_TOTAL |
| road, road2, route | str\|null | TWAY_ID, TWAY_ID2, ROUTENAME |
| area, func_sys | str\|null | RUR_URBNAME, FUNC_SYSNAME |
| first_event, collision | str\|null | HARM_EVNAME, MAN_COLLNAME |
| junction, intersection, relation, work_zone | str\|null | RELJCT2NAME, TYP_INTNAME, REL_ROADNAME, WRK_ZONENAME |
| light, weather | str\|null | LGT_CONDNAME, WEATHERNAME |
| ems_notify_min, ems_arrive_min | int\|null | minutes from crash to EMS notification / arrival; null if any time unknown or the gap exceeds 12 h (midnight wrap handled) |
| speeding, drinking, hit_run, rollover | bool | any vehicle: SPEEDREL ∈ {2,3,4,5}; DR_DRINK = 1; HIT_RUN = 1; ROLLOVER ∈ {1,2,9} |
| vehicle_list | list | up to 6 × `{"year": int\|null, "make": str\|null, "model": str\|null, "body": str\|null, "speed_mph": int\|null}` (VPIC names preferred, MAKENAME fallback; MOD_YEAR 9998/9999 → null; TRAV_SP ≥ 997 → null) |

Values such as `Not Reported`, `Unknown`, `Reported as Unknown` become null.

## API

`GET /api/public/crashes?lat=&lng=&r=` — r in km, default 3, clamped to 0.1–25. 422 for lat outside [-90, 90] or lng outside [-180, 180]; 503 when the artifact is missing or invalid.

```json
{"center": {"lat": 41.2587, "lng": -96.0266}, "radius_km": 3, "years": "2021–2024",
 "source": "NHTSA FARS 2021–2024 · fatal crashes only", "total": 41, "returned": 41, "truncated": false,
 "summary": {"fatal_crashes": 41, "fatalities": 44, "with_pedestrians": 9, "speeding": 12, "drinking": 7,
             "dark": 22, "by_year": {"2021": 10, "2022": 12, "2023": 9, "2024": 10}},
 "crashes": [{"id": "2024-310123", "distance_km": 0.42, "...every field above...": "..."}]}
```

The summary covers every crash in the radius. `crashes` holds at most the 500 nearest (`truncated` true when there are more), sorted newest first. `dark` counts `light` values starting with `Dark`. `by_year` lists every covered year, including years with zero crashes.

`GET /api/public/config` → `{"googleMapsKey": "<GOOGLE_MAPS_API_KEY env or empty>"}`. Restrict the key by HTTP referrer to the site's domain.

Memory budget: under ~120 MB for the whole index. Keep coordinates in numpy arrays and each crash as its raw JSON line, decoded only when returned.

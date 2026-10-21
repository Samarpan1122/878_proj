"""Descriptive FARS behavior cohorts, never pre-crash propensity predictions."""
import math
import zipfile
from pathlib import Path

import pandas as pd

from safety.io import digest

KEY = ["STATE", "ST_CASE"]
VEHICLE_KEY = KEY + ["VEH_NO"]
FACTORS = {
    "speeding": {"label": "Recorded speeding involvement", "positive_codes": [2, 3, 4, 5],
        "negative_codes": [0], "unknown_codes": [9], "not_applicable_codes": [8], "column": "SPEEDREL"},
    "reported_alcohol": {"label": "Police-reported driver alcohol involvement", "positive_codes": [1],
        "negative_codes": [0], "unknown_codes": [8, 9], "not_applicable_codes": [], "column": "DRINKING"},
    "distraction": {"label": "Explicitly recorded driver distraction", "positive_codes": [3, 4, 5, 6, 7, 9, 10, 12, 13, 14, 15, 92, 97, 98],
        "negative_codes": [0], "unknown_codes": [17, 18, 19, 93, 96, 99], "not_applicable_codes": [16], "column": "DRDISTRACT"},
}


def _read(archive, table, required, optional=()):
    names = [name for name in archive.namelist() if Path(name).name.lower() == table]
    if len(names) != 1 or archive.getinfo(names[0]).file_size > 300_000_000:
        raise ValueError(f"Expected one bounded FARS {table} table")
    with archive.open(names[0]) as stream:
        frame = pd.read_csv(stream, encoding="utf-8-sig", usecols=lambda c: c in set(required) | set(optional), low_memory=False)
    if missing := set(required) - set(frame):
        raise ValueError(f"FARS {table} missing columns: {sorted(missing)}")
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if (frame[column].isna().any() or frame[column].isin([float("inf"), float("-inf")]).any()
                or not frame[column].eq(frame[column].round()).all()):
            raise ValueError(f"FARS {table} invalid integer column {column}")
    return frame


def _unique(frame, keys, name):
    if frame.duplicated(keys).any():
        raise ValueError(f"Duplicate {name} identifiers")


def _coverage(child, parent, keys, name):
    joined = child[keys].drop_duplicates().merge(parent[keys], on=keys, how="left", indicator=True)
    if joined._merge.ne("both").any():
        raise ValueError(f"Orphan {name} records outside parent table")


def _classify(series, factor):
    definition = FACTORS[factor]
    result = pd.Series("unknown", index=series.index)
    for field, label in [("negative_codes", "no"), ("not_applicable_codes", "not_applicable"), ("positive_codes", "yes")]:
        result.loc[series.isin(definition[field])] = label
    return result


def _collapse(frame, keys, expected=None):
    """Any recorded positive wins; a negative requires complete negative evidence."""
    values = frame[keys].copy()
    for label in ["yes", "no", "unknown", "not_applicable"]:
        values[label] = frame.status.eq(label).astype(int)
    counts = values.groupby(keys, sort=False).sum()
    totals = counts.sum(axis=1) if expected is None else expected.reindex(counts.index)
    result = pd.Series("unknown", index=counts.index)
    result.loc[counts["no"].eq(totals) & totals.gt(0)] = "no"
    result.loc[counts.not_applicable.eq(totals) & totals.gt(0)] = "not_applicable"
    result.loc[counts.yes.gt(0)] = "yes"
    return result


def _year_records(archive_path, year):
    with zipfile.ZipFile(archive_path) as archive:
        accidents = _read(archive, "accident.csv", KEY + ["YEAR", "VE_FORMS"])
        vehicles = _read(archive, "vehicle.csv", VEHICLE_KEY + ["SPEEDREL"], ["SPEEDRELNAME"])
        people = _read(archive, "person.csv", VEHICLE_KEY + ["PER_NO", "PER_TYP", "DRINKING"], ["DRINKINGNAME"])
        distractions = _read(archive, "distract.csv", VEHICLE_KEY + ["DRDISTRACT"], ["DRDISTRACTNAME"])
    if accidents.empty or not accidents.YEAR.eq(year).all() or accidents.VE_FORMS.lt(0).any():
        raise ValueError("FARS year mismatch, empty archive, or invalid expected vehicle counts")
    if not accidents.STATE.between(1, 78).all() or not (accidents.ST_CASE // 10000).eq(accidents.STATE).all():
        raise ValueError("Invalid FARS state/crash identity")
    if vehicles.VEH_NO.le(0).any():
        raise ValueError("Invalid FARS vehicle identity")
    _unique(accidents, KEY, "crash")
    _unique(vehicles, VEHICLE_KEY, "vehicle")
    _unique(people, VEHICLE_KEY + ["PER_NO"], "person")
    _coverage(vehicles, accidents, KEY, "vehicle")
    _coverage(people, accidents, KEY, "person")
    drivers = people[people.PER_TYP.eq(1)].copy()
    _unique(drivers, VEHICLE_KEY, "driver")
    _coverage(drivers, vehicles, VEHICLE_KEY, "driver")
    _coverage(distractions, vehicles, VEHICLE_KEY, "distraction")
    expected = accidents.set_index(KEY).VE_FORMS
    actual = vehicles.groupby(KEY).size().reindex(expected.index, fill_value=0)
    if actual.gt(expected).any():
        raise ValueError("Vehicle rows exceed declared crash vehicle counts")
    evidence = {}
    for factor, source in [("speeding", vehicles), ("reported_alcohol", drivers), ("distraction", distractions)]:
        field = FACTORS[factor]["column"]
        evidence[factor] = {"column": field, "observed_codes": sorted(source[field].unique().astype(int).tolist())}
        if field + "NAME" in source:
            labels = source[[field, field + "NAME"]].drop_duplicates().sort_values(field)
            evidence[factor]["archive_labels"] = [{"code": int(row[field]), "label": str(row[field + "NAME"])} for _, row in labels.iterrows()]
    vehicle_status = vehicles[VEHICLE_KEY].copy()
    vehicle_status["speeding"] = _classify(vehicles.SPEEDREL, "speeding")
    alcohol = drivers[VEHICLE_KEY].copy()
    alcohol["reported_alcohol"] = _classify(drivers.DRINKING, "reported_alcohol")
    vehicle_status = vehicle_status.merge(alcohol, on=VEHICLE_KEY, how="left", validate="one_to_one")
    # Multiple different distraction codes per vehicle are expected. Duplicate
    # copies of the same factor cannot change a vehicle's or crash's denominator.
    distractions = distractions.drop_duplicates(VEHICLE_KEY + ["DRDISTRACT"])
    distractions["status"] = _classify(distractions.DRDISTRACT, "distraction")
    dist = _collapse(distractions, VEHICLE_KEY).rename("distraction")
    vehicle_status = vehicle_status.join(dist, on=VEHICLE_KEY, validate="one_to_one")
    vehicle_status = vehicle_status.fillna({"reported_alcohol": "unknown", "distraction": "unknown"})
    result = accidents[KEY].copy()
    result["year"] = year
    for factor in FACTORS:
        collapsed = _collapse(vehicle_status[VEHICLE_KEY + [factor]].rename(columns={factor: "status"}), KEY, expected)
        result = result.join(collapsed.rename(factor), on=KEY)
        result[factor] = result[factor].fillna("unknown")
    quality = {"year": year, "fatal_crashes": len(accidents), "vehicles": len(vehicles),
        "crashes_with_missing_vehicle_rows": int(actual.lt(expected).sum()),
        "missing_vehicle_rows": int((expected - actual).sum()),
        "vehicles_without_driver_person_record": int(len(vehicles) - len(drivers)),
        "vehicles_without_distraction_record": int(len(vehicles) - len(dist))}
    return result, quality, evidence


def _factor_stats(series):
    counts = series.value_counts()
    result = {name: int(counts.get(name, 0)) for name in ["yes", "no", "unknown", "not_applicable"]}
    known = result["yes"] + result["no"]
    interval, fraction = None, None
    if known:
        fraction = result["yes"] / known
        z = 1.959963984540054
        denominator = 1 + z * z / known
        center = (fraction + z * z / (2 * known)) / denominator
        half = z * math.sqrt(fraction * (1 - fraction) / known + z * z / (4 * known * known)) / denominator
        interval = [max(0.0, center - half), min(1.0, center + half)]
    return {**result, "known_cases": known, "total_cases": len(series),
            "fraction_among_known": fraction, "known_fraction_interval95": interval}


def build_behavior_report(archive_dir, years):
    """Read official local archives and return national/state/year aggregates only."""
    years = sorted(set(years))
    if not years or any(isinstance(year, bool) or year not in range(2021, 2025) for year in years):
        raise ValueError("Behavior code mappings are verified only for FARS 2021–2024")
    frames, quality, sources = [], [], []
    for year in years:
        archive = Path(archive_dir) / f"geocrash-fars{year}.zip"
        frame, check, evidence = _year_records(archive, year)
        frames.append(frame)
        quality.append(check)
        sources.append({"year": year, "url": f"https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip",
            "sha256": digest(archive), "codebook_evidence": evidence})
    data = pd.concat(frames, ignore_index=True)
    cohorts = []
    for state in [None] + sorted(data.STATE.unique().astype(int).tolist()):
        subset = data if state is None else data[data.STATE.eq(state)]
        for year in [None] + years:
            cohort = subset if year is None else subset[subset.year.eq(year)]
            cohorts.append({"scope": "national" if state is None else "state", "state_fips": state,
                "year": year, "fatal_crashes": len(cohort),
                "factors": {factor: _factor_stats(cohort[factor]) for factor in FACTORS}})
    return {"schema_version": 1, "kind": "descriptive_fatal_crash_cohorts", "years": years,
        "sources": sources, "quality": quality, "definitions": FACTORS, "cohorts": cohorts,
        "codebook": {"url": "https://crashstats.nhtsa.dot.gov/Api/Public/ViewPublication/813794",
                     "title": "FARS Analytical User's Manual, 1975–2024", "pages": {"reported_alcohol": 313, "distraction": [552, 553, 554]}},
        "limitations": [
            "Descriptive reports among fatal crashes only; not driver-population prevalence, causal effects, or future crash propensity.",
            "Police-reported alcohol is officer judgment, not BAC measurement or a statement that alcohol caused a crash.",
            "A crash is positive if any linked vehicle is positive; negative requires every expected vehicle to be recorded negative. Missing or conflicting records remain unknown.",
            "Not applicable includes codes combining no driver with unknown driver presence. Mixed negative/not-applicable vehicles remain unknown.",
            "Distraction codes 17/18/19/93 are conservatively left unknown; this explicitly recorded subset does not reproduce NHTSA's official distraction-related totals.",
            "Wilson intervals describe the known-case fraction only. They do not account for selective reporting, missingness, or ascertainment bias; FARS is a census of recorded fatal crashes.",
            "No person identifiers, raw records, driver profiles, or inferred behavioral traits are exposed by this aggregate report."]}

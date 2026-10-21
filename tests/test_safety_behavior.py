import io
import json
import zipfile
from unittest.mock import MagicMock

import pandas as pd
import pytest

from safety.behavior import _read, build_behavior_report


def tables():
    accidents = pd.DataFrame({"STATE": [31, 31, 31, 6, 31, 31],
        "ST_CASE": [310001, 310002, 310003, 60001, 310004, 310005],
        "YEAR": [2024] * 6, "VE_FORMS": [2, 2, 1, 1, 2, 0]})
    vehicles = pd.DataFrame({"STATE": [31, 31, 31, 31, 31, 6, 31],
        "ST_CASE": [310001, 310001, 310002, 310002, 310003, 60001, 310004],
        "VEH_NO": [1, 2, 1, 2, 1, 1, 1], "SPEEDREL": [0, 9, 2, 9, 8, 0, 0]})
    vehicles["SPEEDRELNAME"] = vehicles.SPEEDREL.map({0: "No", 9: "Reported as Unknown", 2: "Yes, Racing", 8: "No Driver Present/Unknown if Driver Present"})
    people = vehicles.drop(index=4)[["STATE", "ST_CASE", "VEH_NO"]].copy()
    people["PER_NO"], people["PER_TYP"] = 1, 1
    people["DRINKING"] = [0, 8, 1, 9, 0, 0]
    people["DRINKINGNAME"] = people.DRINKING.map({0: "No (Alcohol Not Involved)", 1: "Yes (Alcohol Involved)", 8: "Not Reported", 9: "Reported as Unknown"})
    distractions = vehicles[["STATE", "ST_CASE", "VEH_NO"]].copy()
    distractions["DRDISTRACT"] = [0, 96, 3, 99, 16, 0, 0]
    distractions = pd.concat([distractions, distractions.iloc[[2]], distractions.iloc[[2]].assign(DRDISTRACT=96)], ignore_index=True)
    distractions["DRDISTRACTNAME"] = distractions.DRDISTRACT.map({0: "Not Distracted", 3: "By Other Occupant(s)", 16: "No Driver Present/Unknown if Driver present", 96: "Not Reported", 99: "Reported as Unknown if Distracted"})
    return {"accident.csv": accidents, "vehicle.csv": vehicles, "person.csv": people, "distract.csv": distractions}


def archive(folder, data, year=2024):
    with zipfile.ZipFile(folder / f"geocrash-fars{year}.zip", "w") as zipped:
        for name, frame in data.items():
            zipped.writestr(name, frame.to_csv(index=False).encode("utf-8-sig"))


def test_crash_denominators_positive_unknown_missing_and_na(tmp_path):
    archive(tmp_path, tables())
    report = build_behavior_report(tmp_path, [2024])
    assert report["schema_version"] == 1
    total = report["cohorts"][0]
    assert total["scope"] == "national" and total["year"] is None
    assert total["fatal_crashes"] == 6
    for factor in ["speeding", "distraction"]:
        stats = total["factors"][factor]
        assert [stats[k] for k in ["yes", "no", "unknown", "not_applicable"]] == [1, 1, 3, 1]
        assert stats["known_cases"] == 2 and stats["fraction_among_known"] == 0.5
        assert stats["known_fraction_interval95"][0] < 0.5 < stats["known_fraction_interval95"][1]
    assert total["factors"]["reported_alcohol"]["unknown"] == 4
    nebraska = next(c for c in report["cohorts"] if c["state_fips"] == 31 and c["year"] is None)
    assert nebraska["fatal_crashes"] == 5
    assert nebraska["factors"]["speeding"]["no"] == 0
    assert report["quality"][0]["missing_vehicle_rows"] == 1
    assert report["quality"][0]["vehicles_without_driver_person_record"] == 1
    assert report["sources"][0]["sha256"] and report["sources"][0]["codebook_evidence"]["speeding"]["archive_labels"]
    json.dumps(report, allow_nan=False)


def test_ambiguous_distraction_and_missing_person_are_not_negative(tmp_path):
    data = tables()
    data["distract.csv"]["DRDISTRACT"] = 17
    data["person.csv"]["PER_TYP"] = 2  # Passengers must not classify drivers.
    archive(tmp_path, data)
    stats = build_behavior_report(tmp_path, [2024])["cohorts"][0]["factors"]
    assert stats["distraction"]["unknown"] == 6 and stats["distraction"]["known_cases"] == 0
    assert stats["distraction"]["known_fraction_interval95"] is None
    assert stats["reported_alcohol"]["unknown"] == 6


@pytest.mark.parametrize("kind", ["crash", "vehicle", "person", "driver", "orphan_vehicle", "orphan_driver", "orphan_distraction", "excess_vehicles", "wrong_year", "bad_state", "bad_vehicle", "bad_integer"])
def test_invalid_relationships_fail_loudly(tmp_path, kind):
    data = tables()
    duplicate = {"crash": "accident.csv", "vehicle": "vehicle.csv", "person": "person.csv", "driver": "person.csv"}
    if kind in duplicate:
        key = duplicate[kind]
        extra = data[key].iloc[[0]].copy()
        if kind == "driver":
            extra["PER_NO"] = 2
        data[key] = pd.concat([data[key], extra], ignore_index=True)
    elif kind == "orphan_vehicle":
        data["vehicle.csv"].loc[0, "ST_CASE"] = 319999
    elif kind == "orphan_driver":
        data["person.csv"].loc[0, "VEH_NO"] = 99
    elif kind == "orphan_distraction":
        data["distract.csv"].loc[0, "VEH_NO"] = 99
    elif kind == "excess_vehicles":
        data["accident.csv"].loc[0, "VE_FORMS"] = 1
    elif kind == "wrong_year":
        data["accident.csv"].loc[0, "YEAR"] = 2023
    elif kind == "bad_state":
        data["accident.csv"].loc[0, "STATE"] = 0
    elif kind == "bad_vehicle":
        data["vehicle.csv"].loc[0, "VEH_NO"] = 0
    else:
        data["vehicle.csv"]["SPEEDREL"] = 0.5
    archive(tmp_path, data)
    with pytest.raises(ValueError):
        build_behavior_report(tmp_path, [2024])


def test_years_schema_and_size_guard(tmp_path):
    for years in [[], [2020], [True]]:
        with pytest.raises(ValueError):
            build_behavior_report(tmp_path, years)
    data = tables()
    del data["vehicle.csv"]["SPEEDREL"]
    archive(tmp_path, data)
    with pytest.raises(ValueError, match="missing columns"):
        build_behavior_report(tmp_path, [2024])
    fake = MagicMock()
    fake.namelist.return_value = ["vehicle.csv"]
    fake.getinfo.return_value.file_size = 300_000_001
    with pytest.raises(ValueError, match="bounded"):
        _read(fake, "vehicle.csv", ["STATE"])

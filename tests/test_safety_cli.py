import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from safety.cli import build, main, pipeline_lock
from safety.io import write_json


def inputs(root):
    roads = gpd.GeoDataFrame({"segment_id": [f"S{i}" for i in range(12)],
        "route": [f"R{i}" for i in range(12)], "aadt": [1000 + i * 100 for i in range(12)],
        "aadt_year": [2025] * 12, "length_miles": [1.] * 12,
        "lat": [41. + i * .03 for i in range(12)], "lng": [-96.] * 12, "facility_type": ["unknown"] * 12},
        geometry=[LineString([(-96.01, 41 + i * .03), (-95.99, 41 + i * .03)]) for i in range(12)], crs=4326)
    roads.to_parquet(root / "segments.parquet")
    crashes = pd.DataFrame([{"crash_id": f"C{i}-{year}", "year": year, "state_fips": 31,
        "lat": 41. + i * .03, "lng": -96., "fatalities": 1, "outcome": "fatal_crash"}
        for i in range(8) for year in [2021, 2022, 2023]])
    crashes.to_parquet(root / "crashes.parquet")
    write_json(root / "fars-manifest.json", [{"year": y, "rows": 8} for y in [2021, 2022, 2023]])
    write_json(root / "aadt-manifest.json", {"count_years": [2025]})


def test_pipeline_real_build_and_candidate_do_not_promote(tmp_path):
    inputs(tmp_path)
    result = build(tmp_path)
    assert result["segments"] == 12
    first = (tmp_path / "snapshot.json").read_bytes()
    snapshot = json.loads(first)
    assert snapshot["quality"]["matched"] == 24
    assert snapshot["quality"]["zero_crash_segment_years"] == 12
    assert snapshot["segments"][0]["exposure_status"] == "aadt_vintage_proxy"
    candidate = build(tmp_path, candidate=True)
    assert "/candidates/" in candidate["output"]
    assert (tmp_path / "snapshot.json").read_bytes() == first
    assert "NaN" not in first.decode()


def test_pipeline_lock_rejects_concurrent_jobs(tmp_path):
    with pipeline_lock(tmp_path):
        with pytest.raises(RuntimeError, match="already running"):
            with pipeline_lock(tmp_path):
                pytest.fail("lock must not be acquired twice")
    with pipeline_lock(tmp_path):
        pass


def test_build_rejects_partial_annual_source(tmp_path):
    inputs(tmp_path)
    write_json(tmp_path / "fars-manifest.json", [{"year": 2021, "rows": 8}])
    with pytest.raises(ValueError, match="row counts/years"):
        build(tmp_path)


def test_cli_commands_dispatch_explicit_paths(tmp_path, monkeypatch, capsys):
    from safety import cli, database, feeds
    calls = []
    monkeypatch.setattr(cli, "ingest_fars", lambda *a: calls.append(a) or [1])
    monkeypatch.setattr(cli, "ingest_aadt", lambda *a: [1, 2])
    main(["--root", str(tmp_path), "ingest", "--years", "2023"])
    assert json.loads(capsys.readouterr().out)["fatal_crashes"] == 1
    assert calls[0][1] == [2023]
    monkeypatch.setattr(cli, "build", lambda root, candidate: {"candidate": candidate})
    main(["--root", str(tmp_path), "build", "--candidate"])
    assert json.loads(capsys.readouterr().out)["candidate"]
    monkeypatch.setattr(feeds, "refresh_feeds", lambda *a, **kw: {"refreshed": True})
    main(["--root", str(tmp_path), "refresh-feeds"])
    assert json.loads(capsys.readouterr().out)["refreshed"]
    monkeypatch.setattr(database, "import_snapshot", lambda root: {"rows": 1})
    main(["--root", str(tmp_path), "import-postgis"])
    assert json.loads(capsys.readouterr().out)["rows"] == 1
    monkeypatch.setattr(cli, "import_state_crashes", lambda *a: 5)
    main(["--root", str(tmp_path), "import-state", "records.csv", "agreement.json"])
    assert json.loads(capsys.readouterr().out)["staged_rows"] == 5
    main(["--root", str(tmp_path), "status"])
    assert not json.loads(capsys.readouterr().out)["ready"]


def test_benchmark_rebuilds_panel_and_rejects_changed_sources(tmp_path, monkeypatch, capsys):
    from safety import advanced
    inputs(tmp_path)
    build(tmp_path)
    pd.DataFrame({"fatal_crashes": [99999]}).to_parquet(tmp_path / "panel.parquet")
    def benchmark(panel, **kwargs):
        assert panel.fatal_crashes.sum() == 24
        assert "sinuosity" in panel
        return {"schema_version": 1, "decision": {"promotion": "manual"}}, None
    monkeypatch.setattr(advanced, "run_benchmark", benchmark)
    main(["--root", str(tmp_path), "benchmark"])
    assert json.loads(capsys.readouterr().out)["decision"]["promotion"] == "manual"
    report = json.loads((tmp_path / "advanced-benchmark.json").read_text())
    assert set(report["snapshot_inputs"]) == {"crashes_sha256", "roads_sha256"}
    crashes = pd.read_parquet(tmp_path / "crashes.parquet")
    crashes.loc[0, "fatalities"] = 2
    crashes.to_parquet(tmp_path / "crashes.parquet")
    with pytest.raises(ValueError, match="Sources differ"):
        main(["--root", str(tmp_path), "benchmark"])


def test_behavior_rejects_wrong_archive_release(tmp_path, monkeypatch, capsys):
    from safety import behavior
    inputs(tmp_path)
    write_json(tmp_path / "fars-manifest.json", [{"year": 2024, "sha256": "archive-v1"}])
    report = {"schema_version": 1, "sources": [{"year": 2024, "sha256": "archive-v2"}], "cohorts": []}
    monkeypatch.setattr(behavior, "build_behavior_report", lambda *args: report)
    with pytest.raises(ValueError, match="Behavior archives differ"):
        main(["--root", str(tmp_path), "behavior", "--archive-dir", "/tmp", "--years", "2024"])
    report["sources"][0]["sha256"] = "archive-v1"
    main(["--root", str(tmp_path), "behavior", "--archive-dir", "/tmp", "--years", "2024"])
    assert json.loads(capsys.readouterr().out)["cohorts"] == 0
    assert set(json.loads((tmp_path / "behavior.json").read_text())["snapshot_inputs"]) == {"crashes_sha256"}

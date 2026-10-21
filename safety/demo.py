"""Create an explicitly synthetic workflow demo; never overwrite existing artifacts."""
import argparse
from pathlib import Path

from safety.io import write_json


def create_demo(root):
    root = Path(root)
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("Demo requires a new or empty directory; existing data is never overwritten")
    rows = []
    for area, lat, lng in [("Omaha", 41.2565, -95.9345), ("Lincoln", 40.8136, -96.7026)]:
        for i in range(12):
            aadt, miles, years = 2000 + 1500 * i, .5 + .1 * (i % 5), 4
            observed = i % 4
            exposure = aadt * miles * 1461
            expected = .02 + .015 * i
            rows.append({"segment_id": f"SYNTHETIC-{area.upper()}-{i+1:02}", "route": f"SIMULATED {area} corridor {i+1:02}",
                         "lat": lat + (i // 4) * .012, "lng": lng + (i % 4) * .012, "length_miles": miles,
                         "aadt": aadt, "aadt_year": 2025, "observed": observed, "years": years,
                         "exposure_vmt": exposure, "rate_per_100m_vmt": observed / exposure * 1e8,
                         "expected_annual": expected, "excess_annual": expected - .07,
                         "lower_annual": expected * .25, "upper_annual": expected * 2.4,
                         "exposure_status": "synthetic_example", "data_mode": "synthetic"})
    snapshot = {"schema_version": 1, "built_at": "2026-01-01T00:00:00+00:00", "data_mode": "synthetic",
                "scope": "SYNTHETIC WORKFLOW DEMO — invented roads, counts, exposure and model outputs",
                "status": "synthetic_demo", "commercial_ready": False, "years": [2021, 2022, 2023, 2024],
                "quality": {}, "metrics": {}, "model": {"kind": "hand_constructed_workflow_fixture", "trained": False},
                "sources": [{"name": "Deterministic synthetic demonstration", "rights": "Generated locally; no real crash, roadway or person records.",
                             "commercial_use": True, "scope": "Illustrative workflow only; no real road risk or model accuracy."}],
                "limitations": ["All roads, observations, predictions and intervals are invented examples.",
                                "Coordinates locate fictional examples near cities; no real road is assessed.",
                                "Countermeasure catalog evidence is real; calculations on these inputs are purely illustrative.",
                                "No model benchmark, measured behavior, live feed or foundation model is included."],
                "provenance": {"generator": "safety.demo", "version": 1, "real_data_used": False}, "segments": rows}
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "snapshot.json", snapshot)
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="data/synthetic-demo")
    args = parser.parse_args(argv)
    snapshot = create_demo(args.root)
    print(f"Created {len(snapshot['segments'])} explicitly synthetic road examples in {args.root}")


if __name__ == "__main__":
    main()

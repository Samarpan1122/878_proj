"""Reproducible, sequential pipeline; no legacy inputs and no silent candidate promotion."""
import argparse
import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path

import geopandas as gpd
import pandas as pd

from safety.io import digest, now, write_json
from safety.sources import SOURCES, import_state_crashes, ingest_aadt, ingest_fars

LIMITATIONS = [
    "FARS covers fatal crashes only. These are not all-crash or injury-risk predictions.",
    "Current NDOT traffic volumes and geometries are proxies for older crash years; historical exposure is unverified.",
    "Ambiguous and distant crash-to-road matches are withheld; unmatched fatal crashes are reported separately.",
    "Local negative-binomial SPF is experimental, lacks facility classes, and is not an HSM-calibrated model.",
    "EB intervals condition on the fitted model; traffic-volume, matching and parameter uncertainty are not included.",
    "NDOT commercial-use and redistribution terms require confirmation before commercial export.",
    "No agency pilot, live crash feed or measured countermeasure effectiveness is claimed.",
]


@contextmanager
def pipeline_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".pipeline.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("A safety pipeline job is already running; run heavy jobs sequentially") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def build(root, candidate=False):
    from safety.exposure import build_segment_years
    from safety.models import fit_spf, screen_network, validate_spf
    from safety.monitoring import drift_report
    root = Path(root)
    crashes = pd.read_parquet(root / "crashes.parquet")
    manifest = json.loads((root / "fars-manifest.json").read_text())
    declared = {int(m["year"]): int(m["rows"]) for m in manifest}
    actual = crashes.groupby("year").size().to_dict()
    if len(declared) != len(manifest) or declared != actual:
        raise ValueError("FARS national row counts/years disagree with the source manifest; re-ingest a complete release")
    # Nebraska exposure cannot be used as the denominator for nationwide crashes.
    crashes = crashes[crashes.state_fips.eq(31)].copy()
    roads = gpd.read_parquet(root / "segments.parquet")
    years = sorted({m["year"] for m in manifest})
    panel, coverage = build_segment_years(crashes, roads, years)
    model = fit_spf(panel)
    metrics = validate_spf(panel)
    screened = screen_network(panel, model)
    screened = screened.merge(roads[["segment_id", "aadt_year"]], on="segment_id", validate="one_to_one")
    aliases = {"observed_fatal_crashes": "observed", "years_observed": "years", "vehicle_miles": "exposure_vmt",
        "observed_fatal_crashes_per_100m_vmt": "rate_per_100m_vmt", "eb_annual_fatal_crashes": "expected_annual",
        "excess_annual_fatal_crashes": "excess_annual", "eb_annual_lower95": "lower_annual", "eb_annual_upper95": "upper_annual"}
    for original, alias in aliases.items():
        screened[alias] = screened[original]
    screened["exposure_status"] = screened.aadt_aligned.map({True: "vintage_aligned", False: "aadt_vintage_proxy"})
    baseline = root / "screening.parquet"
    monitoring = drift_report(pd.read_parquet(baseline), screened, ["aadt", "length_miles", "expected_annual"]) if baseline.exists() else {
        "status": "baseline_created", "review_required": True,
        "recommendation": "Review the initial model, linkage and exposure vintages before operational use",
        "promotion": "manual_review_required"}
    built_at = now()
    output = root / "candidates" / built_at.replace(":", "-") if candidate else root
    output.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(output / "panel.parquet", index=False)
    screened.to_parquet(output / "screening.parquet", index=False)
    write_json(output / "model.json", model)
    write_json(output / "monitoring.json", monitoring)
    payload = {"schema_version": 1, "built_at": built_at, "scope": "Nebraska; FARS fatal crashes; NDOT AADT",
        "years": years, "commercial_ready": False, "status": "candidate" if candidate else "experimental",
        "quality": coverage, "metrics": metrics, "model": model, "monitoring": monitoring,
        "limitations": LIMITATIONS, "segments": json.loads(screened.to_json(orient="records")),
        "provenance": {"fars": manifest, "aadt": json.loads((root / "aadt-manifest.json").read_text()),
                       "crashes_sha256": digest(root / "crashes.parquet"), "roads_sha256": digest(root / "segments.parquet")}}
    # The HTTP service only reads this single atomically replaced file.
    write_json(output / "snapshot.json", payload)
    return {"output": str(output), "segments": len(screened), "quality": coverage, "metrics": metrics}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.getenv("SAFETY_DATA_DIR", "data/safety"))
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--years", type=int, nargs="+", default=[2021, 2022, 2023, 2024])
    ingest.add_argument("--archive-dir")
    rebuild = commands.add_parser("build")
    rebuild.add_argument("--candidate", action="store_true")
    benchmark = commands.add_parser("benchmark", help="Compare fixed candidates on development holdouts; never promotes")
    benchmark.add_argument("--bootstrap", type=int, default=1000)
    benchmark.add_argument("--spatial-folds", type=int, default=5)
    behavior = commands.add_parser("behavior", help="Aggregate recorded FARS behavioral factors; not prospective prediction")
    behavior.add_argument("--archive-dir", required=True)
    behavior.add_argument("--years", type=int, nargs="+", default=[2021, 2022, 2023, 2024])
    commands.add_parser("refresh-feeds")
    commands.add_parser("import-postgis")
    agency = commands.add_parser("import-state")
    agency.add_argument("csv")
    agency.add_argument("agreement")
    commands.add_parser("status")
    args = parser.parse_args(argv)
    root = Path(args.root)
    with pipeline_lock(root):
        if args.command == "ingest":
            crashes = ingest_fars(root, args.years, args.archive_dir)
            roads = ingest_aadt(root)
            result = {"fatal_crashes": len(crashes), "road_segments": len(roads)}
        elif args.command == "build":
            result = build(root, args.candidate)
        elif args.command == "benchmark":
            from safety.advanced import run_benchmark
            from safety.context import road_context
            from safety.exposure import build_segment_years
            snapshot = json.loads((root / "snapshot.json").read_text())
            inputs = {"crashes_sha256": digest(root / "crashes.parquet"), "roads_sha256": digest(root / "segments.parquet")}
            if any(snapshot.get("provenance", {}).get(key) != value for key, value in inputs.items()):
                raise ValueError("Sources differ from the active snapshot; rebuild it before benchmarking")
            crashes = pd.read_parquet(root / "crashes.parquet")
            roads = gpd.read_parquet(root / "segments.parquet")
            panel, _ = build_segment_years(crashes[crashes.state_fips.eq(31)], roads, snapshot["years"])
            context = road_context(roads)
            panel = panel.merge(context, on="segment_id", validate="many_to_one")
            report, _ = run_benchmark(panel, spatial_folds=args.spatial_folds, bootstrap_replicates=args.bootstrap)
            report.update({"built_at": now(), "snapshot_inputs": inputs})
            write_json(root / "advanced-benchmark.json", report)
            result = {"artifact": str(root / "advanced-benchmark.json"), "decision": report["decision"]}
        elif args.command == "behavior":
            from safety.behavior import build_behavior_report
            report = build_behavior_report(args.archive_dir, args.years)
            expected = {int(m["year"]): m["sha256"] for m in json.loads((root / "fars-manifest.json").read_text())}
            actual = {int(m["year"]): m["sha256"] for m in report["sources"]}
            if actual != expected:
                raise ValueError("Behavior archives differ from the FARS snapshot release; use matching years and files")
            report.update({"built_at": now(), "snapshot_inputs": {"crashes_sha256": digest(root / "crashes.parquet")}})
            write_json(root / "behavior.json", report)
            result = {"artifact": str(root / "behavior.json"), "cohorts": len(report["cohorts"])}
        elif args.command == "refresh-feeds":
            from safety.feeds import refresh_feeds
            config = os.getenv("INCIDENT_FEED_CONFIG")
            result = refresh_feeds(root, incident_config=json.loads(Path(config).read_text()) if config else None)
        elif args.command == "import-postgis":
            from safety.database import import_snapshot
            result = import_snapshot(root)
        elif args.command == "import-state":
            result = {"staged_rows": import_state_crashes(args.csv, args.agreement, root)}
        else:
            path = root / "snapshot.json"
            snapshot = json.loads(path.read_text()) if path.exists() else {"ready": False}
            result = {k: v for k, v in snapshot.items() if k != "segments"}
    print(json.dumps(result, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()

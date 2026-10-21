"""Audit a private evaluation release and package code without datasets or credentials.

These checks do not grant data rights, certify security, or approve a model.
"""
import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

from safety.io import digest, now, write_json


def assess_readiness(root, verify_files=True):
    from safety.api import Snapshot
    from fastapi import HTTPException
    root = Path(root)
    checks = []

    def check(name, passed, detail, state=None):
        checks.append({"id": name, "status": state or ("passed" if passed else "failed"), "detail": detail})

    try:
        snapshot = Snapshot(root).read()
    except (HTTPException, OSError, ValueError):
        snapshot = None
    check("serving_snapshot", bool(snapshot), "A nonempty, valid, finite serving snapshot is required.")
    snapshot = snapshot or {}
    synthetic = snapshot.get("data_mode") == "synthetic"
    provenance = snapshot.get("provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    if synthetic:
        valid = (isinstance(snapshot.get("scope"), str) and snapshot["scope"].startswith("SYNTHETIC")
                 and isinstance(snapshot.get("sources"), list) and bool(snapshot["sources"])
                 and all(isinstance(s, dict) and isinstance(s.get("name"), str) for s in snapshot["sources"])
                 and provenance.get("real_data_used") is False
                 and all(str(r.get("segment_id", "")).startswith("SYNTHETIC-") for r in snapshot.get("segments", [])))
        check("synthetic_labels", valid, "Simulated roads and sources must be explicitly identified; no accuracy evidence is implied.")
    else:
        for filename, key in [("crashes.parquet", "crashes_sha256"), ("segments.parquet", "roads_sha256")]:
            expected = provenance.get(key)
            valid_hash = isinstance(expected, str) and len(expected) == 64 and all(c in "0123456789abcdef" for c in expected)
            check(key + "_declared", valid_hash, "Snapshot must identify the exact input artifact with SHA-256.")
            if verify_files:
                try:
                    matched = valid_hash and digest(root / filename) == expected
                except OSError:
                    matched = False
                check(key + "_verified", matched, "Local artifact bytes must match the active snapshot.")
            else:
                check(key + "_verified", False, "File hashing is performed by the offline release audit, not on each API request.", "unverified")
        for filename, key in [("fars-manifest.json", "fars"), ("aadt-manifest.json", "aadt")]:
            if verify_files:
                try:
                    value = json.loads((root / filename).read_text())
                    matched = bool(value) and value == provenance.get(key)
                except (OSError, ValueError):
                    matched = False
                check(key + "_manifest", matched, "Source manifest must equal the release's embedded provenance.")
            else:
                check(key + "_manifest", False, "Source manifest comparison requires the offline release audit.", "unverified")
        metrics = snapshot.get("metrics", {})
        check("evaluation_present", isinstance(metrics, dict) and all(
            isinstance(metrics.get(p), dict) and metrics[p].get("status") == "evaluated" for p in ["temporal", "spatial"]),
            "Temporal and geographic evaluation records are required; presence is not agency acceptance.")
        check("limitations_present", bool(snapshot.get("limitations")), "Expose source, exposure, model and applicability limitations.")
    technical = bool(checks) and all(c["status"] == "passed" for c in checks)
    blockers = [
        {"id": "commercial_data_rights", "owner": "Data owner and provider", "detail":
         "Synthetic demonstration data establishes no rights to any real agency dataset." if synthetic else
         "NDOT commercial reuse and redistribution are unconfirmed; obtain written permission or replace the source."},
        {"id": "agency_validation", "owner": "Partner transportation engineer", "detail":
         "Agree on data coverage, historical exposure, linkage audit and holdout acceptance; sign the pilot evaluation."},
        {"id": "commercial_terms", "owner": "Product owner and buyer", "detail":
         "Agree on software rights, scope, authorized users, data retention, support and incident responsibilities."},
        {"id": "operational_acceptance", "owner": "Deployment operator and buyer", "detail":
         "Review IAM and dependencies, assign alert owners and test recovery for the buyer's deployment. No SLA or certification is established."},
    ]
    try:
        snapshot_hash = digest(root / "snapshot.json") if snapshot else None
    except OSError:
        snapshot_hash = None
    return {"schema_version": 1, "checked_at": now(), "data_mode": "synthetic" if synthetic else "official_source_experimental",
            "verification_scope": "local_artifact_integrity" if verify_files else "serving_metadata_only",
            "snapshot_sha256": snapshot_hash, "snapshot_built_at": snapshot.get("built_at"),
            "segments": len(snapshot.get("segments", [])), "technical_checks_passed": technical,
            "private_evaluation_status": "technical_checks_passed" if technical else "requires_offline_audit" if snapshot and not verify_files else "blocked",
            "commercial_ready": False, "foundation_model_trained": False, "checks": checks,
            "commercial_blockers": blockers,
            "interpretation": "Technical integrity supports a private demonstration only. It is not legal clearance, validated safety effectiveness or a commercial release approval."}


EXACT_FILES = ("Dockerfile", ".dockerignore", ".gcloudignore", "compose.yaml", "requirements-safety.txt", "requirements-safety.lock", "requirements-test.txt",
               "infra/cloud-run.sh", "infra/rollback-cloud-run.sh", "infra/postgis.sql", "infra/bigquery.sql",
               "scripts/smoke_safety.py", "docs/SAFETY_ENGINE.md", "docs/OPERATIONS.md", "docs/PILOT.md",
               "docs/PROCUREMENT.md", "docs/ADVANCED_MODELS.md", "docs/FOUNDATION_ARCHITECTURE.md",
               "configs/foundation/roadworld_scratch.json", "web/static/tokens.css")


def build_bundle(repo, output):
    """Allowlist only; neither data/ nor outputs/ nor account files are traversed."""
    repo, output = Path(repo).resolve(), Path(output).resolve()
    candidates = [repo / p for p in EXACT_FILES]
    for folder, pattern in [("safety", "*.py"), ("tests", "test_safety*.py"), ("docs/commercial", "*.md"), ("web/static", "safety*")]:
        candidates.extend((repo / folder).glob(pattern))
    files = {}
    for path in sorted(set(candidates)):
        if not path.exists():
            continue
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != repo.parent):
            raise ValueError("Release files must not be symlinks")
        if not path.is_file() or not path.resolve().is_relative_to(repo):
            raise ValueError("Release file escapes the allowlist")
        name = path.relative_to(repo).as_posix()
        files[name] = path.read_bytes()
    if "safety/demo.py" not in files or "Dockerfile" not in files:
        raise ValueError("Bundle requires the demo generator and deployment files")
    files["README.md"] = BUNDLE_README.encode()
    files["NOTICE.txt"] = b"Engineering evaluation package. No software license grant is implied. The owner must agree distribution and commercial terms. No real datasets, trained research weights, accounts or credentials are included.\n"
    manifest = {"schema_version": 1, "kind": "synthetic_demo_and_engineering_evaluation", "contains_real_data": False,
                "commercial_ready": False, "foundation_model_trained": False,
                "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in sorted(files.items())}}
    files["MANIFEST.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"bundle": str(output), "sha256": digest(output), "bytes": output.stat().st_size, "files": len(files), "contains_real_data": False}


BUNDLE_README = """# GeoCrash private evaluation package

Start with [the buyer guide](docs/commercial/README.md). This package contains code and documentation, no real datasets or research weights. Synthetic examples demonstrate workflow, not model performance or real road risk. Commercial rights and a validated agency pilot remain separate gates.

## Run the synthetic demo

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-safety.txt -c requirements-safety.lock
.venv/bin/python -m safety.demo --root data/safety
GEOCRASH_SAFETY_DATA=data/safety .venv/bin/uvicorn safety.api:app --host 127.0.0.1 --port 8893
```

Open http://localhost:8893. Or, after generating the synthetic snapshot, run `docker compose up --build api` and open http://localhost:8080. The generator refuses to overwrite a nonempty directory. To use real data, use a separate directory and follow the source rights and operations documents.

```bash
.venv/bin/python -m safety.release audit --root data/safety --output readiness.json --require-technical
.venv/bin/python scripts/smoke_safety.py --help
```

The Cloud Run deployment defaults to private IAM access. Review `docs/OPERATIONS.md` before provisioning. No GPU foundation training is implemented. File checksums are recorded in MANIFEST.json; the manifest lists every other file. No software license grant is implied by this archive.
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--root", default="data/safety")
    audit.add_argument("--output", default="outputs/releases/readiness.json")
    audit.add_argument("--require-technical", action="store_true")
    bundle = commands.add_parser("bundle")
    bundle.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    bundle.add_argument("--output", default="outputs/releases/geocrash-evaluation.zip")
    args = parser.parse_args(argv)
    if args.command == "audit":
        result = assess_readiness(args.root)
        write_json(args.output, result)
        print(json.dumps({"report": args.output, "technical_checks_passed": result["technical_checks_passed"], "commercial_ready": False}))
        return 1 if args.require_technical and not result["technical_checks_passed"] else 0
    print(json.dumps(build_bundle(args.repo, args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

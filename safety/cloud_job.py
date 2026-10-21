"""Run scheduled work on local disk; publish to GCS with generation preconditions."""
import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from safety.io import digest

INPUTS = ["segments.parquet", "crashes.parquet", "snapshot.json", "screening.parquet", "panel.parquet",
          "model.json", "fars-manifest.json", "aadt-manifest.json", "feeds.json", "monitoring.json"]


def _verify_candidate_inputs(root):
    """An in-progress deployment must never combine different source snapshots."""
    snapshot = json.loads((root / "snapshot.json").read_text())
    provenance = snapshot.get("provenance", {})
    for filename, key in [("crashes.parquet", "crashes_sha256"), ("segments.parquet", "roads_sha256")]:
        if digest(root / filename) != provenance.get(key):
            raise ValueError(f"Candidate input checksum mismatch: {filename}; retry after deployment completes")
    for filename, key in [("fars-manifest.json", "fars"), ("aadt-manifest.json", "aadt")]:
        if json.loads((root / filename).read_text()) != provenance.get(key):
            raise ValueError(f"Candidate source manifest mismatch: {filename}; retry after deployment completes")


def run_job(bucket_name, task, client=None, runner=None):
    if task not in {"feeds", "candidate"}:
        raise ValueError("Task must be feeds or candidate")
    if not bucket_name or "/" in bucket_name:
        raise ValueError("Supply a bucket name, without gs:// or a path")
    if client is None:
        from google.cloud import storage
        client = storage.Client()
    runner = runner or subprocess.run
    bucket = client.bucket(bucket_name)
    run_id = str(uuid.uuid4())
    lease = bucket.blob("safety/.job-lease.json")
    # A crashed worker leaves the lease behind intentionally. Inspect the execution
    # and manually remove that exact lease generation before restarting.
    lease.upload_from_string(json.dumps({"run_id": run_id, "task": task}),
                             content_type="application/json", if_generation_match=0)
    lease_generation = lease.generation
    try:
        with tempfile.TemporaryDirectory(prefix="geocrash-job-") as folder:
            root = Path(folder)
            versions = {}
            for name in INPUTS:
                blob = bucket.get_blob("safety/" + name)
                if blob is not None:
                    versions[name] = blob.generation
                    blob.download_to_filename(str(root / name), if_generation_match=blob.generation)
            if task == "candidate":
                _verify_candidate_inputs(root)
            command = [sys.executable, "-m", "safety.cli", "--root", str(root)]
            command += ["refresh-feeds"] if task == "feeds" else ["build", "--candidate"]
            runner(command, check=True)
            if task == "feeds":
                outputs = [(root / "feeds.json", "safety/feeds.json", versions.get("feeds.json", 0))]
            else:
                files = sorted((root / "candidates").rglob("*"))
                outputs = [(path, f"safety/candidates/{run_id}/{path.relative_to(root / 'candidates')}", 0)
                           for path in files if path.is_file() and not path.name.startswith(".")]
                if not outputs:
                    raise RuntimeError("Candidate build produced no artifacts")
            uploaded = []
            for path, object_name, generation in outputs:
                bucket.blob(object_name).upload_from_filename(str(path), if_generation_match=generation)
                uploaded.append(object_name)
            if task == "feeds":
                snapshot = json.loads((root / "feeds.json").read_text())
                if any(snapshot.get(source, {}).get("status") == "error" for source in ["nws", "incidents"]):
                    raise RuntimeError("Feed refresh failed; published the explicitly stale last-good snapshot")
            # Publish completion marker last. Partial candidate uploads lack it and
            # must never be considered an approved or complete artifact set.
            if task == "candidate":
                bucket.blob(f"safety/candidates/{run_id}/complete.json").upload_from_string(
                    json.dumps({"run_id": run_id, "artifacts": uploaded, "promotion": "manual_review_required"}),
                    content_type="application/json", if_generation_match=0)
            return {"task": task, "run_id": run_id, "uploaded": uploaded}
    finally:
        lease.delete(if_generation_match=lease_generation)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--task", choices=["feeds", "candidate"], required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_job(args.bucket, args.task)))


if __name__ == "__main__":
    main()

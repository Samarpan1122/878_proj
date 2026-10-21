import hashlib
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from safety.api import create_app
from safety.demo import create_demo
from safety.io import digest, write_json
from safety.release import assess_readiness, build_bundle, main


def test_synthetic_demo_is_explicit_and_does_not_overwrite(tmp_path):
    root = tmp_path / "demo"
    snapshot = create_demo(root)
    assert len(snapshot["segments"]) == 24
    original = (root / "snapshot.json").read_bytes()
    with pytest.raises(ValueError, match="never overwritten"):
        create_demo(root)
    assert (root / "snapshot.json").read_bytes() == original
    assert all(r["data_mode"] == "synthetic" and r["segment_id"].startswith("SYNTHETIC-") for r in snapshot["segments"])
    client = TestClient(create_app(root))
    status = client.get("/api/safety/status").json()
    assert status["data_mode"] == "synthetic"
    assert len(status["sources"]) == 1 and "synthetic" in status["sources"][0]["name"]
    assert client.get("/ready").json()["segments"] == 24
    assert client.get("/api/safety/segments?lat=41.2565&lng=-95.9345&radius_km=30").json()["total"] == 12
    report = assess_readiness(root)
    assert report["technical_checks_passed"] and not report["commercial_ready"]
    assert not report["foundation_model_trained"]
    assert client.get("/api/safety/readiness").json()["verification_scope"] == "serving_metadata_only"


def real_release(root):
    snapshot = create_demo(root)
    snapshot.pop("data_mode")
    snapshot["scope"] = "Experimental source fixture"
    snapshot["metrics"] = {p: {"status": "evaluated"} for p in ["temporal", "spatial"]}
    for filename in ["segments.parquet", "crashes.parquet"]:
        (root / filename).write_bytes(b"input bytes are hashed, not loaded as parquet by the release audit")
    snapshot["provenance"] = {"crashes_sha256": digest(root / "crashes.parquet"), "roads_sha256": digest(root / "segments.parquet"),
                              "fars": [{"year": 2024, "source": "fars"}], "aadt": {"commercial_use": False}}
    write_json(root / "fars-manifest.json", snapshot["provenance"]["fars"])
    write_json(root / "aadt-manifest.json", snapshot["provenance"]["aadt"])
    write_json(root / "snapshot.json", snapshot)
    return snapshot


def test_readiness_distinguishes_hashes_metadata_and_commercial_review(tmp_path):
    root = tmp_path / "data"
    real_release(root)
    report = assess_readiness(root)
    assert report["technical_checks_passed"] and not report["commercial_ready"]
    assert len(report["commercial_blockers"]) == 4
    metadata = assess_readiness(root, verify_files=False)
    assert not metadata["technical_checks_passed"]
    assert metadata["private_evaluation_status"] == "requires_offline_audit"
    assert any(c["status"] == "unverified" for c in metadata["checks"])
    (root / "segments.parquet").write_bytes(b"tampered")
    assert not assess_readiness(root)["technical_checks_passed"]
    assert main(["audit", "--root", str(root), "--output", str(tmp_path / "report.json"), "--require-technical"]) == 1


def test_manifest_mismatch_and_missing_data_fail_closed(tmp_path):
    assert not assess_readiness(tmp_path)["technical_checks_passed"]
    root = tmp_path / "data"
    real_release(root)
    write_json(root / "aadt-manifest.json", {"commercial_use": True})
    report = assess_readiness(root)
    assert next(c for c in report["checks"] if c["id"] == "aadt_manifest")["status"] == "failed"
    assert not report["commercial_ready"]
    (root / "snapshot.json").write_text('{"bad":1e999}')
    assert not assess_readiness(root)["technical_checks_passed"]


def test_bundle_deterministic_allowlist_and_checksums(tmp_path):
    repo = tmp_path / "repo"
    for name in ["safety/demo.py", "safety/api.py", "Dockerfile", "docs/commercial/README.md", ".env",
                 ".cloud-config/token", "data/safety/snapshot.json", "outputs/research/model.pt", "SESSION_HANDOFF.md"]:
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("never-distribute" if name.startswith((".", "data/", "outputs/", "SESSION")) else name)
    first = build_bundle(repo, tmp_path / "a.zip")
    second = build_bundle(repo, tmp_path / "b.zip")
    assert first["sha256"] == second["sha256"]
    with zipfile.ZipFile(first["bundle"]) as archive:
        names = archive.namelist()
        assert not any(n.startswith(("data/", "outputs/", ".env", ".cloud-config/", "SESSION")) for n in names)
        manifest = json.loads(archive.read("MANIFEST.json"))
        assert set(manifest["files"]) == set(names) - {"MANIFEST.json"}
        for name, record in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == record["sha256"]
        assert b"never-distribute" not in b"".join(archive.read(n) for n in names)


def test_bundle_rejects_symlink_in_allowlisted_directory(tmp_path):
    repo = tmp_path / "repo"
    (repo / "safety").mkdir(parents=True)
    (repo / "Dockerfile").write_text("test")
    secret = tmp_path / "secret"
    secret.write_text("do not copy")
    (repo / "safety/demo.py").symlink_to(secret)
    with pytest.raises(ValueError, match="symlinks"):
        build_bundle(repo, tmp_path / "bundle.zip")

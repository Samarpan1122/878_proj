"""Verify the private pilot without printing credentials. Uses the user's gcloud login."""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "geocrashai-safety-20260929"
REGION = "us-central1"
SDK = ROOT / ".tools/google-cloud-sdk/bin"
ENV = {**os.environ, "CLOUDSDK_CONFIG": str(ROOT / ".cloud-config"), "PATH": str(SDK) + os.pathsep + os.environ.get("PATH", "")}


def command(program, *args):
    result = subprocess.run([str(SDK / program), *args], env=ENV, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{program} command failed: {result.stderr[-3000:]}")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-jobs", action="store_true")
    parser.add_argument("--advanced", action="store_true", help="Verify model/behavior report routes and research isolation")
    parser.add_argument("--output", default="outputs/reports/CLOUD_VERIFICATION.json")
    args = parser.parse_args()
    query = ('SELECT "segments" AS table_name, COUNT(*) AS row_count, COUNTIF(geometry IS NULL) AS unlocated '
             f'FROM `{PROJECT}.safety.segments` UNION ALL SELECT "crashes", COUNT(*), COUNTIF(geometry IS NULL) '
             f'FROM `{PROJECT}.safety.crashes`')
    warehouse = json.loads(command("bq", f"--project_id={PROJECT}", "query", "--use_legacy_sql=false", "--format=json", query))
    print(json.dumps({"warehouse": warehouse}), flush=True)
    url = command("gcloud", "run", "services", "describe", "geocrash-safety", f"--project={PROJECT}", f"--region={REGION}", "--format=value(status.url)")
    token = command("gcloud", "auth", "print-identity-token")

    def get(path, body=None):
        request = Request(url + path, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                          data=json.dumps(body).encode() if body else None)
        with urlopen(request, timeout=60) as response:
            return json.load(response)

    try:
        with urlopen(url + "/health", timeout=30) as response:
            private = response.status in (401, 403)
    except HTTPError as exc:
        private = exc.code in (401, 403)
    policy = json.loads(command("gcloud", "run", "services", "get-iam-policy", "geocrash-safety",
                                f"--project={PROJECT}", f"--region={REGION}", "--format=json"))
    if any(member in {"allUsers", "allAuthenticatedUsers"} for binding in policy.get("bindings", []) for member in binding.get("members", [])):
        raise RuntimeError("Cloud Run IAM policy grants broad access")
    if not private:
        raise RuntimeError("Pilot unexpectedly permits unauthenticated access")
    health = get("/health")
    status = get("/api/safety/status")
    ready = {"ready": status["ready"], "built_at": status["built_at"]}
    for path in ["/", "/safety.html", "/safety.js", "/safety.css"]:
        request = Request(url + path, headers={"Authorization": "Bearer " + token})
        with urlopen(request, timeout=60) as response:
            if response.status != 200:
                raise RuntimeError(f"Static surface unavailable: {path}")
    assert ready["ready"] and not health["legacy_models_loaded"]
    page = get("/api/safety/segments?lat=41.2565&lng=-95.9345&radius_km=30&limit=2")
    assert len(page["segments"]) == 2
    scenario = get("/api/safety/benefit-cost", {
        "segment_id": page["segments"][0]["segment_id"], "countermeasure_id": "4737",
        "implementation_cost": 100000, "annual_maintenance_cost": 1000,
        "service_life_years": 10, "discount_rate": .03, "fatalities_per_crash": 1,
        "eligible_fraction": .5, "applicability_confirmed": True, "fatal_transfer_assumption_confirmed": True})
    result = {"project": PROJECT, "url": url, "verified_at": datetime.now(timezone.utc).isoformat(),
              "authenticated_only": private, "health": health,
              "ready": ready, "warehouse": warehouse, "omaha_segments": page["total"],
              "scenario_api": "passed; test assumptions do not establish applicability", "jobs": []}
    if args.advanced:
        advanced = get("/api/safety/model-evidence")
        behavior = get("/api/safety/behavior")
        assert advanced["schema_version"] == 1 and advanced["segments"] == 11048
        assert behavior["schema_version"] == 1 and len(behavior["cohorts"]) == 260
        assert "gated_mixture" in advanced["temporal"]["models"]
        national = next(c for c in behavior["cohorts"] if c["scope"] == "national" and c["year"] is None)
        assert national["fatal_crashes"] == 153273
        request = Request(url + "/safety-evidence.js", headers={"Authorization": "Bearer " + token})
        with urlopen(request, timeout=60) as response:
            assert response.status == 200
        try:
            get("/api/research/advanced")
            raise RuntimeError("Production unexpectedly exposes research data")
        except HTTPError as exc:
            if exc.code != 404:
                raise
        result["advanced"] = {"model_evidence": "passed", "behavior_cohorts": len(behavior["cohorts"]),
            "research_isolation": "passed", "decision": advanced["decision"]}
    if args.execute_jobs:
        for name in ["geocrash-feeds", "geocrash-candidate"]:
            print(f"Executing {name} and waiting for completion", flush=True)
            output = command("gcloud", "run", "jobs", "execute", name, f"--project={PROJECT}", f"--region={REGION}", "--wait", "--format=json")
            result["jobs"].append({"name": name, "execution": json.loads(output) if output else "completed"})
    status = get("/api/safety/status")
    result["quality"] = status["quality"]
    result["feeds"] = {name: {k: v for k, v in item.items() if k != "records"} for name, item in status["feeds"].items() if isinstance(item, dict)}
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2))
    print(json.dumps({"url": url, "checks": "passed", "jobs": [j["name"] for j in result["jobs"]], "artifact": str(target)}), flush=True)


if __name__ == "__main__":
    main()

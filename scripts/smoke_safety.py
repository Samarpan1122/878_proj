"""Read-only safety service smoke checks, for loopback or authenticated HTTPS deployments."""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    # Never forward an identity token to a redirect target.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify(fetch, *, require_private=False):
    """fetch(path, authenticated=True) returns status, content type and body bytes."""
    if require_private and fetch("/health", authenticated=False)[0] not in (401, 403):
        raise RuntimeError("Service must reject unauthenticated requests")

    def get(path):
        code, content_type, body = fetch(path)
        if code != 200 or "application/json" not in content_type:
            raise RuntimeError(f"Expected JSON HTTP 200 from {path}; received {code}")
        result = json.loads(body)
        json.dumps(result, allow_nan=False)
        return result

    health = get("/health")
    if health.get("status") != "ok" or health.get("service") != "safety" or health.get("legacy_models_loaded") is not False:
        raise RuntimeError("Expected an isolated healthy safety service")
    ready = get("/ready")
    if ready.get("ready") is not True or not ready.get("built_at") or ready.get("segments", 0) < 1:
        raise RuntimeError("Safety snapshot is not ready")
    page = get("/api/safety/segments?limit=2")
    rows = page.get("segments", [])
    if not rows or page.get("total", 0) < len(rows):
        raise RuntimeError("Screening did not return usable roads")
    for path in ("/", "/safety.js", "/safety.css", "/safety-evidence.js"):
        code, _, body = fetch(path)
        if code != 200 or not body:
            raise RuntimeError(f"Missing workspace asset: {path}")
    for path in ("/api/research/advanced", "/api/research/metro", "/models.html", "/.env"):
        if fetch(path)[0] != 404:
            raise RuntimeError(f"Production isolation failed for {path}")
    if fetch("/api/safety/export?commercial=true")[0] != 409:
        raise RuntimeError("Commercial export guard is not active")
    return {"status": "passed", "checked_at": datetime.now(timezone.utc).isoformat(),
            "private_access_checked": require_private, "ready": ready, "segments": page["total"],
            "research_isolation": "passed", "commercial_export_guard": "passed",
            "scope": "Read-only technical smoke check; does not certify commercial rights or model validity"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--identity-token", action="store_true", help="Read a token from gcloud; never prints it")
    parser.add_argument("--gcloud", default=os.getenv("GCLOUD_BIN", "gcloud"))
    parser.add_argument("--require-private", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        parser.error("Supply a service origin without credentials, query, fragment or path")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        parser.error("HTTPS is required except for loopback")
    if args.identity_token and parsed.scheme != "https":
        parser.error("Identity tokens are sent only over HTTPS")
    token = None
    if args.identity_token:
        result = subprocess.run([args.gcloud, "auth", "print-identity-token"], capture_output=True, text=True, check=False)
        if result.returncode or not result.stdout.strip():
            raise SystemExit("Could not obtain an identity token from gcloud")
        token = result.stdout.strip()
    opener = build_opener(NoRedirect())

    def fetch(path, authenticated=True):
        headers = {"Authorization": "Bearer " + token} if token and authenticated else {}
        try:
            response = opener.open(Request(args.url.rstrip("/") + path, headers=headers), timeout=60)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read(8_000_001)
            if len(body) > 8_000_000:
                raise RuntimeError("Smoke response exceeds its size limit")
            return response.code, response.headers.get("Content-Type", ""), body

    result = {"url": args.url, **verify(fetch, require_private=args.require_private)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()

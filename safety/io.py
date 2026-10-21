"""Atomic, strict JSON artifacts and bounded official-source downloads."""
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            json.dump(value, f, allow_nan=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def download(url, destination, max_bytes=150_000_000):
    """Bound downloads, retry transient failures, never overwrite a good cache partially."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("Download size limit must be a positive integer")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": os.getenv("NWS_USER_AGENT", "GeoCrashAI research (local pilot)")})
            with urlopen(request, timeout=60) as response, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as f:
                temp = Path(f.name)
                try:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("source exceeds download size limit")
                        f.write(chunk)
                except BaseException:
                    temp.unlink(missing_ok=True)
                    raise
            try:
                temp.replace(destination)
            finally:
                temp.unlink(missing_ok=True)
            return destination
        except (OSError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in {408, 429, 500, 502, 503, 504}:
                raise
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def digest(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def get_json(url):
    def reject_nonfinite(value):
        raise ValueError(f"Nonfinite JSON number: {value}")

    with tempfile.TemporaryDirectory() as folder:
        return json.loads(download(url, Path(folder) / "response.json", max_bytes=25_000_000).read_text(),
                          parse_constant=reject_nonfinite)

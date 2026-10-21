"""Auditable cached weather and explicitly authorized incident feed snapshots."""
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from safety.io import get_json, now, write_json


def _features(payload):
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Expected GeoJSON FeatureCollection")
    return payload["features"]


def normalize_alerts(payload):
    alerts = {}
    for feature in _features(payload):
        props = feature.get("properties") or {}
        identity = feature.get("id") or props.get("id")
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("NWS alert is missing its stable ID")
        alerts[identity] = {"id": identity, "event": props.get("event"), "headline": props.get("headline"),
            "severity": props.get("severity"), "area": props.get("areaDesc"),
            "onset": props.get("onset"), "expires": props.get("expires"), "kind": "weather_alert"}
    return list(alerts.values())


def normalize_incidents(payload):
    incidents = {}
    for feature in _features(payload):
        props = feature.get("properties") or {}
        identity = feature.get("id") if feature.get("id") is not None else props.get("id")
        if isinstance(identity, bool) or not isinstance(identity, (str, int)) or not str(identity).strip():
            raise ValueError("Incident requires a stable source ID")
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if geometry.get("type") != "Point" or len(coords) != 2:
            raise ValueError("Incident adapter accepts GeoJSON Point [longitude, latitude] only")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in coords):
            raise ValueError("Incident coordinates must be finite numbers")
        lng, lat = coords
        if not -180 <= lng <= 180 or not -90 <= lat <= 90:
            raise ValueError("Incident coordinates outside WGS84 bounds")
        incidents[str(identity)] = {"id": str(identity), "lat": lat, "lng": lng,
            "description": props.get("description"), "updated_at": props.get("updated_at"),
            "kind": "reported_incident"}
    return list(incidents.values())


def _authorized_config(config):
    required = ["url", "provider", "terms_url", "permitted_use", "approved_by"]
    if not all(isinstance(config.get(k), str) and config[k].strip() for k in required):
        raise ValueError("Incident feed requires provider, terms_url, permitted_use and approved_by")
    parsed = urlsplit(config["url"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Incident feed must use an HTTPS URL without embedded credentials")


def refresh_feeds(root, nws_area="NE", incident_config=None, fetch=None):
    """Preserve last good records on failures; failures never refresh successful timestamps."""
    fetch = fetch or get_json
    if not re.fullmatch(r"[A-Z]{2}", nws_area):
        raise ValueError("NWS area must be a two-letter state/territory code")
    if incident_config is not None:
        _authorized_config(incident_config)
    path = Path(root) / "feeds.json"
    previous = json.loads(path.read_text()) if path.exists() else {}
    stamp = now()
    sources = [("nws", f"https://api.weather.gov/alerts/active?area={nws_area}", normalize_alerts,
                {"provider": "NOAA NWS", "terms_url": "https://www.weather.gov/documentation/services-web-api",
                 "permitted_use": "Open government weather data", "area": nws_area})]
    if incident_config:
        # Keep authentication query values out of public provenance and error messages.
        provenance = {k: incident_config[k] for k in ["provider", "terms_url", "permitted_use", "approved_by"]}
        sources.append(("incidents", incident_config["url"], normalize_incidents, provenance))
    result = {"checked_at": stamp, "note": "Weather alerts are not crash observations."}
    for name, url, normalize, provenance in sources:
        cached = previous.get(name, {})
        if cached.get("provenance") != provenance:
            cached = {}
        try:
            records = normalize(fetch(url))
            result[name] = {"status": "ok", "checked_at": stamp, "fetched_at": stamp,
                            "records": records, "provenance": provenance, "error": None}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result[name] = {"status": "error", "checked_at": stamp, "fetched_at": cached.get("fetched_at"),
                "records": cached.get("records", []), "provenance": provenance,
                "error": f"{type(exc).__name__}: feed refresh failed; last successful snapshot retained"}
    if not incident_config:
        result["incidents"] = {"status": "not_configured", "records": [], "fetched_at": None,
                               "error": None, "note": "An authorized agency feed agreement is required."}
    write_json(path, result)
    return feed_status(root)


def feed_status(root, max_age_seconds=1800):
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    path = Path(root) / "feeds.json"
    if not path.exists():
        return {"status": "not_refreshed", "nws": {"status": "not_refreshed", "stale": True, "records": []},
                "incidents": {"status": "not_configured", "stale": True, "records": []}}
    result = json.loads(path.read_text())
    for name in ["nws", "incidents"]:
        source = result[name]
        stamp = source.get("fetched_at")
        try:
            parsed = datetime.fromisoformat(stamp) if stamp else None
            age = (datetime.now(timezone.utc) - parsed).total_seconds() if parsed else None
        except (ValueError, TypeError):
            age = None
        source["age_seconds"] = max(0, round(age)) if age is not None else None
        source["stale"] = age is None or age < 0 or age > max_age_seconds or source["status"] != "ok"
    return result

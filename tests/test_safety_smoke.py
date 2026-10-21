import json

import pytest

from scripts.smoke_safety import verify


def fetch(path, authenticated=True):
    if not authenticated:
        return 403, 'text/html', b'Forbidden'
    data = {
        '/health': {'status': 'ok', 'service': 'safety', 'legacy_models_loaded': False},
        '/ready': {'ready': True, 'built_at': '2026-09-29', 'segments': 2},
        '/api/safety/segments?limit=2': {'segments': [{'segment_id': 'A'}], 'total': 2},
    }
    if path in data:
        return 200, 'application/json', json.dumps(data[path]).encode()
    if path in ('/', '/safety.js', '/safety.css', '/safety-evidence.js'):
        return 200, 'text/plain', b'asset'
    return (409 if path.endswith('commercial=true') else 404), 'application/json', b'{}'


def test_smoke_passes_isolated_ready_private_service():
    report = verify(fetch, require_private=True)
    assert report['status'] == 'passed' and report['private_access_checked']


@pytest.mark.parametrize('path,status,body', [
    ('/ready', 503, {}),
    ('/health', 200, {'status': 'ok', 'service': 'research_and_safety', 'legacy_models_loaded': False}),
    ('/api/research/advanced', 200, {}),
    ('/api/safety/export?commercial=true', 200, {}),
    ('/api/safety/segments?limit=2', 200, {'segments': [], 'total': 0}),
])
def test_smoke_rejects_unready_or_unisolated_service(path, status, body):
    def broken(candidate, authenticated=True):
        if candidate == path:
            return status, 'application/json', json.dumps(body).encode()
        return fetch(candidate, authenticated=authenticated)
    with pytest.raises(RuntimeError):
        verify(broken)


def test_smoke_rejects_public_service_when_private_required():
    with pytest.raises(RuntimeError, match='unauthenticated'):
        verify(lambda path, authenticated=True: fetch(path), require_private=True)

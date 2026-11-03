"""Verify cache policy persistence, exports and executable response caching."""

from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask
import pytest

from app import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path):
    """Create a project-aware disposable backend."""
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'cache.db'}"})
    client = app.test_client()
    client.environ_base["HTTP_X_PROJECT_ID"] = "1"

    return client


def policy(kind: str = "route") -> dict:
    """Return an explicitly public cache policy."""
    return {"kind": kind, "path": "/catalog", "method": "GET", "access": "public",
            "ttl_seconds": 60, "api_type": "rest", "query_keys": ["page"]}


def test_save_conflict_project_and_export(client) -> None:
    """Persist separate revisions and export each predefined template safely."""
    assert len(client.get('/api/caching').json['presets']) == 3

    for revision, kind in enumerate(("route", "redis", "gateway")):
        response = client.put('/api/caching', json={"revision": revision, "configuration": policy(kind)})
        assert response.status_code == 200
        archive = client.post('/api/caching/export', json={"revision": revision + 1})
        assert archive.status_code == 200

        with ZipFile(BytesIO(archive.data)) as bundle:
            config = json.loads(bundle.read('cache-policy.json'))
            assert config['namespace'] == f'project-1:revision-{revision + 1}'
            assert ('gateway.py' if kind == 'gateway' else 'route_cache.py') in bundle.namelist()

    assert client.put('/api/caching', json={"revision": 1, "configuration": policy()}).status_code == 409
    assert client.post('/api/caching/export', json={"revision": 1}).status_code == 409
    project = client.post('/api/projects', json={"name": "Separate", "summary": "Cache isolation"}).json['project']
    assert client.get('/api/caching', headers={'X-Project-ID': str(project['id'])}).json['configuration'] is None
    assert client.get('/api/caching', headers={'X-Project-ID': ''}).status_code == 400
    assert client.get('/api/caching').json['configuration']['kind'] == 'gateway'


@pytest.mark.parametrize('changes', [
    {'ttl_seconds': 0}, {'ttl_seconds': 3601}, {'ttl_seconds': True}, {'method': 'POST'},
    {'access': 'authenticated'}, {'path': '/../../escape'}, {'kind': 'gateway', 'api_type': 'http'},
    {'query_keys': ['a', 'a']}, {'kind': 'unknown'},
])
def test_reject_invalid_policy(client, changes) -> None:
    """Reject unsupported combinations without persisting a revision."""
    response = client.put('/api/caching', json={'revision': 0, 'configuration': {**policy(), **changes}})
    assert response.status_code == 400
    assert client.get('/api/caching').json['revision'] == 0


def test_runtime_hit_variants_expiry_invalidation_and_bypass(monkeypatch) -> None:
    """Execute the exported decorator with real Flask requests and a fake clock."""
    module = run_path(str(ROOT / 'builder-resources/templates/caching/route_cache.py'))
    clock = [100.0]
    monkeypatch.setattr(module['time'], 'monotonic', lambda: clock[0])
    cache = module['MemoryCache'](2)
    app = Flask(__name__)
    calls = []

    @app.get('/catalog')
    @module['cached_response']({**policy(), 'namespace': 'test'}, cache)
    def catalog():
        """Count authoritative reads without user-specific data."""
        calls.append(1)
        return {'calls': len(calls)}

    client = app.test_client()
    assert client.get('/catalog').headers['X-Cache'] == 'MISS'
    assert client.get('/catalog').headers['X-Cache'] == 'HIT'
    assert client.get('/catalog?page=2').headers['X-Cache'] == 'MISS'
    assert client.get('/catalog', headers={'Authorization': 'Bearer example'}).headers.get('X-Cache') is None
    client.set_cookie('session', 'example')
    assert client.get('/catalog').headers.get('X-Cache') is None
    client.delete_cookie('session')
    clock[0] += 61
    assert client.get('/catalog').headers['X-Cache'] == 'MISS'

    for key in list(cache.entries):
        cache.delete(key)

    assert client.get('/catalog').headers['X-Cache'] == 'MISS'
    assert client.get('/catalog?page=3').headers['X-Cache'] == 'MISS'
    assert client.get('/catalog?page=4').headers['X-Cache'] == 'MISS'
    assert len(cache.entries) == 2


@pytest.mark.parametrize('headers', [{'Cache-Control': 'no-store'}, {'Cache-Control': 'private'}, {'Set-Cookie': 'id=x'}, {'Vary': 'Accept'}])
def test_private_responses_never_cached(headers) -> None:
    """Honor response opt-outs even for an explicitly public configured path."""
    module = run_path(str(ROOT / 'builder-resources/templates/caching/route_cache.py'))
    app = Flask(__name__)
    cache = module['MemoryCache']()

    @app.get('/catalog')
    @module['cached_response']({**policy(), 'namespace': 'test'}, cache)
    def catalog():
        """Return an opt-out response."""
        return 'private', 200, headers

    app.test_client().get('/catalog')
    assert len(cache.entries) == 0


def test_redis_adapter_expiry_and_failure(monkeypatch) -> None:
    """Verify Redis protocol calls and outage fallback without a live Redis service."""
    client = MagicMock()
    fake = SimpleNamespace(Redis=SimpleNamespace(from_url=MagicMock(return_value=client)), RedisError=ConnectionError)
    monkeypatch.setitem(sys.modules, 'redis', fake)
    module = run_path(str(ROOT / 'builder-resources/templates/caching/redis_cache.py'))
    cache = module['RedisCache']('redis://localhost:6379/0')
    cache.set('key', {'body': '00'}, 60)
    client.set.assert_called_once_with('key', json.dumps({'body': '00'}), ex=60)
    client.get.return_value = '{"body":"00"}'
    assert cache.get('key') == {'body': '00'}
    client.get.side_effect = ConnectionError('offline')
    assert cache.get('key') is None
    client.delete.side_effect = ConnectionError('offline')
    assert cache.delete('key') is False

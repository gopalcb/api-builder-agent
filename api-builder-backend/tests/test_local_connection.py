"""Verify health checks and cookie-preserving local cross-port requests."""

import pytest

from app import create_app
from models import User, db
from validation import is_local_connection_origin


def test_health_and_preflight_do_not_allocate_users(tmp_path) -> None:
    """Checking a candidate backend never changes the user's current catalog."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'connection.db'}"})
    client = app.test_client()
    origin = {'Origin': 'http://localhost:4200'}
    response = client.get('/api/health', headers=origin)
    assert response.json == {'service': 'api-builder', 'status': 'ok'}
    assert response.headers['Access-Control-Allow-Origin'] == origin['Origin']
    assert response.headers['Access-Control-Allow-Credentials'] == 'true'
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'Set-Cookie' not in response.headers
    preflight = client.options('/api/entities', headers={**origin,
        'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type, X-Project-ID'})
    assert preflight.status_code == 204
    assert 'Set-Cookie' not in preflight.headers

    with app.app_context():
        assert db.session.query(User).count() == 0

    first = client.get('/api/projects', headers=origin)
    assert first.status_code == 200
    assert client.get('/api/projects', headers=origin).json == first.json
    project = first.json['default_project_id']
    assert client.post('/api/entities', headers={**origin, 'X-Project-ID': str(project)}, json={'name': 'LocalEntity'}).status_code == 201
    assert client.get('/api/entities', headers={**origin, 'X-Project-ID': str(project)}).json['entities'][0]['name'] == 'LocalEntity'
    error = client.get('/api/entities', headers=origin)
    assert error.status_code == 400
    assert error.headers['Access-Control-Allow-Origin'] == origin['Origin']

    for bad_origin in ['http://localhost.attacker.test:4200', 'http://127.0.0.1:4200', 'https://localhost:4200', 'null']:
        denied = client.post('/api/projects', headers={'Origin': bad_origin}, json={'name': 'Denied', 'summary': 'Denied'})
        assert denied.status_code == 403
        assert 'Access-Control-Allow-Origin' not in denied.headers

    assert len(client.get('/api/projects').json['projects']) == 1
    assert client.options('/api/projects', headers={**origin, 'Access-Control-Request-Method': 'TRACE'}).status_code == 403
    assert client.options('/api/projects', headers={**origin, 'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'Authorization'}).status_code == 403


@pytest.mark.parametrize('origin,server,expected', [
    ('http://127.0.0.1:4200', 'http://127.0.0.1:5000/', True),
    ('http://localhost:4200', 'http://localhost:5000/', True),
    ('https://[::1]:4200', 'https://[::1]:5000/', True),
    ('http://localhost:0', 'http://localhost:5000/', False),
    ('http://localhost:65536', 'http://localhost:5000/', False),
    ('http://localhost:4200/path', 'http://localhost:5000/', False),
    ('http://user@localhost:4200', 'http://localhost:5000/', False),
    ('http://localhost:4200#fragment', 'http://localhost:5000/', False),
    ('https://example.test', 'https://example.test/', False),
])
def test_local_origin_validation(origin, server, expected) -> None:
    """Origins must be exact loopback hosts with valid ports and matching scheme."""
    assert is_local_connection_origin(origin, server) is expected

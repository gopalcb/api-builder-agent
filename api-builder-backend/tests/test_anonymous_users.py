"""Verify anonymous cookie persistence, ownership boundaries and safe upgrades."""

import re
import sqlite3

from sqlalchemy import select

from app import create_app
from models import Project, ProjectEntityName, User, db
from services import user_service


def test_cookie_identity_and_project_boundaries(tmp_path) -> None:
    """Keep independent browsers isolated across all project operations."""
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'users.db'}"}
    app = create_app(config)
    first, second = app.test_client(), app.test_client()
    response = first.get('/api/projects')
    cookie = first.get_cookie('user_id')
    assert re.fullmatch(r'user-[1-9][0-9]{3}', cookie.value)
    assert cookie.http_only and cookie.same_site == 'Lax' and cookie.expires
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert 'Cookie' in response.headers['Vary']
    assert cookie.value not in response.get_data(as_text=True)
    first_id = response.json['default_project_id']
    second_id = second.get('/api/projects').json['default_project_id']
    assert first_id != second_id
    assert second.get_cookie('user_id').value != cookie.value
    payload = {'name': 'Same name', 'summary': 'Separate owners'}
    project = first.post('/api/projects', json=payload).json['project']
    assert second.post('/api/projects', json=payload).status_code == 201
    assert first.post('/api/projects', json=payload).status_code == 409
    base = f"/api/projects/{project['id']}"

    for method, path in [('put', base), ('delete', base), ('get', base + '/download'),
                         ('get', base + '/openapi'), ('post', base + '/test'),
                         ('post', base + '/build'), ('post', base + '/github')]:
        assert getattr(second, method)(path, json=payload).status_code == 404

    for method, path in [('get', '/entities'), ('post', '/entities'), ('get', '/rbac'),
                         ('put', '/rbac'), ('post', '/rbac/generate'), ('get', '/caching'),
                         ('put', '/caching'), ('get', '/project-documents'),
                         ('put', '/project-documents/overview'), ('post', '/generate-search-configuration'),
                         ('post', '/generate-infrastructure-plan')]:
        assert getattr(second, method)('/api' + path, headers={'X-Project-ID': str(first_id)}, json={}).status_code == 400

    restored = create_app(config).test_client()
    restored.set_cookie('user_id', cookie.value)
    assert restored.get('/projects').json == first.get('/api/projects').json

    with app.app_context():
        user = db.session.get(User, cookie.value)
        assert user.username == cookie.value and user.email == user.password == ''
        assert db.session.get(Project, project['id']).user_id == user.id
        assert db.session.query(User).count() == 2

    first.delete_cookie('user_id')
    assert first.get('/api/projects').json['default_project_id'] not in (first_id, second_id)
    assert first.get_cookie('user_id').value != cookie.value
    first.set_cookie('user_id', 'invalid')
    assert first.get('/api/projects', base_url='https://localhost').status_code == 200
    assert first.get_cookie('user_id').secure


def test_allocation_excludes_used_ids_and_handles_capacity(tmp_path, monkeypatch) -> None:
    """Never reuse allocated numbers, including when the four-digit space is full."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'capacity.db'}"})
    monkeypatch.setattr(user_service.secrets, 'choice', lambda available: available[0])
    first, second = app.test_client(), app.test_client()
    first.get('/api/projects')
    second.get('/api/projects')
    assert first.get_cookie('user_id').value == 'user-1000'
    assert second.get_cookie('user_id').value == 'user-1001'

    with app.app_context():
        db.session.add_all(User(id=f'user-{number}', username=f'user-{number}') for number in range(1002, 10000))
        db.session.commit()

    assert app.test_client().get('/api/projects').status_code == 503
    assert first.get('/api/projects').status_code == 200


def test_existing_database_upgrade_preserves_private_metadata(tmp_path) -> None:
    """Upgrade the old globally unique catalog without exposing or dropping rows."""
    path = tmp_path / 'legacy.db'

    with sqlite3.connect(path) as connection:
        connection.executescript('''
            CREATE TABLE project (id INTEGER PRIMARY KEY, name VARCHAR(100) COLLATE NOCASE NOT NULL UNIQUE, summary TEXT NOT NULL);
            INSERT INTO project VALUES (7, 'Existing', 'Retained');
            CREATE TABLE project_entity_name (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES project(id), name VARCHAR(100) NOT NULL, UNIQUE(project_id, name));
            INSERT INTO project_entity_name VALUES (12, 7, 'PreservedEntity');
        ''')

    config = {'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}'}
    app = create_app(config)
    create_app(config)
    client = app.test_client()
    assert all(project['id'] != 7 for project in client.get('/api/projects').json['projects'])
    assert client.post('/api/projects', json={'name': 'Existing', 'summary': 'New owner'}).status_code == 201

    with app.app_context():
        project = db.session.get(Project, 7)
        assert project.name == 'Existing' and project.summary == 'Retained'
        assert db.session.get(User, project.user_id) is not None
        assert db.session.get(ProjectEntityName, 12).project_id == 7
        assert len(list(db.session.scalars(select(User)))) == 2

    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []

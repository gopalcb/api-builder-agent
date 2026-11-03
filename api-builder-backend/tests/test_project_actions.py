"""Verify project lifecycle, artifact readiness and publication without external calls."""

from io import BytesIO
from zipfile import ZipFile

from app import create_app
from models import Project, ProjectArchive, ProjectRepository, db
from services import github_service


def test_project_edit_archive_and_build(tmp_path) -> None:
    """Persist edits, invalidate stale bundles and retain archived project metadata."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'actions.db'}"})
    client = app.test_client()
    project = client.post('/api/projects', json={'name': 'Build sample', 'summary': 'Original summary'}).json['project']
    base = f"/api/projects/{project['id']}"

    assert client.get(base + '/download').status_code == 409
    spec = client.get(base + '/openapi').json
    assert spec['info']['title'] == 'Build sample'
    assert set(spec['paths']) == {'/health', '/auth/token'}
    assert client.post(base + '/test').status_code == 200
    assert client.post(base + '/build').json['project']['build_ready'] is True
    response = client.get(base + '/download')
    assert response.status_code == 200

    with ZipFile(BytesIO(response.data)) as bundle:
        assert {'project.json', 'builder-configuration.json', 'Dockerfile', 'compose.yaml', 'docs/README.md', 'BUILD-NOTES.md'} <= set(bundle.namelist())
        assert 'Build sample' in bundle.read('docs/README.md').decode()
        assert not any('.venv/' in name or '__pycache__/' in name for name in bundle.namelist())
        assert 'services/logger_service.py' in bundle.namelist()
        assert [name for name in bundle.namelist() if name.startswith('logs/')] == ['logs/.gitkeep']
        assert b'./logs:/app/logs' in bundle.read('compose.yaml')

    updated = client.put(base, json={'name': 'Updated sample', 'summary': 'Changed summary'})
    assert updated.json['project']['name'] == 'Updated sample'
    assert updated.json['project']['build_ready'] is False
    assert client.get(base + '/download').status_code == 409
    assert client.put(base, json={'name': 'Default', 'summary': 'Duplicate'}).status_code == 409
    assert client.delete(base).status_code == 200
    assert project['id'] not in [item['id'] for item in client.get('/api/projects').json['projects']]
    assert client.post(base + '/build').status_code == 404
    assert client.get('/api/project-documents', headers={'X-Project-ID': str(project['id'])}).status_code == 400

    with app.app_context():
        assert db.session.get(Project, project['id']).name == 'Updated sample'
        assert db.session.get(ProjectArchive, project['id']) is not None


def test_github_push_uses_built_files_and_never_stores_token(tmp_path, monkeypatch) -> None:
    """Publish through mocked GitHub objects using a non-force ref update."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'github.db'}"})
    client = app.test_client()
    client.post('/api/projects/1/build')
    calls = []

    def request(token, method, path, payload=None):
        """Model GitHub success while inspecting only this test's synthetic credential."""
        assert token == 'synthetic-test-token'
        calls.append((method, path, payload))

        if path == '/user':
            return {'login': 'tester'}
        if path == '/user/repos':
            assert payload['private'] is True
            return {'default_branch': 'main'}
        if '/git/ref/heads/' in path:
            return {'object': {'sha': 'old-head'}}
        if path.endswith('/git/commits/old-head'):
            return {'tree': {'sha': 'old-tree'}}
        if path.endswith('/git/trees'):
            assert payload['base_tree'] == 'old-tree'
            assert any(item['path'] == 'builder-configuration.json' for item in payload['tree'])
            return {'sha': 'new-tree'}
        if path.endswith('/git/commits'):
            return {'sha': 'new-commit'}

        assert payload == {'sha': 'new-commit', 'force': False}
        return {'object': {'sha': 'new-commit'}}

    monkeypatch.setattr(github_service, 'github_request', request)
    response = client.post('/api/projects/1/github', json={'owner': '', 'name': 'default', 'token': 'synthetic-test-token', 'create': True})
    assert response.status_code == 200
    assert response.json['repository']['url'] == 'https://github.com/tester/default'
    assert calls[-1][0] == 'PATCH'

    with app.app_context():
        row = db.session.get(ProjectRepository, 1)
        assert row.owner == 'tester'
        assert 'token' not in row.__table__.columns.keys()

    assert client.post('/api/projects/1/github', json={'owner': '../bad', 'name': 'default', 'token': 'x', 'create': False}).status_code == 400

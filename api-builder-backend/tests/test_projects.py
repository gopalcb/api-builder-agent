"""Verify project selection, persisted catalogs and configuration isolation."""

from app import create_app
from models import EntityName, RbacConfiguration, Project, ProjectEntityName, ProjectRbacConfiguration, db


def test_project_catalog_and_isolation(tmp_path) -> None:
    """Require context, persist projects and isolate identical entity names and RBAC."""
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'projects.db'}"}
    app = create_app(config)
    client = app.test_client()
    catalog = client.get('/api/projects').json
    assert catalog['default_project_id'] == 1
    assert catalog['projects'][0]['name'] == 'Default'
    response = client.post('/api/projects', json={"name": " Store ", "summary": " Shopping API "})
    assert response.status_code == 201
    second = response.json['project']
    assert second['name'] == 'Store' and second['summary'] == 'Shopping API'
    assert client.post('/api/projects', json={"name": "store", "summary": "Duplicate"}).status_code == 409
    assert client.post('/api/projects', json={"name": "Empty", "summary": " "}).status_code == 400
    for endpoint in ['/api/entities', '/api/rbac']:
        assert client.get(endpoint).status_code == 400
        assert client.get(endpoint, headers={'X-Project-ID': '999'}).status_code == 400
    assert client.post('/api/generate-search-configuration', json={}).status_code == 400
    one = {'X-Project-ID': '1'}
    two = {'X-Project-ID': str(second['id'])}
    first_entity = client.post('/api/entities', headers=one, json={'name': 'Customer'}).json['entity']
    assert client.get('/api/entities', headers=two).json == {'entities': []}
    second_entity = client.post('/api/entities', headers=two, json={'name': 'Customer'}).json['entity']
    assert first_entity['id'] != second_entity['id']
    with app.app_context():
        db.session.add(ProjectRbacConfiguration(project_id=1, revision=3, document={'notes': 'Default only'}))
        db.session.commit()
    assert client.get('/api/rbac', headers=one).json['revision'] == 3
    assert client.get('/api/rbac', headers=two).json == {'revision': 0, 'configuration': None}
    restarted = create_app(config).test_client()
    restarted.set_cookie("user_id", client.get_cookie("user_id").value)
    assert len(restarted.get('/api/projects').json['projects']) == 2
    assert restarted.get('/api/entities', headers=one).json['entities'] == [first_entity]
    assert restarted.get('/api/entities', headers=two).json['entities'] == [second_entity]


def test_legacy_metadata_is_copied_once(tmp_path) -> None:
    """Preserve source tables and copy existing values to Default on first upgrade."""
    config = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'legacy.db'}"}
    app = create_app(config)
    with app.app_context():
        db.session.add(EntityName(name='Existing'))
        db.session.add(RbacConfiguration(id=1, revision=2, document={'notes': 'Legacy'}))
        db.session.commit()
    upgraded = create_app(config)
    create_app(config)
    with upgraded.app_context():
        assert db.session.query(EntityName).count() == 1
        assert db.session.query(ProjectEntityName).count() == 1
        assert db.session.get(ProjectRbacConfiguration, 1).revision == 2
        assert db.session.get(RbacConfiguration, 1).document == {'notes': 'Legacy'}


def test_entity_edit_delete_and_duplicate_names(tmp_path) -> None:
    """Persist renames, reject duplicates and isolate destructive operations."""
    client = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'edit.db'}"}).test_client()
    project = client.get('/api/projects').json['default_project_id']
    headers = {'X-Project-ID': str(project)}
    first = client.post('/api/entities', headers=headers, json={'name': ' Customer '}).json['entity']
    second = client.post('/api/entities', headers=headers, json={'name': 'Order'}).json['entity']
    url = f"/api/entities/{second['id']}"

    assert first['name'] == 'Customer'
    assert client.post('/api/entities', headers=headers, json={'name': ' customer '}).status_code == 409
    assert client.put(url, headers=headers, json={'name': ' CUSTOMER '}).status_code == 409
    assert client.put(url, headers=headers, json={'name': ' '}).status_code == 400
    assert client.put(url, headers=headers, json={'name': ' Orders '}).json['entity']['name'] == 'Orders'
    other = client.post('/api/projects', json={'name': 'Other', 'summary': 'Separate'}).json['project']['id']

    for method in (client.put, client.delete):
        assert method(url, headers={'X-Project-ID': str(other)}, json={'name': 'Wrong'}).status_code == 404

    assert client.delete(url, headers=headers).status_code == 200
    assert client.get('/api/entities', headers=headers).json['entities'] == [first]

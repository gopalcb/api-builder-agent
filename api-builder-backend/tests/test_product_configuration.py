"""Verify project-owned generated definitions, endpoint lifecycle and executable bundles."""

from io import BytesIO
import json
from zipfile import ZipFile

from app import create_app
from services import configuration_service, project_build_service


def test_product_configuration(tmp_path, monkeypatch) -> None:
    """Exercise the real HTTP/persistence/build boundary with a deterministic agent response."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'product.db'}"})
    client = app.test_client()
    project = client.get('/api/projects').json['default_project_id']
    headers = {'X-Project-ID': str(project)}
    entity = client.post('/api/entities', headers=headers, json={'name': 'Product'}).json['entity']
    url = f"/api/entity-configurations/{entity['id']}"
    attributes = [{'name': name, 'data_type': kind, 'nullable': False, 'description': name}
                  for name, kind in [('name', 'string'), ('price', 'decimal'), ('stock', 'integer')]]
    calls = []
    monkeypatch.setattr(project_build_service, 'run_agent_worker', lambda *args: {
        'record_service': (project_build_service.TEMPLATE / 'services/record_service.py').read_text(),
        'validation': (project_build_service.TEMPLATE / 'validation.py').read_text(),
    })
    monkeypatch.setattr(project_build_service, 'test_implementation_container', lambda directory: None)

    def worker(agent, context, timeout):
        """Capture the project-filtered context while replacing only the provider boundary."""
        calls.append(context)

        return {'entity_id': entity['id'], 'attributes': attributes, 'relationships': []}

    monkeypatch.setattr(configuration_service, 'run_agent_worker', worker)
    assert client.post(f'/api/projects/{project}/build').status_code == 400
    generated = client.post(url, headers=headers, json={'prompt': 'Product with name, price and stock', 'revision': 0})
    assert generated.status_code == 200, generated.json
    assert generated.json['attributes'] == attributes
    assert generated.json['revision'] == 1
    assert client.get(url, headers=headers).json == generated.json
    assert calls[0]['entity']['name'] == 'Product'
    assert client.post(url, headers=headers, json={'prompt': 'Stale', 'revision': 0}).status_code == 409
    assert len(calls) == 1
    other = client.post('/api/projects', json={'name': 'Other', 'summary': 'Isolation'}).json['project']['id']
    assert client.get(url, headers={'X-Project-ID': str(other)}).status_code == 404
    assert app.test_client().get(url, headers=headers).status_code == 400
    endpoints = client.get('/api/endpoints', headers=headers).json
    assert len(endpoints['routes']) == 5
    endpoints['routes'].append({'id': 99, 'entity': 'Product', 'operation': 'sell', 'method': 'POST',
                               'path': '/product/sell', 'access': 'authenticated', 'type': 'authenticated', 'prompt': 'Sell stock'})
    saved = client.put('/api/endpoints', headers=headers, json=endpoints)
    assert saved.status_code == 200, saved.json
    assert client.put('/api/endpoints', headers=headers, json=endpoints).status_code == 409
    assert client.get('/api/endpoints', headers=headers).json == saved.json
    built = client.post(f'/api/projects/{project}/build')
    assert built.status_code == 200, built.json

    with ZipFile(BytesIO(client.get(f'/api/projects/{project}/download').data)) as archive:
        assert 'Dockerfile' in archive.namelist()
        assert 'stack.py' not in archive.namelist()
        snapshot = json.loads(archive.read('builder-configuration.json'))
        assert snapshot['entities'][0]['attributes'] == attributes
        assert len(snapshot['routes']) == 6

    changed = saved.json
    changed['routes'][-1]['path'] = '/product/{id}/sell'
    assert client.put('/api/endpoints', headers=headers, json=changed).status_code == 200
    assert client.get(f'/api/projects/{project}/download').status_code == 409
    assert client.put(f"/api/entities/{entity['id']}", headers=headers, json={'name': 'Products'}).status_code == 200
    assert all(route['entity'] == 'Products' for route in client.get('/api/endpoints', headers=headers).json['routes'])
    assert client.delete(f"/api/entities/{entity['id']}", headers=headers).status_code == 200
    assert client.get(url, headers=headers).status_code == 404
    assert client.get('/api/endpoints', headers=headers).json['routes'] == []

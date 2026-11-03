"""Check project isolation and durable, conflict-protected Markdown editing."""

from app import create_app


def test_project_documents_and_edit_conflicts(tmp_path) -> None:
    """Generate from selected metadata, save edits, reject stale writes and reload."""
    config = {'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'docs.db'}"}
    client = create_app(config).test_client()
    project = client.post('/api/projects', json={'name': 'Other', 'summary': 'Other summary'}).json['project']
    one, two = {'X-Project-ID': '1'}, {'X-Project-ID': str(project['id'])}
    assert client.get('/api/project-documents').status_code == 400
    assert client.get('/api/project-documents/overview', headers={'X-Project-ID': '999'}).status_code == 400
    client.post('/api/entities', headers=one, json={'name': 'PrivateEntity'})
    assert 'PrivateEntity' in client.get('/api/project-documents/entities', headers=one).json['document']['content']
    assert 'PrivateEntity' not in client.get('/api/project-documents/entities', headers=two).json['document']['content']
    assert all('content' not in item for item in client.get('/api/project-documents', headers=one).json['documents'])
    doc = client.get('/api/project-documents/overview', headers=one).json['document']
    payload = {**doc, 'content': '# Edited documentation'}
    assert client.put('/api/project-documents/overview', headers=one, json=payload).status_code == 200
    assert client.put('/api/project-documents/overview', headers=one, json=payload).status_code == 409
    assert client.put('/api/project-documents/overview', headers=two, json=payload).status_code == 409
    assert client.get('/api/project-documents/overview', headers=two).json['document']['content'].startswith('# Other')
    assert client.get('/api/project-documents/missing', headers=one).status_code == 404
    assert client.put('/api/project-documents/overview', headers=one, json={'content': 'x' * 48001}).status_code == 400
    restarted = create_app(config).test_client()
    restarted.set_cookie("user_id", client.get_cookie("user_id").value)
    assert restarted.get('/api/project-documents/overview', headers=one).json['document']['content'] == '# Edited documentation'

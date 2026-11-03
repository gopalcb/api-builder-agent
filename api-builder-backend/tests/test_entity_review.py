"""Verify configuration-only generation, safe live logs, edits and explicit implementation."""

from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile
from io import BytesIO

from app import create_app
from services import configuration_service, project_build_service
from shared.logging_service import log_event, LOG_CONTEXT, worker_environment


def test_entity_review_logs_edits_and_build(tmp_path, monkeypatch):
    """Review a persisted schema before the implementation agent is invoked by Build."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'db'}",
                      'GENERATION_LOG_ROOT': tmp_path / 'runs'})
    client = app.test_client()
    project = client.get('/api/projects').json['default_project_id']
    headers = {'X-Project-ID': str(project)}
    entity = client.post('/api/entities', headers=headers, json={'name': 'Product'}).json['entity']
    url = f"/api/entity-configurations/{entity['id']}"
    definition = {'entity_id': entity['id'], 'attributes': [
        {'name': 'price', 'data_type': 'decimal', 'nullable': False, 'description': 'Hidden explanation'},
        {'name': 'stock', 'data_type': 'integer', 'nullable': False, 'description': ''},
    ], 'relationships': []}
    implementations = []
    contexts = []

    def worker(agent, context, timeout):
        """Emit real structured events through the current generation context."""
        contexts.append(deepcopy(context))
        log_event('agent.worker.started', agent=agent, prompt='must-not-be-exposed')
        assert LOG_CONTEXT.get()['entity_id'] == entity['id']
        subprocess.run([sys.executable, '-c', "import runtime; from shared.logging_service import configure_worker, log_event; configure_worker(); log_event('agent.child.step', agent='entity-builder')"], env=worker_environment(), check=True)
        return definition

    def implement(agent, context, timeout):
        """Replace the model boundary while checking exactly when it is invoked."""
        implementations.append(context)
        assert agent == 'api-implementation-builder'
        return {'record_service': (project_build_service.TEMPLATE / 'services/record_service.py').read_text(),
                'validation': (project_build_service.TEMPLATE / 'validation.py').read_text()}

    monkeypatch.setattr(configuration_service, 'run_agent_worker', worker)
    monkeypatch.setattr(project_build_service, 'run_agent_worker', implement)
    checked = []
    monkeypatch.setattr(project_build_service, 'test_implementation_container', lambda directory: checked.append(directory))
    run_id = str(uuid4())
    log_url = url + '/logs/' + run_id
    assert client.get(log_url, headers=headers).json['status'] == 'pending'
    result = client.post(url, headers=headers, json={'prompt': 'Product price and stock', 'revision': 0, 'run_id': run_id})
    assert result.status_code == 200, result.json
    logs = client.get(log_url, headers=headers).json
    assert logs['status'] == 'completed'
    assert any(entry['event'] == 'agent.worker.started' for entry in logs['entries'])
    assert any(entry['event'] == 'agent.child.step' for entry in logs['entries'])
    assert any(entry['event'] == 'entity.generation.completed' for entry in logs['entries'])
    assert 'must-not-be-exposed' not in json.dumps(logs)
    assert 'project_id' not in json.dumps(logs)
    assert client.get(log_url + '?cursor=' + str(logs['cursor']), headers=headers).json['entries'] == []
    assert client.get(log_url + '?cursor=-1', headers=headers).status_code == 400
    assert client.get(url + '/logs/invalid', headers=headers).status_code == 400
    other = client.post('/api/projects', json={'name': 'Other', 'summary': 'Isolation check'}).json['project']['id']
    assert client.get(log_url, headers={'X-Project-ID': str(other)}).status_code == 404
    assert app.test_client().get(log_url, headers=headers).status_code == 400
    assert not implementations

    attributes = deepcopy(result.json['attributes'])
    attributes[0].update(name='cost', data_type='float', nullable=True)
    edited = client.put(url, headers=headers, json={'revision': 1, 'attributes': attributes})
    assert edited.status_code == 200, edited.json
    assert edited.json['attributes'][0]['name'] == 'cost'
    assert edited.json['attributes'][0]['nullable'] is True
    assert client.put(url, headers=headers, json={'revision': 1, 'attributes': attributes}).status_code == 409
    invalid = deepcopy(attributes)
    invalid[0]['data_type'] = 'executable'
    assert client.put(url, headers=headers, json={'revision': 2, 'attributes': invalid}).status_code == 400
    assert client.put(url, headers=headers, json={'revision': 2, 'attributes': attributes[:1]}).status_code == 200
    assert len(client.get(url, headers=headers).json['attributes']) == 1
    assert not implementations

    prompt_update = client.post(url, headers=headers, json={'revision': 3, 'prompt': 'Keep cost; restore stock', 'run_id': str(uuid4())})
    assert prompt_update.status_code == 200
    assert contexts[-1]['entity']['attributes'][0]['name'] == 'cost'
    assert not implementations
    built = client.post(f'/api/projects/{project}/build')
    assert built.status_code == 200, built.json
    assert len(implementations) == len(checked) == 1
    assert implementations[0]['configuration']['entities'][0]['revision'] == 4
    with ZipFile(BytesIO(client.get(f'/api/projects/{project}/download').data)) as archive:
        assert 'services/record_service.py' in archive.namelist()
        assert 'Dockerfile' in archive.namelist()
    assert client.put(url, headers=headers, json={'revision': 4, 'attributes': attributes}).status_code == 200
    assert client.get(f'/api/projects/{project}/download').status_code == 409


def test_generation_failure_logs_and_preserves_definition(tmp_path, monkeypatch):
    """Failed generation retains actual error events, without exposing exception text."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'db'}",
                      'GENERATION_LOG_ROOT': tmp_path / 'runs'})
    client = app.test_client()
    project = client.get('/api/projects').json['default_project_id']
    headers = {'X-Project-ID': str(project)}
    entity = client.post('/api/entities', headers=headers, json={'name': 'Failure test'}).json['entity']
    run_id = str(uuid4())
    url = f"/api/entity-configurations/{entity['id']}"

    def failure(*args):
        """Model a provider error with a value that must never enter public logs."""
        raise RuntimeError('private-provider-message')

    monkeypatch.setattr(configuration_service, 'run_agent_worker', failure)
    assert client.post(url, headers=headers, json={'prompt': 'Generate', 'revision': 0, 'run_id': run_id}).status_code == 502
    result = client.get(url + '/logs/' + run_id, headers=headers).json
    assert result['status'] == 'failed'
    assert any(entry['level'] == 'ERROR' for entry in result['entries'])
    assert 'private-provider-message' not in json.dumps(result)
    assert client.get(url, headers=headers).json['revision'] == 0
    assert client.post(url, headers=headers, json={'prompt': 'Retry', 'revision': 0, 'run_id': run_id}).status_code == 409
    assert LOG_CONTEXT.get() == {}


def test_generated_code_is_checked_only_inside_isolated_docker(monkeypatch):
    """Keep implementation execution off the host and clean up disposable resources."""
    commands = []

    def execute(command, **kwargs):
        """Inspect the process boundary without executing model-written code."""
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(project_build_service.subprocess, 'run', execute)
    project_build_service.test_implementation_container('/tmp/reviewed-generated-api')
    assert commands[0][:2] == ['docker', 'build']
    run = commands[1]
    assert run[:2] == ['docker', 'run']
    assert run[run.index('--network') + 1] == 'none'
    assert '--read-only' in run and '--cap-drop' in run
    assert '--mount' not in run and '-v' not in run
    assert run[-6:] == ['python', '-m', 'unittest', 'discover', '-s', 'tests']
    assert commands[-2][:3] == ['docker', 'rm', '-f']
    assert commands[-1][:4] == ['docker', 'image', 'rm', '-f']


def test_implementation_agent_assets_use_the_shared_runtime_contract():
    """Validate the new registered workflow metadata before invoking a provider."""
    from runtime.registry import AGENTS
    from shared.agent_response_validator import validate_agent_assets

    registration = AGENTS['api-implementation-builder']
    validate_agent_assets('Implement reviewed API', registration.load_schema())
    assert registration.create_workflow() is not None


def test_project_build_logs_are_safe_scoped_and_incremental(tmp_path, monkeypatch):
    """Expose build worker events without revealing private fields or other owners."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'db'}",
                      'GENERATION_LOG_ROOT': tmp_path / 'runs'})
    client = app.test_client()
    project = client.get('/api/projects').json['default_project_id']
    run_id = str(uuid4())
    url = f'/api/projects/{project}/build/logs/{run_id}'

    def check(project, build):
        log_event('build.worker.step', agent='implementation', prompt='private prompt')
        return {'message': 'Built'}

    monkeypatch.setattr('routing.run_project_check', check)
    assert client.get(url).json['status'] == 'pending'
    assert client.post(f'/api/projects/{project}/build', json={'run_id': run_id}).status_code == 200
    result = client.get(url).json
    assert result['status'] == 'completed'
    assert any(entry['event'] == 'build.worker.step' for entry in result['entries'])
    assert 'private prompt' not in json.dumps(result)
    assert client.get(url + '?cursor=' + str(result['cursor'])).json['entries'] == []
    assert app.test_client().get(url).status_code == 404
    assert client.get(url + '?cursor=-1').status_code == 400
    assert client.post(f'/api/projects/{project}/build', json={'run_id': run_id}).status_code == 409

    def failed(project, build):
        raise RuntimeError('private failure')

    monkeypatch.setattr('routing.run_project_check', failed)
    failed_run = str(uuid4())
    assert client.post(f'/api/projects/{project}/build', json={'run_id': failed_run}).status_code == 400
    failure = client.get(f'/api/projects/{project}/build/logs/{failed_run}').json
    assert failure['status'] == 'failed'
    assert 'private failure' not in json.dumps(failure)
    assert any(entry['level'] == 'ERROR' for entry in failure['entries'])

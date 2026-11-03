"""Verify project isolation, code reuse and durable real-run report handling."""

import fcntl
from pathlib import Path
import subprocess
import time

import pytest

from app import create_app
from services import load_testing_service as service

CONFIG = {'prompt': 'Test all read endpoints', 'host': 'http://127.0.0.1:8080',
          'users': 2, 'spawnRate': 1, 'duration': 2, 'waitMin': 0, 'waitMax': 1}
ROUTES = [{'path': '/product/list', 'operation': 'list', 'method': 'GET', 'access': 'authenticated'}]
CSV = '''Type,Name,Request Count,Failure Count,Average Response Time,Requests/s,50%,90%,95%,99%
GET,/product/list,10,0,12,5,10,15,20,30
,Aggregated,10,0,12,5,10,15,20,30
'''


def test_scenario_cache_and_validation(tmp_path):
    """Reuse unchanged generated source and reject invented or unsafe scenarios."""
    configuration, scenario, target = service.validate_configuration(CONFIG, ROUTES)
    assert target == 'http://host.docker.internal:8080'
    fingerprint, changed = service.prepare_code(tmp_path, scenario)
    assert changed
    timestamp = (tmp_path / 'locustfile.py').stat().st_mtime_ns
    assert service.prepare_code(tmp_path, scenario) == (fingerprint, False)
    assert (tmp_path / 'locustfile.py').stat().st_mtime_ns == timestamp
    assert service.prepare_code(tmp_path, [{**scenario[0], 'path': '/products/list'}])[1]
    (tmp_path / 'locustfile.py').unlink()
    assert service.prepare_code(tmp_path, scenario)[1]

    for change in [{'host': 'http://example.com:8080'}, {'host': 'http://localhost:5000'},
                   {'host': 'http://localhost:8080/private'}, {'waitMin': 2},
                   {'prompt': 'POST /product/list'}, {'prompt': 'GET /missing'},
                   {'prompt': 'custom scenario'}, {'host': 'http://localhost:99999'}]:
        with pytest.raises(ValueError):
            service.validate_configuration({**CONFIG, **change}, ROUTES)


def test_run_storage_ownership_and_recovery(tmp_path, monkeypatch):
    """Use the HTTP lifecycle while replacing only the Docker process boundary."""
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'db'}",
                      'LOAD_TEST_ROOT': tmp_path / 'load'})
    client = app.test_client()
    project = client.get('/api/projects').json['default_project_id']
    headers = {'X-Project-ID': str(project)}
    directory = tmp_path / 'load' / f'project-{project}'
    assert client.get('/api/load-testing', headers=headers).json == {'configuration': None, 'run': None, 'report': None}
    assert client.post('/api/entities', headers=headers, json={'name': 'Product'}).status_code == 201
    assert app.test_client().get('/api/load-testing', headers=headers).status_code == 400
    other_client = app.test_client()
    other_client.get('/api/projects')
    assert other_client.get('/api/load-testing', headers=headers).status_code == 400
    assert client.post('/api/load-testing', headers=headers, json={**CONFIG, 'users': 101}).status_code == 400

    calls = []

    def docker(command, **kwargs):
        """Write real CSV fixture files at the container mount destination."""
        calls.append(command)
        if command[1] == 'run':
            mount = command[command.index('--mount') + 1]
            folder = Path(mount.split('source=', 1)[1].split(',target=')[0])
            (folder / 'results_stats.csv').write_text(CSV)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(service.subprocess, 'run', docker)
    for expected_updated in [True, False]:
        response = client.post('/api/load-testing', headers=headers, json=CONFIG)
        assert response.status_code == 202, response.json
        assert response.json['run']['codeUpdated'] is expected_updated
        for _ in range(100):
            state = client.get('/api/load-testing', headers=headers).json
            if state['run']['status'] != 'running':
                break
            time.sleep(0.01)
        assert state['report']['status'] == 'passed', state
        assert state['report']['metrics']['requests'] == 10
        assert state['report']['completedAt']
        assert service.read_json(directory / 'last-report.json') == state['report']
        assert (directory / 'runs' / state['report']['id'] / 'report.json').exists()

    other = client.post('/api/projects', json={'name': 'Another', 'summary': 'Separate'}).json['project']['id']
    assert client.get('/api/load-testing', headers={'X-Project-ID': str(other)}).json['report'] is None
    assert len([command for command in calls if command[1] == 'run']) == 2
    assert client.get('/api/load-testing', headers=headers).json['report']['status'] == 'passed'

    with (directory / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert client.post('/api/load-testing', headers=headers, json=CONFIG).status_code == 409

    stale = {**state['run'], 'status': 'running'}
    service.save_json(directory / 'run.json', stale)
    assert client.get('/api/load-testing', headers=headers).json['run']['status'] == 'interrupted'


@pytest.mark.parametrize('outcome', ['missing', 'failed', 'timeout', 'zero'])
def test_failed_runs_never_pass(tmp_path, monkeypatch, outcome):
    """Preserve failures, empty results and timeouts as saved failed reports."""
    service.prepare_code(tmp_path, [{'path': '/product/list', 'access': 'authenticated'}])
    run = {'id': outcome, 'projectId': 1, 'status': 'running', 'startedAt': service.now(),
           'configuration': CONFIG, 'endpoints': ['/product/list'], 'codeUpdated': True}
    lock = (tmp_path / '.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX)

    def docker(command, **kwargs):
        """Inject process and request errors independently of report persistence."""
        if command[1] == 'run':
            if outcome == 'missing':
                raise FileNotFoundError('docker')
            if outcome == 'timeout':
                raise subprocess.TimeoutExpired(command, 3)
            text = CSV.replace(',10,0,', ',10,2,') if outcome == 'failed' else CSV.replace(',10,0,', ',0,0,').replace(',10,15,20,30', ',N/A,N/A,N/A,N/A')
            (tmp_path / 'runs' / outcome / 'results_stats.csv').write_text(text)
        return subprocess.CompletedProcess(command, 1 if outcome == 'failed' else 0)

    monkeypatch.setattr(service.subprocess, 'run', docker)
    service.execute_run(tmp_path, run, 'http://host.docker.internal:8080', lock)
    report = service.read_json(tmp_path / 'last-report.json')
    assert report['status'] == 'failed'
    assert report['error']
    assert report['completedAt']
    assert lock.closed

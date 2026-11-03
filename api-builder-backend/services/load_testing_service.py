"""Generate cached project scenarios and persist real container load-test results."""

from contextvars import copy_context
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
from pathlib import Path
import re
import subprocess
from threading import Thread
from urllib.parse import urlsplit
from uuid import uuid4

from flask import current_app, g
from jsonschema import validate
from werkzeug.exceptions import Conflict

from services.configuration_service import read_endpoints
from services.logger_service import log_event, log_function, LogStep

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'locustio/locust:2.47.0'
CONFIG_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['prompt', 'host', 'users', 'spawnRate', 'duration', 'waitMin', 'waitMax'],
    'properties': {
        'prompt': {'type': 'string', 'minLength': 1, 'maxLength': 4000, 'pattern': r'\S'},
        'host': {'type': 'string', 'maxLength': 250},
        'users': {'type': 'integer', 'minimum': 1, 'maximum': 100},
        'spawnRate': {'type': 'number', 'minimum': 0.1, 'maximum': 100},
        'duration': {'type': 'integer', 'minimum': 1, 'maximum': 3600},
        'waitMin': {'type': 'number', 'minimum': 0, 'maximum': 300},
        'waitMax': {'type': 'number', 'minimum': 0, 'maximum': 300},
    },
}


def now() -> str:
    """Use timezone-qualified timestamps for stored and displayed run times."""
    return datetime.now(timezone.utc).isoformat()


@log_function
def save_json(path: Path, value: dict) -> None:
    """Atomically replace one JSON document without exposing partial reports."""
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def read_json(path: Path):
    """Read a previously committed document, or an explicit empty state."""
    return json.loads(path.read_text()) if path.exists() else None


def read_run_logs(directory: Path, run: dict | None) -> list:
    """Return safe line-oriented runner output for the current project run."""
    if not run:
        return []
    path = directory / 'runs' / run['id'] / 'runner.log'
    if not path.exists():
        return []
    return path.read_text(errors='replace').splitlines()[-200:]


def load_state(directory: Path, run: dict | None) -> dict:
    """Build the stable load-testing response and attach logs when available."""
    state = {'configuration': read_json(directory / 'configuration.json'),
             'run': run, 'report': read_json(directory / 'last-report.json')}
    if run:
        state['logs'] = read_run_logs(directory, run)
    return state


def project_directory() -> Path:
    """Derive storage only from the ownership-checked project ID."""
    directory = Path(current_app.config.get('LOAD_TEST_ROOT', ROOT / 'generated-artifacts/load-testing')) / f'project-{g.project_id}'
    directory.mkdir(parents=True, exist_ok=True)

    return directory


@log_function
def read_load_testing() -> dict:
    """Return durable state and mark an abandoned process as interrupted."""
    directory = project_directory()
    with (directory / '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            run = read_json(directory / 'run.json')
            return load_state(directory, run)

        run = read_json(directory / 'run.json')
        if run and run['status'] == 'running':
            cleanup_container('api-builder-load-' + run['id'])
            run.update(status='interrupted', completedAt=now(), error='Builder stopped before the run finished. Run load testing again.')
            save_json(directory / 'run.json', run)

        return load_state(directory, run)


@log_function
def validate_configuration(configuration: dict, routes: list) -> tuple:
    """Bound local workloads and resolve explicit paths without inventing requests."""
    validate(configuration, CONFIG_SCHEMA)
    url = urlsplit(configuration['host'].strip())
    if (url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'}
            or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'}):
        raise ValueError('Use the deployed local API origin, for example http://127.0.0.1:8080.')

    if not url.port or url.port in {4200, 5000}:
        raise ValueError('Use the generated API port, not the builder UI or backend port.')

    if configuration['waitMin'] > configuration['waitMax']:
        raise ValueError('Minimum wait cannot exceed maximum wait.')

    prompt = configuration['prompt'].strip()
    paths = set(re.findall(r'/[A-Za-z0-9_/{}/-]+', prompt))
    selected = [route for route in routes if not paths or route['path'] in paths]
    if paths - {route['path'] for route in selected}:
        raise ValueError('The prompt contains an endpoint that is not configured in this project.')

    if not paths:
        if not re.fullmatch(r'(?:test\s+)?all\s+(?:read|list)\s+endpoints[.!]?', prompt, re.IGNORECASE):
            raise ValueError('Enter "Test all read endpoints" or the exact list endpoint paths to test.')
        selected = [route for route in selected if route['operation'] == 'list' and route['method'] == 'GET']

    if not selected or any(route['operation'] != 'list' or route['method'] != 'GET' or '{' in route['path'] for route in selected):
        raise ValueError('Select GET list endpoints. Other operations require fixtures and are not supported by this load scenario.')

    if re.search(r'\b(create|update|delete|sell|POST|PATCH|PUT|DELETE)\b', prompt, re.IGNORECASE):
        raise ValueError('This load scenario supports read-only list endpoints; mutation flows are not supported.')

    configuration = {**configuration, 'host': configuration['host'].strip().rstrip('/'), 'prompt': prompt}
    scenario = sorted([{'path': route['path'], 'access': route['access']} for route in selected], key=lambda item: item['path'])

    return configuration, scenario, f'http://host.docker.internal:{url.port}'


@log_function
def prepare_code(directory: Path, scenario: list) -> tuple:
    """Rewrite generated code only when its actual content changes or is missing."""
    template = (ROOT / 'builder-resources/templates/load-testing/locustfile.py').read_text()
    code = template.replace("'__ROUTES_JSON__'", repr(json.dumps(scenario, sort_keys=True)))
    path = directory / 'locustfile.py'
    changed = not path.exists() or path.read_text() != code
    if changed:
        path.write_text(code)

    return hashlib.sha256(code.encode()).hexdigest(), changed


@log_function
def start_load_testing(configuration: dict) -> dict:
    """Validate synchronously, then return while a project-locked worker executes."""
    configuration, scenario, target = validate_configuration(configuration, read_endpoints()['routes'])
    directory = project_directory()
    lock = (directory / '.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock.close()
        raise Conflict('Load testing is already running for this project.') from error

    try:
        fingerprint, changed = prepare_code(directory, scenario)
        run = {'id': uuid4().hex, 'projectId': g.project_id, 'status': 'running', 'startedAt': now(),
               'codeUpdated': changed, 'codeFingerprint': fingerprint, 'configuration': configuration,
               'endpoints': [route['path'] for route in scenario]}
        save_json(directory / 'configuration.json', configuration)
        save_json(directory / 'run.json', run)
        worker = Thread(target=copy_context().run, args=(execute_run, directory, run, target, lock), daemon=True)
        worker.start()
    except (OSError, RuntimeError):
        lock.close()
        raise

    return {'run': run}


@log_function
def parse_statistics(path: Path) -> tuple:
    """Convert Locust CSV metrics into the stable JSON report contract."""
    if not path.exists():
        return {}, []

    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))

    endpoints = []
    total = {}
    for row in rows:
        metric = {'path': row['Name'], 'requests': int(row['Request Count']), 'failures': int(row['Failure Count']),
                  'average': round(float(row['Average Response Time']), 2), 'rps': round(float(row['Requests/s']), 2),
                  **{f'p{percent}': None if row[f'{percent}%'] == 'N/A' else float(row[f'{percent}%'])
                     for percent in [50, 90, 95, 99]}}
        if row['Name'] == 'Aggregated':
            total = metric
        else:
            endpoints.append(metric)

    return total, endpoints


@log_function
def execute_run(directory: Path, run: dict, target: str, lock) -> None:
    """Run only Docker workloads and retain failed as well as successful reports."""
    run_directory = directory / 'runs' / run['id']
    name = 'api-builder-load-' + run['id']
    configuration = run['configuration']
    report = {**run, 'status': 'failed', 'metrics': {}, 'statistics': [], 'runner': IMAGE}
    try:
        run_directory.mkdir(parents=True)
        (run_directory / 'locustfile.py').write_text((directory / 'locustfile.py').read_text())
        command = ['docker', 'run', '--rm', '--name', name, '--add-host', 'host.docker.internal:host-gateway',
                   '--user', '0:0', '--cpus', '2', '--memory', '512m',
                   '--mount', f'type=bind,source={run_directory},target=/mnt/locust',
                   '-e', f"WAIT_MIN={configuration['waitMin']}", '-e', f"WAIT_MAX={configuration['waitMax']}",
                   IMAGE, '-f', '/mnt/locust/locustfile.py', '--headless', '--host', target,
                   '--users', str(configuration['users']), '--spawn-rate', str(configuration['spawnRate']),
                   '--run-time', str(configuration['duration']) + 's', '--stop-timeout', '10',
                   '--csv', '/mnt/locust/results', '--only-summary']
        with LogStep('load_testing.container', project_id=run['projectId']), (run_directory / 'runner.log').open('w') as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=configuration['duration'] + 180, check=False)

        total, endpoints = parse_statistics(run_directory / 'results_stats.csv')
        report.update(metrics=total, statistics=endpoints, exitCode=result.returncode)
        exercised = {item['path'] for item in endpoints if item['requests'] > 0}
        if result.returncode == 0 and total.get('requests', 0) > 0 and not total.get('failures') and exercised == set(run['endpoints']):
            report['status'] = 'passed'
        else:
            report['error'] = 'Run failed or did not exercise every selected endpoint. Check target availability, local mock authentication and endpoint failures.'
            log_event('load_testing.failed', level=logging.ERROR, returncode=result.returncode, project_id=run['projectId'])
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
        report['error'] = 'Load runner failed. Ensure Docker is running and the local target is available; see this run’s runner.log.'
        log_event('load_testing.failed', level=logging.ERROR, error_type=type(error).__name__, project_id=run['projectId'])
    finally:
        cleanup_container(name)

        report['completedAt'] = now()
        try:
            save_json(run_directory / 'report.json', report)
            save_json(directory / 'last-report.json', report)
            save_json(directory / 'run.json', {key: value for key, value in report.items() if key not in {'metrics', 'statistics'}})
        finally:
            lock.close()


@log_function
def cleanup_container(name: str) -> None:
    """Remove the specific run container after timeout or interrupted execution."""
    try:
        result = subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=15, check=False)
        if result.returncode and b'No such container' not in (result.stderr or b''):
            log_event('load_testing.cleanup_failed', level=logging.ERROR, returncode=result.returncode)
    except (OSError, subprocess.TimeoutExpired) as error:
        log_event('load_testing.cleanup_failed', level=logging.ERROR, error_type=type(error).__name__)

"""Implement and package the reviewed container API only on an explicit Build."""

import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from runtime.worker import run_agent_worker
from runtime.registry import AGENTS
from zipfile import ZIP_DEFLATED, ZipFile

from flask import g, current_app
from sqlalchemy import select
from werkzeug.exceptions import Conflict

from models import Project, ProjectBuild, ProjectCachingConfiguration, ProjectEntityName, ProjectRbacConfiguration, ProjectRepository, db
from services.document_service import read_documents
from services.observability_service import read_observability
from services.configuration_service import read_definition, read_endpoints

from services.logger_service import log_function, log_event, LogStep

TEMPLATE = Path(__file__).resolve().parents[2] / 'builder-resources/templates/container-api'
RUNNING_ROOT = Path(__file__).resolve().parents[2] / 'generated-artifacts/running-api'


@log_function
def project_slug(name: str) -> str:
    """Map a display name to a bounded, safe repository and starter name."""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:32].rstrip('-') or 'api-project'


@log_function
def build_files(project: Project) -> dict:
    """Render a deterministic artifact; saved configuration is data, never executable code."""
    files = {}

    for path in TEMPLATE.rglob('*'):
        if path.is_file() and not any(part in {'__pycache__', '.venv', 'cdk.out', 'node_modules', 'logs'} for part in path.relative_to(TEMPLATE).parts):
            files[path.relative_to(TEMPLATE).as_posix()] = path.read_text()

    logger_source = TEMPLATE.parents[2] / 'builder-agents/shared/logging_service.py'
    files['services/logger_service.py'] = logger_source.read_text().replace(
        "Path(__file__).resolve().parents[2] / 'logs'", "Path(__file__).resolve().parents[1] / 'logs'")
    files['services/telemetry_service.py'] = (logger_source.parent / 'telemetry_service.py').read_text()
    files['logs/.gitkeep'] = ''
    implementation = AGENTS['api-implementation-builder'].directory
    files['implementation-source.json'] = json.dumps({'fingerprint': hashlib.sha256(
        (implementation / 'agent.py').read_bytes() + (implementation / 'output-schema.py').read_bytes()).hexdigest()})

    g.project_id = project.id
    snapshot = {'project': project.to_dict(), 'entities': [dict(name=row.name, **read_definition(row.id)) for row in db.session.scalars(
        select(ProjectEntityName).where(ProjectEntityName.project_id == project.id).order_by(ProjectEntityName.id))],
        'routes': read_endpoints()['routes'], 'authentication': {'mode': 'local-mock'},
        'observability': read_observability()['configuration']}

    for key, model in [('rbac', ProjectRbacConfiguration), ('caching', ProjectCachingConfiguration)]:
        row = db.session.get(model, project.id)
        snapshot[key] = row.document if row else None

    files['project.json'] = json.dumps({'project': project_slug(project.name), 'stage': 'dev'}, indent=2) + '\n'
    files['builder-configuration.json'] = json.dumps(snapshot, indent=2, sort_keys=True) + '\n'

    for document in read_documents():
        files['docs/' + document['filename']] = document['content']

    files['BUILD-NOTES.md'] = ('# Local container API\n\nSaved entity schemas and endpoint operations drive this API. '
        'Run docker compose up --build -d. Authentication uses local mock bearer tokens only. '
        'Search, RBAC and cache proposals are snapshots, not runtime integrations. No cloud infrastructure is generated.\n')
    files['openapi.json'] = json.dumps(project_openapi(project), indent=2) + '\n'
    files['.gitignore'] = 'logs/*\n!logs/.gitkeep\n.venv/\n__pycache__/\ncdk.out/\n.env\n'

    return files


@log_function
def fingerprint(files: dict) -> str:
    """Hash source and saved configuration so stale artifacts cannot be downloaded or pushed."""
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


@log_function
def test_files(files: dict, container: bool = False) -> None:
    """Check syntax and exercise trusted source locally or agent output inside Docker."""
    for name, content in files.items():
        if name.endswith('.py'):
            compile(content, name, 'exec')
        elif name.endswith('.json'):
            json.loads(content)

    log_event('build.syntax_validated', count=len(files))
    snapshot = json.loads(files['builder-configuration.json'])

    for entity in snapshot['entities']:
        if not entity['attributes']:
            raise ValueError(f"Generate attributes for {entity['name']} before building.")

    for route in snapshot['routes']:
        if route['operation'] not in {'list', 'get', 'create', 'update', 'delete', 'sell'} or route['type'] not in {'authenticated', 'public'}:
            raise ValueError(f"Endpoint {route['path']} has no supported executable operation.")

    with TemporaryDirectory(prefix='api-builder-check-') as directory:
        for name, content in files.items():
            path = Path(directory) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

        if container:
            test_implementation_container(directory)
            return

        result = subprocess.run([sys.executable, '-c',
            "from app import create_app; app=create_app(database='test.db'); assert app.test_client().get('/health').json['status']=='ok'"],
            cwd=directory, capture_output=True, text=True, timeout=30)

        log_event('build.health_checked', returncode=result.returncode)

        if result.returncode:
            raise ValueError('Container application health check failed.')

        checks = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'],
                                cwd=directory, capture_output=True, text=True, timeout=30)

        log_event('build.runtime_tests_checked', returncode=checks.returncode)

        if checks.returncode:
            raise ValueError('Container CRUD and authentication tests failed.')


@log_function
def project_view(project: Project) -> dict:
    """Expose build readiness and repository destination without credentials."""
    g.project_id = project.id
    built = db.session.get(ProjectBuild, project.id)
    repository = db.session.get(ProjectRepository, project.id)

    return {**project.to_dict(), 'build_ready': bool(built and built.fingerprint == fingerprint(build_files(project))),
            'repository': {'owner': repository.owner, 'name': repository.name, 'url': repository.url} if repository else None}


@log_function
def run_current_project(project: Project) -> dict:
    """Replace the managed local API container with the selected tested build."""
    artifact = db.session.get(ProjectBuild, project.id)
    if artifact is None or artifact.fingerprint != fingerprint(build_files(project)):
        raise Conflict('Build this project before running its API.')

    directory = RUNNING_ROOT / f'project-{project.id}'
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)

    with ZipFile(BytesIO(artifact.archive)) as bundle:
        bundle.extractall(directory)

    subprocess.run(['docker', 'compose', '-p', 'api-builder-current', 'down', '--remove-orphans'],
                   cwd=directory, check=False, capture_output=True, text=True, timeout=60)
    try:
        subprocess.run(['docker', 'compose', '-p', 'api-builder-current', 'up', '--build', '-d'],
                       cwd=directory, check=True, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) and error.stderr else str(error)
        raise RuntimeError(f'Could not start the current API: {detail}') from error

    return {'message': 'Current API is running at http://127.0.0.1:8080.', 'project': project_view(project)}


@log_function
def run_project_check(project: Project, build: bool) -> dict:
    """Implement only for Build, validate the snapshot and persist its tested ZIP."""
    with LogStep('build.render', project_id=project.id):
        files = build_files(project)

    input_fingerprint = fingerprint(files)
    snapshot = json.loads(files['builder-configuration.json'])
    if build and snapshot['entities']:
        if any(not entity['attributes'] for entity in snapshot['entities']):
            raise ValueError('Generate and review entity attributes before building.')

        with LogStep('build.agent_implementation', project_id=project.id):
            implementation = run_agent_worker('api-implementation-builder', {
                'configuration': snapshot,
                'source': {name: files[name] for name in ['services/record_service.py', 'validation.py', 'models.py', 'routing.py', 'tests/test_api.py', 'app.py', 'services/telemetry_service.py', 'OBSERVABILITY.md']},
            }, current_app.config.get('IMPLEMENTATION_AGENT_TIMEOUT', 300))
            files['services/record_service.py'] = implementation['record_service']
            files['validation.py'] = implementation['validation']

    with LogStep('build.validate_and_test', project_id=project.id):
        test_files(files, container=bool(build and snapshot['entities']))

    db.session.expire_all()
    if input_fingerprint != fingerprint(build_files(project)):
        raise Conflict('Configuration changed during implementation. Build again from the latest saved configuration.')

    if build:
        archive = BytesIO()

        with LogStep('build.archive', project_id=project.id), ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
            for name, content in sorted(files.items()):
                bundle.writestr(name, content)

        row = db.session.get(ProjectBuild, project.id) or ProjectBuild(project_id=project.id)
        row.fingerprint = input_fingerprint
        row.filename = project_slug(project.name) + '.zip'
        row.archive = archive.getvalue()
        db.session.add(row)
        with LogStep('build.persist', project_id=project.id):
            db.session.commit()

    return {'project': project_view(project), 'message': 'Container API implemented and built. Configuration, CRUD and mock authentication checks passed.' if build else 'Configuration, health, CRUD and mock authentication checks passed.'}


@log_function
def ready_build(project: Project) -> ProjectBuild:
    """Require the tested artifact to match current project configuration and starter source."""
    row = db.session.get(ProjectBuild, project.id)

    if row is None or row.fingerprint != fingerprint(build_files(project)):
        raise Conflict('Build this project again before downloading or publishing.')

    return row


@log_function
def project_openapi(project: Project) -> dict:
    """Describe the executable starter endpoint without presenting draft routes as deployed."""
    g.project_id = project.id
    paths = {'/health': {'get': {'summary': 'Health check', 'responses': {'200': {'description': 'Healthy'}}}},
             '/auth/token': {'post': {'summary': 'Issue localhost mock token', 'responses': {'200': {'description': 'Local bearer token'}}}}}

    for route in read_endpoints()['routes']:
        operation = {'summary': f"{route['operation'] or 'Unimplemented'} {route['entity']}",
                     'security': [{'bearerAuth': []}] if route['access'] == 'authenticated' else [],
                     'responses': {'200': {'description': 'Success'}, '400': {'description': 'Invalid input'},
                                   '401': {'description': 'Token required'}, '404': {'description': 'Record not found'},
                                   '409': {'description': 'Conflict or insufficient stock'}}}

        if route['operation'] in {'get', 'update', 'delete', 'sell'}:
            operation['parameters'] = [{'name': 'id', 'in': 'path' if '{id}' in route['path'] else 'query',
                                        'required': True, 'schema': {'type': 'string'}}]

        if route['method'] in {'POST', 'PATCH'}:
            operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': {'type': 'object'}}}}

        paths.setdefault(route['path'], {})[(route['method'] or 'POST').lower()] = operation

    return {'openapi': '3.0.3', 'info': {'title': project.name, 'version': '1.0.0',
            'description': project.summary + '\nLocal container API. Use local mock tokens for authenticated endpoints.'},
            'servers': [{'url': 'http://127.0.0.1:8080'}], 'paths': paths,
            'components': {'securitySchemes': {'bearerAuth': {'type': 'http', 'scheme': 'bearer'}}}}


@log_function
def test_implementation_container(directory: str) -> None:
    """Execute agent-written source only inside an isolated disposable container."""
    identifier = uuid4().hex
    image = 'api-builder-check:' + identifier
    container = 'api-builder-check-' + identifier
    try:
        built = subprocess.run(['docker', 'build', '-t', image, directory], capture_output=True, text=True, timeout=180)
        log_event('build.container_image_checked', returncode=built.returncode)
        if built.returncode:
            raise ValueError('Generated API container build failed. Check Docker and the generated source.')

        checks = subprocess.run(['docker', 'run', '--rm', '--name', container, '--network', 'none',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--cpus', '2', '--memory', '512m',
            '--tmpfs', '/tmp:rw,size=128m', '--tmpfs', '/app/logs:rw,uid=10001,gid=10001,size=32m',
            image, 'python', '-m', 'unittest', 'discover', '-s', 'tests'], capture_output=True, text=True, timeout=60)
        log_event('build.runtime_tests_checked', returncode=checks.returncode)
        if checks.returncode:
            raise ValueError('Agent implementation failed container CRUD/authentication tests. Previous build is unchanged.')
    finally:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=15, check=False)
        subprocess.run(['docker', 'image', 'rm', '-f', image], capture_output=True, timeout=15, check=False)

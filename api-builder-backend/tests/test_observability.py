"""Verify isolation, trace semantics, privacy and generated artifact integration."""

import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult

from app import create_app
from shared import telemetry_service
from shared.telemetry_service import DEFAULT_CONFIGURATION


class RecordingExporter:
    """Capture completed SDK spans without a network collector."""

    def __init__(self) -> None:
        """Initialize independent captured spans."""
        self.spans = []

    def export(self, spans) -> SpanExportResult:
        """Record a batch and acknowledge it."""
        self.spans.extend(spans)

        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        """Keep recorded spans available after provider cleanup."""


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """Provide an isolated real Flask app with an observable exporter."""
    exporter = RecordingExporter()
    monkeypatch.setattr(telemetry_service, 'create_exporter', lambda config: exporter)
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'tracing.db'}"})
    client = app.test_client()
    project = client.get('/api/projects').json['projects'][0]
    client.environ_base['HTTP_X_PROJECT_ID'] = str(project['id'])
    yield app, client, exporter
    app.extensions['tracing'].shutdown()


def save(client, revision: int = 0, **changes):
    """Write a valid policy with targeted overrides."""
    return client.put('/api/observability', json={'revision': revision,
        'configuration': {**DEFAULT_CONFIGURATION, 'enabled': True, **changes}})


def test_policy_isolation_conflicts_and_disable(configured) -> None:
    """Apply settings to subsequent requests and keep other users/projects separate."""
    app, client, exporter = configured
    assert client.get('/api/observability').json['revision'] == 0
    assert save(client).status_code == 200
    assert save(client).status_code == 409
    other = client.post('/api/projects', json={'name': 'Other', 'summary': 'Isolated'}).json['project']
    assert client.get('/api/observability', headers={'X-Project-ID': str(other['id'])}).json['revision'] == 0
    stranger = app.test_client()
    assert stranger.get('/api/observability', headers={'X-Project-ID': client.environ_base['HTTP_X_PROJECT_ID']}).status_code == 400
    assert client.post('/api/observability/test', json={'revision': 2}).status_code == 409
    assert save(client, 1, enabled=False).status_code == 200
    assert 'X-Trace-ID' not in client.get('/api/entities').headers
    assert client.post('/api/observability/test', json={'revision': 2}).status_code == 400


@pytest.mark.parametrize('change', [
    {'endpoint': 'http://example.com:4318/v1/traces'}, {'endpoint': 'http://localhost:0/v1/traces'},
    {'endpoint': 'http://localhost:65536/v1/traces'}, {'endpoint': 'http://localhost:4318/v1/traces?secret=x'},
    {'endpoint': 'http://user:secret@localhost:4318/v1/traces'}, {'sample_ratio': 2},
    {'sample_ratio': True}, {'sample_ratio': float('nan')}, {'sample_ratio': float('inf')}, {'service_name': 'bad name'}, {'enabled': 'true'}, {'environment': ''},
])
def test_invalid_configuration(configured, change) -> None:
    """Reject unsafe destinations and invalid resource/sampling values before saving."""
    _, client, _ = configured
    assert save(client, **change).status_code == 400
    assert client.get('/api/observability').json['revision'] == 0


def test_parent_status_and_private_values(configured) -> None:
    """Preserve W3C parentage, safe route templates, duration and correlation headers."""
    app, client, exporter = configured
    save(client)
    parent_trace = '0123456789abcdef0123456789abcdef'
    response = client.get('/api/entities?secret=do-not-record', headers={
        'traceparent': f'00-{parent_trace}-0123456789abcdef-01', 'Authorization': 'Bearer do-not-record'})
    assert response.headers['X-Trace-ID'] == parent_trace
    assert app.extensions['tracing'].flush()
    span = next(span for span in exporter.spans if span.name == 'GET /api/entities')
    assert span.parent.span_id == int('0123456789abcdef', 16)
    assert span.attributes['http.response.status_code'] == 200
    assert span.end_time >= span.start_time
    assert 'do-not-record' not in str(span.attributes)
    assert dict(span.attributes) == {'http.request.method': 'GET', 'http.route': '/api/entities', 'http.response.status_code': 200}


def test_sampling_and_probe_reports_export_failure(configured, monkeypatch) -> None:
    """A zero root ratio suppresses spans while diagnostic probes still verify export."""
    app, client, exporter = configured
    save(client, sample_ratio=0)
    client.get('/api/entities')
    app.extensions['tracing'].flush()
    assert exporter.spans == []
    probe = client.post('/api/observability/test', json={'revision': 1})
    assert probe.status_code == 200
    assert len(probe.json['trace_id']) == 32
    assert exporter.spans[-1].name == 'observability.test'
    monkeypatch.setattr(exporter, 'export', lambda spans: SpanExportResult.FAILURE)
    assert client.post('/api/observability/test', json={'revision': 1}).status_code == 502
    assert client.get('/api/entities').status_code == 200


def test_generated_snapshot_and_stale_build(configured) -> None:
    """Package runtime, settings and local collector, and invalidate changed builds."""
    _, client, _ = configured
    save(client, enabled=False)
    project = client.environ_base['HTTP_X_PROJECT_ID']
    assert client.post(f'/api/projects/{project}/build').status_code == 200
    response = client.get(f'/api/projects/{project}/download')

    with ZipFile(BytesIO(response.data)) as bundle:
        config = json.loads(bundle.read('builder-configuration.json'))
        assert config['observability']['enabled'] is False
        assert b'OTLPSpanExporter' in bundle.read('services/telemetry_service.py')
        assert b'http://jaeger:4318/v1/traces' in bundle.read('compose.yaml')
        assert 'OBSERVABILITY.md' in bundle.namelist()
        assert b'opentelemetry-sdk==' in bundle.read('requirements.txt')

    save(client, 1, service_name='changed', enabled=False)
    assert client.get(f'/api/projects/{project}/download').status_code == 409


def test_health_and_error_status(configured) -> None:
    """Honor health exclusion and include project build actions after ownership checks."""
    app, client, exporter = configured
    save(client)
    assert 'X-Trace-ID' not in client.get('/api/health').headers
    save(client, 1, exclude_health=False)
    assert 'X-Trace-ID' in client.get('/api/health').headers
    app.extensions['tracing'].flush()
    assert any(span.name == 'GET /api/health' for span in exporter.spans)


def test_build_actions_are_traced(configured) -> None:
    """Trace project actions even though their project is resolved from the route."""
    app, client, exporter = configured
    save(client)
    project = client.environ_base['HTTP_X_PROJECT_ID']
    response = client.get(f'/api/projects/{project}/openapi')
    assert response.status_code == 200
    assert 'X-Trace-ID' in response.headers
    app.extensions['tracing'].flush()
    assert any(span.name == 'GET /api/projects/<int:project_id>/<operation>' for span in exporter.spans)

"""Export payload-free HTTP spans using app-owned providers and W3C trace context."""

import atexit
from collections import OrderedDict
import json
from threading import RLock

from flask import g, request
from opentelemetry import context, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
import requests

DEFAULT_CONFIGURATION = {
    'enabled': False, 'service_name': 'api-builder', 'service_namespace': 'local',
    'environment': 'development', 'endpoint': 'http://127.0.0.1:4318/v1/traces',
    'sample_ratio': 1.0, 'exclude_health': True,
}


def create_provider(configuration: dict) -> TracerProvider:
    """Use explicit resources and parent-based sampling without global SDK mutation."""
    return TracerProvider(resource=Resource({
        'service.name': configuration['service_name'],
        'service.namespace': configuration['service_namespace'],
        'deployment.environment.name': configuration['environment'],
    }), sampler=ParentBased(TraceIdRatioBased(configuration['sample_ratio'])))


class LocalExportSession(requests.Session):
    """Prevent environment-provided OTLP credentials from reaching the local receiver."""

    def request(self, method: str, url: str, **kwargs):
        """Allow protocol headers only; the SDK owns compression and request encoding."""
        headers = kwargs.get('headers') or {}
        kwargs['headers'] = {key: value for key, value in headers.items()
                             if key.lower() in {'content-type', 'content-encoding', 'user-agent'}}

        return super().request(method, url, **kwargs)


def create_exporter(configuration: dict) -> OTLPSpanExporter:
    """Send only to the configured destination without inherited proxy credentials."""
    session = LocalExportSession()
    session.trust_env = False

    return OTLPSpanExporter(endpoint=configuration['endpoint'], timeout=3, session=session, headers={})


class TraceRuntime:
    """Bound cached providers and keep in-flight spans alive through configuration changes."""

    def __init__(self) -> None:
        """Own lifecycle independently for each Flask application."""
        self.providers = OrderedDict()
        self.lock = RLock()
        atexit.register(self.shutdown)

    def acquire(self, configuration: dict) -> tuple:
        """Reuse immutable settings and evict only idle providers."""
        key = json.dumps(configuration, sort_keys=True)

        with self.lock:
            if key not in self.providers:
                for old_key, entry in list(self.providers.items()):
                    if len(self.providers) < 32:
                        break

                    if entry['active'] == 0:
                        self.providers.pop(old_key)['provider'].shutdown()

                provider = create_provider(configuration)
                provider.add_span_processor(BatchSpanProcessor(create_exporter(configuration), schedule_delay_millis=500))
                self.providers[key] = {'provider': provider, 'active': 0}

            entry = self.providers[key]
            entry['active'] += 1
            self.providers.move_to_end(key)

            return key, entry['provider'].get_tracer('api-builder.http')

    def release(self, key: str) -> None:
        """Mark the provider idle once its request span ends."""
        with self.lock:
            self.providers[key]['active'] -= 1

    def flush(self) -> bool:
        """Drain queued spans for integration checks and graceful stopping."""
        with self.lock:
            return all(entry['provider'].force_flush(5000) for entry in self.providers.values())

    def shutdown(self) -> None:
        """Close exporters on process exit without installing a global tracer provider."""
        with self.lock:
            for entry in self.providers.values():
                entry['provider'].shutdown()

            self.providers.clear()


def install_tracing(app) -> None:
    """Register completion hooks; the caller starts spans after resolving configuration."""
    app.extensions['tracing'] = TraceRuntime()
    app.after_request(finish_request_trace)
    app.teardown_request(clear_request_trace)


def start_request_trace(runtime: TraceRuntime, configuration: dict) -> None:
    """Trace route templates only, never raw paths, headers, bodies or query strings."""
    if not configuration['enabled'] or (configuration['exclude_health'] and request.path in {'/health', '/api/health'}):
        return

    key, tracer = runtime.acquire(configuration)
    route = request.url_rule.rule if request.url_rule else '<unmatched>'
    span = tracer.start_span(f'{request.method} {route}',
        context=TraceContextTextMapPropagator().extract(request.headers), kind=trace.SpanKind.SERVER,
        attributes={'http.request.method': request.method, 'http.route': route})
    token = context.attach(trace.set_span_in_context(span))
    g.otel_request = (runtime, key, span, token)


def finish_request_trace(response):
    """Record HTTP status and expose the correlation ID while leaving context for logging."""
    if hasattr(g, 'otel_request'):
        span = g.otel_request[2]
        span.set_attribute('http.response.status_code', response.status_code)

        if response.status_code >= 500:
            span.set_status(trace.StatusCode.ERROR)

        response.headers['X-Trace-ID'] = format(span.get_span_context().trace_id, '032x')

    return response


def clear_request_trace(error) -> None:
    """End and detach once, including unhandled errors, without leaking exception text."""
    if not hasattr(g, 'otel_request'):
        return

    runtime, key, span, token = g.pop('otel_request')

    if error is not None:
        span.set_status(trace.StatusCode.ERROR)
        span.set_attribute('error.type', type(error).__name__)

    span.end()
    context.detach(token)
    runtime.release(key)


def send_test_trace(configuration: dict) -> dict:
    """Export one always-sampled probe and report actual OTLP acceptance, not flush success."""
    provider = create_provider({**configuration, 'sample_ratio': 1})
    span = provider.get_tracer('api-builder.diagnostics').start_span('observability.test', context=context.Context())
    span.end()
    exporter = create_exporter(configuration)

    try:
        result = exporter.export([span])
    except requests.RequestException as error:
        raise ConnectionError('Local collector could not accept the test trace.') from error
    finally:
        exporter.shutdown()
        provider.shutdown()

    if result != SpanExportResult.SUCCESS:
        raise ConnectionError('Local collector could not accept the test trace.')

    return {'trace_id': format(span.get_span_context().trace_id, '032x'),
            'message': 'Collector accepted the test trace. Open Jaeger to inspect it.'}

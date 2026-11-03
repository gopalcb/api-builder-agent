"""Write correlated, payload-free application and agent logs to one daily run file."""

from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import logging
import os
from pathlib import Path
import re
from threading import RLock
from time import perf_counter
import traceback
from uuid import uuid4

from flask import g, request
from opentelemetry.trace import get_current_span

DEFAULT_LOG_DIRECTORY = Path(__file__).resolve().parents[2] / 'logs'
LOG_CONTEXT = ContextVar('application_log_context', default={})
LOG_LOCK = RLock()
LOGGER = logging.getLogger('api_builder.flow')
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
LOG_PATH = None
ALLOWED_FIELDS = {'method', 'route', 'status', 'project_id', 'entity_id', 'agent', 'step', 'count',
                  'returncode', 'timeout_seconds', 'duration_ms', 'error_type', 'stack', 'component'}


def configure_logging(directory: Path = DEFAULT_LOG_DIRECTORY, inherited_file: str | None = None) -> Path:
    """Reserve the next daily run atomically, or join a trusted parent process run."""
    global LOG_PATH
    directory = Path(directory).resolve()

    with LOG_LOCK:
        if LOG_PATH is not None:
            return LOG_PATH

        directory.mkdir(parents=True, exist_ok=True)

        if inherited_file:
            path = Path(inherited_file).resolve()

            if path.parent != directory or not re.fullmatch(r'log-\d{4}-\d{2}-\d{2}-[1-9]\d*', path.name) or not path.is_file():
                raise ValueError('Invalid inherited application log file.')
        else:
            prefix = datetime.now().strftime('log-%Y-%m-%d-')
            indexes = [int(path.name[len(prefix):]) for path in directory.glob(prefix + '*')
                       if path.name[len(prefix):].isdigit()]
            index = max(indexes, default=0) + 1

            while True:
                path = directory / f'{prefix}{index}'

                try:
                    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    index += 1
                    continue

                os.close(descriptor)
                break

        handler = logging.FileHandler(path, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        LOGGER.addHandler(handler)
        LOG_PATH = path
        log_event('logging.started', component='application')

        return path


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """Write only selected operational metadata; never serialize inputs or exception messages."""
    if LOG_PATH is None:
        configure_logging()

    record = {'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
              'level': logging.getLevelName(level), 'run': LOG_PATH.name, 'pid': os.getpid(),
              **LOG_CONTEXT.get(), 'event': event}
    span = get_current_span().get_span_context()

    if span.is_valid:
        record.update(trace_id=format(span.trace_id, '032x'), span_id=format(span.span_id, '016x'))

    record.update({key: value for key, value in fields.items() if key in ALLOWED_FIELDS})
    LOGGER.log(level, json.dumps(record, ensure_ascii=True, separators=(',', ':')))


class LogStep:
    """Log entry, completion or failure while preserving the original exception behavior."""

    def __init__(self, name: str, **fields) -> None:
        """Capture a static operation name and safe operational metadata."""
        self.name = name
        self.fields = fields

    def __enter__(self):
        """Create a nested span retaining the request or parent agent trace."""
        parent = LOG_CONTEXT.get()
        self.token = LOG_CONTEXT.set({**parent, 'trace_id': parent.get('trace_id') or uuid4().hex,
                                      'parent_span_id': parent.get('span_id'), 'span_id': uuid4().hex,
                                      'function': self.name})
        self.started = perf_counter()
        log_event('function.started', **self.fields)

        return self

    def __exit__(self, error_type, error, trace) -> bool:
        """Record safe stack locations without locals/messages, then restore parent context."""
        fields = {**self.fields, 'duration_ms': round((perf_counter() - self.started) * 1000, 3)}

        if error_type:
            fields.update(error_type=error_type.__name__, stack=[
                {'file': Path(frame.filename).name, 'function': frame.name, 'line': frame.lineno}
                for frame in traceback.extract_tb(trace)])
            log_event('function.failed', logging.ERROR, **fields)
        else:
            log_event('function.completed', **fields)

        LOG_CONTEXT.reset(self.token)

        return False


def log_function(function):
    """Trace a synchronous function without recording its arguments or return value."""
    @wraps(function)
    def logged(*args, **kwargs):
        """Preserve the wrapped function contract and propagate every failure."""
        with LogStep(f'{function.__module__}.{function.__qualname__}'):
            return function(*args, **kwargs)

    return logged


def worker_environment() -> dict:
    """Pass file and trace metadata explicitly, without mutating the server environment."""
    path = configure_logging()

    return {**os.environ, 'API_BUILDER_LOG_FILE': str(path),
            'API_BUILDER_LOG_CONTEXT': json.dumps(LOG_CONTEXT.get())}


def configure_worker() -> None:
    """Join the parent file and trace, or allocate a standalone agent run."""
    configure_logging(inherited_file=os.environ.get('API_BUILDER_LOG_FILE'))
    inherited = json.loads(os.environ.get('API_BUILDER_LOG_CONTEXT', '{}'))
    LOG_CONTEXT.set({key: inherited[key] for key in ('trace_id', 'span_id', 'parent_span_id', 'generation_id', 'entity_id', 'project_id') if key in inherited})


def install_request_logging(app) -> None:
    """Install HTTP lifecycle hooks before authentication and project resolution."""
    app.before_request(start_request_log)
    app.after_request(finish_request_log)
    app.teardown_request(clear_request_log)


def start_request_log() -> None:
    """Assign a server-owned trace and avoid raw URLs, headers or request payloads."""
    g.log_token = LOG_CONTEXT.set({'trace_id': uuid4().hex, 'span_id': uuid4().hex})
    g.log_started = perf_counter()
    log_event('request.started', method=request.method, route=request.url_rule.rule if request.url_rule else '<unmatched>')


def finish_request_log(response):
    """Record final status and duration, including handled validation/auth failures."""
    if hasattr(g, 'log_started'):
        log_event('request.completed', logging.ERROR if response.status_code >= 400 else logging.INFO,
                  method=request.method, route=request.url_rule.rule if request.url_rule else '<unmatched>',
                  status=response.status_code, project_id=getattr(g, 'project_id', None),
                  duration_ms=round((perf_counter() - g.log_started) * 1000, 3))
        response.headers['X-Request-ID'] = LOG_CONTEXT.get()['trace_id']

    return response


def clear_request_log(error) -> None:
    """Prevent request/thread context leaks, including unhandled server failures."""
    if error is not None:
        log_event('request.failed', logging.ERROR, error_type=type(error).__name__)

    if hasattr(g, 'log_token'):
        LOG_CONTEXT.reset(g.log_token)
        del g.log_token

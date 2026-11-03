"""Create the local container API from the builder's saved configuration."""

import json
import os
from pathlib import Path

from flask import Flask, jsonify, current_app
from werkzeug.exceptions import HTTPException

from services.logger_service import configure_logging, install_request_logging, log_event, log_function
from services.telemetry_service import DEFAULT_CONFIGURATION, install_tracing, start_request_trace
from models import initialize_database
from routing import register_routes


@log_function
def create_app(configuration: dict | None = None, database: str | None = None) -> Flask:
    """Bind explicit local mock authentication, storage and configured endpoints."""
    configure_logging()
    log_event('application.starting', component='generated-api')
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=65536, DATABASE=database or os.environ.get('DATABASE_PATH', '/data/api.db'),
                      MOCK_AUTH=os.environ.get('LOCAL_MOCK_AUTH') == '1', SECRET_KEY=os.urandom(32))
    configuration = configuration or json.loads(Path('builder-configuration.json').read_text())
    tracing = {**DEFAULT_CONFIGURATION, **configuration.get('observability', {})}
    tracing['service_name'] += '-api'
    tracing['endpoint'] = os.environ.get('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', tracing['endpoint'])
    app.config['TRACING'] = tracing
    install_request_logging(app)
    install_tracing(app)
    app.before_request(trace_request)
    initialize_database(app.config['DATABASE'])
    register_routes(app, configuration)
    app.register_error_handler(HTTPException, handle_http_error)

    log_event('application.ready', component='generated-api')

    return app


@log_function
def handle_http_error(error: HTTPException) -> tuple:
    """Expose safe JSON validation and request errors."""
    return jsonify(error=error.description), error.code


def trace_request() -> None:
    """Start generated API spans from the saved policy and container endpoint override."""
    start_request_trace(current_app.extensions['tracing'], current_app.config['TRACING'])

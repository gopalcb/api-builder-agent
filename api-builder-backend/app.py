"""Build and run the local Flask entity API; persistence is owned by models/services."""

import os
import sys
from pathlib import Path

from flask import Flask, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.logger_service import configure_logging, install_request_logging, log_event, log_function
from models import db
from services.project_service import initialize_projects
from services.local_connection_service import check_local_connection, add_local_connection_headers
from routing import api
from shared.telemetry_service import install_tracing


@log_function
def create_app(config: dict | None = None) -> Flask:
    """Configure an isolated app and initialize its metadata tables."""
    configure_logging()
    log_event('application.starting', component='builder-backend')
    app = Flask(__name__, instance_path=str(Path(__file__).resolve().parent.parent / "instance"))
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///entities.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=65536,
        SEARCH_AGENT_TIMEOUT=int(os.environ.get("SEARCH_AGENT_TIMEOUT", "180")),
        RBAC_AGENT_TIMEOUT=int(os.environ.get("RBAC_AGENT_TIMEOUT", "120")),
        ENTITY_AGENT_TIMEOUT=int(os.environ.get("ENTITY_AGENT_TIMEOUT", "120")),
        INFRASTRUCTURE_AGENT_TIMEOUT=int(os.environ.get("INFRASTRUCTURE_AGENT_TIMEOUT", "180")),
    )

    if config:
        app.config.update(config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    install_request_logging(app)
    install_tracing(app)
    db.init_app(app)
    app.before_request(check_local_connection)
    app.after_request(add_local_connection_headers)
    app.register_blueprint(api)
    app.register_blueprint(api, url_prefix="/api", name="proxied_api")
    app.register_error_handler(HTTPException, handle_http_error)
    app.register_error_handler(SQLAlchemyError, handle_database_error)

    with app.app_context():
        db.create_all()
        initialize_projects()

    log_event('application.ready', component='builder-backend')

    return app


@log_function
def handle_http_error(error: HTTPException) -> tuple:
    """Keep malformed JSON, missing routes and other HTTP errors in JSON format."""
    return jsonify(error=error.description), error.code


@log_function
def handle_database_error(error: SQLAlchemyError) -> tuple:
    """Roll back failed transactions without exposing database details to callers."""
    db.session.rollback()

    return jsonify(error="Database operation failed"), 500


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))

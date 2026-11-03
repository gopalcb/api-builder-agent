"""HTTP routes for creating entities and generating their schemas through Codex."""

import subprocess
from io import BytesIO
from urllib.error import HTTPError, URLError

from services.project_build_service import project_view, run_project_check, ready_build, project_openapi, run_current_project
from services.github_service import push_project

from jsonschema import ValidationError, validate

from flask import g, Response, Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models import Entity, Project, ProjectArchive, ProjectEntityName, db
from services.document_service import read_documents, save_document
from services.configuration_service import add_entity_endpoints, read_definition, generate_definition, save_attributes, read_endpoints, save_endpoints, delete_entity_configuration, rename_entity_endpoints
from services.project_service import require_project
from services.user_service import bind_user, save_user_cookie
from services.entity_service import GenerationError, generate_entity_attributes
from validation import SEARCH_REQUEST_SCHEMA, validate_payload, validate_rbac_request, validate_project_payload, validate_entity_name
from services.rbac_service import (
    RbacError, read_configuration, save_configuration, generate_configuration,
    preview_access, export_configuration,
)
from runtime.worker import run_agent_worker
from services.caching_service import CachingError, read_caching, save_caching, export_caching
from validation import validate_caching_request, INFRASTRUCTURE_REQUEST_SCHEMA

from services.observability_service import read_observability, save_observability
from shared.telemetry_service import start_request_trace, send_test_trace
from validation import validate_observability_request
from werkzeug.exceptions import Conflict

from services.logger_service import log_function

api = Blueprint("entities", __name__)
api.after_request(save_user_cookie)


@api.get("/health")
@log_function
def health() -> tuple:
    """Identify a ready builder backend without creating an anonymous workspace."""
    db.session.execute(select(1))
    response = jsonify(service="api-builder", status="ok")
    response.headers["Cache-Control"] = "no-store"

    return response, 200


@api.before_request
@log_function
def bind_project_context() -> None:
    """Require project context for every configuration endpoint used by the UI."""
    endpoint = (request.endpoint or "").rsplit(".", 1)[-1]
    if endpoint == 'health' and request.headers.get('X-Project-ID'):
        bind_user()
        require_project()

    if endpoint in {"projects", "project_details", "project_action", "project_build_logs", "entity_names", "entity_name_details", "rbac", "generate_search_configuration", "generate_infrastructure_plan", "caching", "project_documents", "entity_configuration", "entity_generation_logs", "endpoint_configuration", "load_testing", "observability", "observability_test"}:
        bind_user()

    if endpoint in {"entity_names", "entity_name_details", "rbac", "generate_search_configuration", "generate_infrastructure_plan", "caching", "project_documents", "entity_configuration", "entity_generation_logs", "endpoint_configuration", "load_testing", "observability", "observability_test"}:
        require_project()


@api.before_request
def trace_project_request() -> None:
    """Begin tracing only after the existing ownership boundary resolves the project."""
    if hasattr(g, 'project_id'):
        start_request_trace(current_app.extensions['tracing'], read_observability()['configuration'])


@api.route('/observability', methods=['GET', 'PUT'])
def observability() -> tuple:
    """Read or update the selected project's validated tracing configuration."""
    if request.method == 'GET':
        return jsonify(read_observability()), 200

    try:
        payload = validate_observability_request(request.get_json())
        result = save_observability(payload)
    except (ValidationError, ValueError):
        return jsonify(error='Use local HTTP /v1/traces, port 1–65535, valid resource names and sampling 0–1.'), 400

    return jsonify(result), 200


@api.post('/observability/test')
def observability_test() -> tuple:
    """Send a real probe using the saved revision without mutating configuration."""
    try:
        payload = request.get_json()
        validate(payload, {'type': 'object', 'additionalProperties': False, 'required': ['revision'],
                          'properties': {'revision': {'type': 'integer', 'minimum': 1}}})
        saved = read_observability()

        if payload['revision'] != saved['revision']:
            raise Conflict('Configuration changed. Reload before testing.')

        if not saved['configuration']['enabled']:
            return jsonify(error='Enable and save tracing before sending a test trace.'), 400

        return jsonify(send_test_trace(saved['configuration'])), 200
    except ValidationError:
        return jsonify(error='Save configuration before testing.'), 400
    except ConnectionError:
        return jsonify(error='Collector unavailable or rejected the trace. Start Jaeger and check the saved endpoint.'), 502


@api.route("/projects", methods=["GET", "POST"])
@log_function
def projects() -> tuple:
    """List workspace projects or persist a new name and summary."""
    if request.method == "GET":
        rows = list(db.session.scalars(select(Project).where(Project.user_id == g.user_id, ~Project.id.in_(select(ProjectArchive.project_id))).order_by(Project.id)))
        return jsonify(projects=[project_view(row) for row in rows], default_project_id=rows[0].id if rows else None), 200
    try:
        project = Project(user_id=g.user_id, **validate_project_payload(request.get_json()))
        db.session.add(project)
        db.session.commit()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="A project with this name already exists."), 409
    return jsonify(project=project_view(project)), 201


@api.post("/create-entity")
@log_function
def create_entity() -> tuple:
    """Persist an entity from a JSON object."""
    try:
        payload = validate_payload(request.get_json())
    except ValueError as error:
        return jsonify(error=str(error)), 400

    entity = Entity(**payload)
    db.session.add(entity)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(error="An entity with that name already exists"), 409

    return jsonify(entity=entity.to_dict()), 201


@api.post("/generate-entity-attributes")
@log_function
def generate_attributes() -> tuple:
    """Generate and atomically save attributes and outgoing relationships."""
    try:
        payload = validate_payload(request.get_json())
    except ValueError as error:
        return jsonify(error=str(error)), 400

    try:
        entity = generate_entity_attributes(payload, current_app.config["ENTITY_AGENT_TIMEOUT"])
    except GenerationError as error:
        db.session.rollback()

        return jsonify(error=str(error)), error.status

    return jsonify(entity=entity), 200


@api.get("/entities/<int:entity_id>")
@log_function
def get_entity(entity_id: int) -> tuple:
    """Read a stored definition for clients and persistence verification."""
    entity = db.session.get(Entity, entity_id)

    if entity is None:
        return jsonify(error="Entity not found"), 404

    return jsonify(entity=entity.to_dict()), 200


@api.route("/entities", methods=["GET", "POST"])
@log_function
def entity_names() -> tuple:
    """List or save screen entity names without storing definition drafts."""
    if request.method == "GET":
        entities = db.session.scalars(select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id).order_by(ProjectEntityName.id))

        return jsonify(entities=[{"id": entity.id, "name": entity.name} for entity in entities]), 200

    try:
        name = validate_entity_name(request.get_json())
        existing = db.session.scalars(select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id))

        if any(row.name.strip().casefold() == name.casefold() for row in existing):
            return jsonify(error="An entity with this name already exists."), 409

        entity = ProjectEntityName(project_id=g.project_id, name=name)
        db.session.add(entity)
        db.session.flush()
        add_entity_endpoints(entity)
        db.session.commit()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except IntegrityError:
        db.session.rollback()

        return jsonify(error="An entity with this name already exists."), 409

    return jsonify(entity={"id": entity.id, "name": entity.name}), 201


@api.post("/generate-search-configuration")
@log_function
def generate_search_configuration() -> tuple:
    """Return a reviewed proposal without provisioning or executing a route."""
    try:
        payload = request.get_json()
        validate(payload, SEARCH_REQUEST_SCHEMA)
        context = {
            **payload,
            "entities": [entity.name for entity in db.session.scalars(select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id))],
        }
        db.session.rollback()
        configuration = run_agent_worker("search-builder", context, current_app.config["SEARCH_AGENT_TIMEOUT"])
    except ValidationError:
        return jsonify(error="Choose a supported type, a /route/path and a prompt of 1–4000 characters."), 400
    except subprocess.TimeoutExpired:
        return jsonify(error="Generation timed out. Your draft is unchanged; retry."), 504
    except (OSError, RuntimeError, ValueError):
        return jsonify(error="Generation failed. Check local Codex sign-in and runtime, then retry."), 502

    return jsonify(configuration=configuration), 200


@api.post("/generate-infrastructure-plan")
@log_function
def generate_infrastructure_plan() -> tuple:
    """Build a reviewed proposal from owned project inputs without creating AWS resources."""
    try:
        payload = request.get_json()
        validate(payload, INFRASTRUCTURE_REQUEST_SCHEMA)
        context = {
            **payload,
            "entities": [{"id": entity.id, "name": entity.name} for entity in db.session.scalars(
                select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id)
                .order_by(ProjectEntityName.id)
            )],
            "caching": read_caching()["configuration"],
        }
        db.session.rollback()
        proposal = run_agent_worker("infrastructure-builder", context, current_app.config["INFRASTRUCTURE_AGENT_TIMEOUT"])
    except ValidationError:
        return jsonify(error="Choose AWS, serverless, dev/staging/prod and requirements up to 4000 characters."), 400
    except subprocess.TimeoutExpired:
        return jsonify(error="Generation timed out. Your previous proposal is unchanged; retry."), 504
    except (OSError, RuntimeError, ValueError):
        return jsonify(error="Generation failed. Check local Codex sign-in and runtime, then retry."), 502

    return jsonify(proposal=proposal), 200


@api.route("/rbac", methods=["GET", "PUT"])
@api.post("/rbac/<operation>")
@log_function
def rbac(operation: str = "configuration") -> Response | tuple:
    """Handle RBAC configuration, proposal, preview and export requests."""
    if request.method == "GET":
        return jsonify(read_configuration())

    if operation not in ("configuration", "generate", "preview", "export"):
        return jsonify(error="Unknown RBAC operation"), 404

    try:
        payload = validate_rbac_request(request.get_json(), operation)

        if operation == "configuration":
            return jsonify(save_configuration(payload["configuration"], payload["revision"]))

        if operation == "generate":
            return jsonify(generate_configuration(
                payload["configuration"], payload["prompt"], payload["revision"], current_app.config["RBAC_AGENT_TIMEOUT"],
            ))

        if operation == "preview":
            return jsonify(preview_access(payload["configuration"], payload["roles"], payload["route"]))

        return send_file(export_configuration(payload["revision"]), mimetype="application/zip", as_attachment=True,
                         download_name=f"rbac-revision-{payload['revision']}.zip")
    except ValidationError as error:
        return jsonify(error=f"Invalid RBAC request at {'/'.join(map(str, error.absolute_path)) or 'request'}: check required fields and allowed values."), 400
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except RbacError as error:
        db.session.rollback()

        return jsonify(error=str(error)), error.status


@api.route("/caching", methods=["GET", "PUT"])
@api.post("/caching/export")
@log_function
def caching() -> Response | tuple:
    """Read, persist or export a project-scoped cache configuration."""
    if request.method == "GET":
        return jsonify(read_caching())

    try:
        exporting = request.method == "POST"
        payload = validate_caching_request(request.get_json(), exporting)

        if exporting:
            return send_file(export_caching(payload["revision"]), mimetype="application/zip",
                             as_attachment=True, download_name=f"caching-{payload['revision']}.zip")

        return jsonify(save_caching(payload["configuration"], payload["revision"]))
    except ValidationError:
        return jsonify(error="Use a public GET route, TTL 1–3600 seconds and valid query parameter names."), 400
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except CachingError as error:
        db.session.rollback()

        return jsonify(error=str(error)), error.status


@api.get("/project-documents")
@api.route("/project-documents/<slug>", methods=["GET", "PUT"])
@log_function
def project_documents(slug: str | None = None) -> tuple:
    """List, read or edit generated Markdown for the active project."""
    if request.method == "PUT":
        return jsonify(document=save_document(slug, request.get_json())), 200
    documents = read_documents()
    if slug is None:
        return jsonify(documents=[{key: value for key, value in item.items() if key != "content"} for item in documents]), 200
    document = next((item for item in documents if item["id"] == slug), None)
    if document is None:
        return jsonify(error="Document not found."), 404
    return jsonify(document=document), 200


@api.route("/projects/<int:project_id>", methods=["PUT", "DELETE"])
@log_function
def project_details(project_id: int) -> tuple:
    """Update project details or remove a project from the catalog recoverably."""
    project = db.session.get(Project, project_id)

    if project is None or project.user_id != g.user_id or db.session.get(ProjectArchive, project_id):
        return jsonify(error="Project not found."), 404

    if request.method == "DELETE":
        db.session.add(ProjectArchive(project_id=project_id))
        db.session.commit()

        return jsonify(deleted=True), 200

    try:
        payload = validate_project_payload(request.get_json())
        project.name = payload["name"]
        project.summary = payload["summary"]
        db.session.commit()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except IntegrityError:
        db.session.rollback()

        return jsonify(error="A project with this name already exists."), 409

    return jsonify(project=project_view(project)), 200


@api.route("/projects/<int:project_id>/<operation>", methods=["GET", "POST"])
@log_function
def project_action(project_id: int, operation: str) -> Response | tuple:
    """Run scoped checks/build/download/publish operations with caller-safe errors."""
    project = db.session.get(Project, project_id)

    if project is None or project.user_id != g.user_id or db.session.get(ProjectArchive, project_id):
        return jsonify(error="Project not found."), 404

    g.project_id = project_id
    start_request_trace(current_app.extensions['tracing'], read_observability()['configuration'])

    if request.method == "GET" and operation == "openapi":
        return jsonify(project_openapi(project)), 200

    if request.method == "POST" and operation == "run":
        try:
            return jsonify(run_current_project(project)), 200
        except (Conflict, RuntimeError) as error:
            return jsonify(error=str(error)), 409 if isinstance(error, Conflict) else 503

    if request.method == "GET" and operation == "download":
        artifact = ready_build(project)

        return send_file(BytesIO(artifact.archive), mimetype="application/zip", as_attachment=True, download_name=artifact.filename)

    if request.method != "POST" or operation not in {"test", "build", "github"}:
        return jsonify(error="Unknown project action."), 404

    try:
        if operation == "github":
            return jsonify(repository=push_project(project, request.get_json())), 200

        if operation == "build":
            from services.generation_logs_service import generation_log_context

            payload = request.get_json(silent=True) or {}
            run_id = payload.get('run_id') if isinstance(payload, dict) else None
            if run_id is not None and not isinstance(run_id, str):
                raise ValueError('Invalid build run ID.')

            with generation_log_context(0, run_id, 'project.build'):
                return jsonify(run_project_check(project, True)), 200

        return jsonify(run_project_check(project, False)), 200
    except HTTPError as error:
        messages = {401: "GitHub authentication failed. Check your token.", 403: "GitHub denied access. Check repository permissions or rate limits.",
                    404: "GitHub repository or branch was not found. Check the account, repository and token access.",
                    409: "GitHub repository changed or is empty. Initialize it, then retry.",
                    422: "GitHub rejected the update. The repository may already exist; select an existing repository to retry."}

        return jsonify(error=messages.get(error.code, "GitHub did not confirm publication. Inspect the repository before retrying.")), 502
    except (URLError, TimeoutError):
        return jsonify(error="GitHub did not confirm publication. Check the repository before retrying; the repository or commit may already exist."), 502
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (SyntaxError, OSError, RuntimeError, subprocess.TimeoutExpired):
        return jsonify(error="Project checks failed. Check the container source and saved configuration."), 400


@api.get('/projects/<int:project_id>/build/logs/<run_id>')
@log_function
def project_build_logs(project_id: int, run_id: str) -> tuple:
    """Read safe build events only for a project owned by the current user."""
    from services.generation_logs_service import read_generation_logs

    project = db.session.get(Project, project_id)
    if project is None or project.user_id != g.user_id or db.session.get(ProjectArchive, project_id):
        return jsonify(error='Project not found.'), 404

    g.project_id = project_id
    try:
        result = read_generation_logs(0, run_id, int(request.args.get('cursor', '0')))
    except ValueError:
        return jsonify(error='Invalid build log request.'), 400

    return jsonify(result), 200


@api.route("/entities/<int:entity_id>", methods=["PUT", "DELETE"])
@log_function
def entity_name_details(entity_id: int) -> tuple:
    """Rename or delete one entity owned by the active project."""
    entity = db.session.scalar(select(ProjectEntityName).where(
        ProjectEntityName.id == entity_id, ProjectEntityName.project_id == g.project_id,
    ))

    if entity is None:
        return jsonify(error="Entity not found"), 404

    if request.method == "DELETE":
        delete_entity_configuration(entity)
        db.session.delete(entity)
        db.session.commit()
        return jsonify(deleted=True), 200

    try:
        name = validate_entity_name(request.get_json())
        siblings = db.session.scalars(select(ProjectEntityName).where(
            ProjectEntityName.project_id == g.project_id, ProjectEntityName.id != entity_id,
        ))

        if any(row.name.strip().casefold() == name.casefold() for row in siblings):
            return jsonify(error="An entity with this name already exists."), 409

        rename_entity_endpoints(entity, name)
        entity.name = name
        db.session.commit()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="An entity with this name already exists."), 409

    return jsonify(entity={"id": entity.id, "name": entity.name}), 200


@api.route("/entity-configurations/<int:entity_id>", methods=["GET", "POST", "PUT"])
@log_function
def entity_configuration(entity_id: int) -> tuple:
    """Read or generate a schema owned by the selected project."""
    try:
        if request.method == 'GET':
            result = read_definition(entity_id)
        elif request.method == 'PUT':
            result = save_attributes(entity_id, request.get_json())
        else:
            result = generate_definition(entity_id, request.get_json(), current_app.config["ENTITY_AGENT_TIMEOUT"])
    except (ValueError, ValidationError) as error:
        db.session.rollback()

        return jsonify(error=str(error) if isinstance(error, ValueError) else "Invalid entity configuration."), 400
    except IntegrityError:
        db.session.rollback()

        return jsonify(error="Configuration changed during generation. Reload and retry."), 409
    except subprocess.TimeoutExpired:
        return jsonify(error="Generation timed out. Your saved definition is unchanged."), 504
    except (OSError, RuntimeError):
        return jsonify(error="Generation failed. Check local Codex sign-in and retry."), 502

    return jsonify(result), 200


@api.route("/endpoints", methods=["GET", "PUT"])
@log_function
def endpoint_configuration() -> tuple:
    """Read and save the selected project's endpoint catalog."""
    try:
        result = read_endpoints() if request.method == "GET" else save_endpoints(request.get_json())
    except IntegrityError:
        db.session.rollback()

        return jsonify(error="Endpoints changed. Reload and retry."), 409
    except (ValueError, ValidationError):
        return jsonify(error="Invalid endpoints. Choose an entity, operation, matching method and unique path."), 400

    return jsonify(result), 200


@api.route('/load-testing', methods=['GET', 'POST'])
@log_function
def load_testing() -> tuple:
    """Read the latest project report or start its real container load run."""
    from services.load_testing_service import read_load_testing, start_load_testing

    if request.method == 'GET':
        return jsonify(read_load_testing()), 200

    try:
        return jsonify(start_load_testing(request.get_json())), 202
    except (ValueError, ValidationError) as error:
        return jsonify(error=error.message if isinstance(error, ValidationError) else str(error)), 400
    except OSError:
        return jsonify(error='Could not prepare load testing files. Check project storage permissions.'), 500


@api.get('/entity-configurations/<int:entity_id>/logs/<run_id>')
@log_function
def entity_generation_logs(entity_id: int, run_id: str) -> tuple:
    """Read only the selected project's owned entity execution events."""
    from services.configuration_service import owned_entity
    from services.generation_logs_service import read_generation_logs

    owned_entity(entity_id)
    try:
        result = read_generation_logs(entity_id, run_id, int(request.args.get('cursor', '0')))
    except ValueError:
        return jsonify(error='Invalid generation log request.'), 400

    return jsonify(result), 200

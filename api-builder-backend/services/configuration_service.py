"""Own project schemas and endpoint snapshots consumed by the UI and container builder."""

import re

from flask import g
from jsonschema import validate
from sqlalchemy import select, update
from werkzeug.exceptions import Conflict, NotFound

from models import ProjectEntityName, ProjectEntityDefinition, ProjectEndpoints, db
from runtime.worker import run_agent_worker
from runtime.registry import AGENTS
from validation import validate_attribute_names, validate_endpoint_payload

from services.logger_service import log_function, log_event, LogStep
from services.generation_logs_service import generation_log_context, RUN_PATTERN

METHODS = {'list': 'GET', 'get': 'GET', 'create': 'POST', 'update': 'PATCH', 'delete': 'DELETE', 'sell': 'POST'}


@log_function
def owned_entity(entity_id: int) -> ProjectEntityName:
    """Resolve a catalog entity only within the selected workspace."""
    entity = db.session.get(ProjectEntityName, entity_id)

    if entity is None or entity.project_id != g.project_id:
        raise NotFound('Entity not found.')

    return entity


@log_function
def read_definition(entity_id: int) -> dict:
    """Return an empty or saved schema without creating database rows on reads."""
    entity = owned_entity(entity_id)
    row = db.session.get(ProjectEntityDefinition, entity_id)

    return {'entity_id': entity.id, 'revision': row.revision if row else 0,
            'prompt': row.prompt if row else '',
            'attributes': row.document['attributes'] if row else [],
            'relationships': row.document['relationships'] if row else []}


@log_function
def generate_definition(entity_id: int, payload: dict, timeout: int) -> dict:
    """Generate with the registered agent and reject stale or cross-project output."""
    validate(payload, {'type': 'object', 'additionalProperties': False, 'required': ['prompt', 'revision'],
        'properties': {'run_id': {'type': 'string', 'pattern': '^' + RUN_PATTERN + '$'}, 'prompt': {'type': 'string', 'minLength': 1, 'maxLength': 4000, 'pattern': r'\S'},
                       'revision': {'type': 'integer', 'minimum': 0}}})
    owned_entity(entity_id)

    with generation_log_context(entity_id, payload.get('run_id')):
        return generate_validated_definition(entity_id, payload, timeout)


@log_function
def generate_validated_definition(entity_id: int, payload: dict, timeout: int) -> dict:
    """Generate and persist a validated request inside its correlated log context."""
    entity = owned_entity(entity_id)
    before = read_definition(entity_id)

    if before['revision'] != payload['revision']:
        raise Conflict('Entity changed. Reload before generating.')

    existing = [{'id': item.id, 'name': item.name} for item in db.session.scalars(
        select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id))]
    context = {'entity_id': entity_id, 'description': payload['prompt'], 'prompt': payload['prompt'],
               'entity': {'id': entity_id, 'name': entity.name, **before}, 'existing_entities': existing}
    db.session.rollback()
    log_event('entity.generation_requested', entity_id=entity_id, project_id=g.project_id)
    definition = run_agent_worker('entity-builder', context, timeout)
    validate_attribute_names(definition)

    if definition['entity_id'] != entity_id or any(
        relation['target_entity_id'] not in {item['id'] for item in existing} for relation in definition['relationships']
    ):
        raise ValueError('Agent returned an unrelated entity reference.')

    if len(definition['attributes']) < 1:
        raise ValueError('Agent returned no attributes. Describe the entity fields, for example: name, status, and created date.')

    owned_entity(entity_id)
    row = db.session.get(ProjectEntityDefinition, entity_id)

    if row is None:
        row = ProjectEntityDefinition(entity_id=entity_id, revision=0, prompt='', document={})
        db.session.add(row)
        db.session.flush()

    result = db.session.execute(update(ProjectEntityDefinition).where(
        ProjectEntityDefinition.entity_id == entity_id, ProjectEntityDefinition.revision == payload['revision']
    ).values(revision=payload['revision'] + 1, prompt=payload['prompt'], document=definition))

    if result.rowcount != 1:
        raise Conflict('Entity changed during generation. Reload and retry.')

    db.session.commit()

    log_event('entity.definition_saved', entity_id=entity_id, project_id=g.project_id, count=len(definition['attributes']))

    return read_definition(entity_id)


@log_function
def read_endpoints() -> dict:
    """Use saved endpoints or derive deterministic defaults for an untouched project."""
    row = db.session.get(ProjectEndpoints, g.project_id)
    names = [item.name for item in db.session.scalars(select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id))]

    if row:
        return {'routes': row.document, 'revision': row.revision, 'entities': names}

    routes = []

    for entity in db.session.scalars(select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id)):
        slug = re.sub(r'[^a-z0-9_-]+', '-', entity.name.strip().lower()).strip('-') or f'entity-{entity.id}'

        for operation, method in METHODS.items():
            if operation == 'sell':
                continue

            routes.append({'id': entity.id * 10 + len(routes) + 1, 'entity': entity.name, 'operation': operation,
                           'method': method, 'path': f'/{slug}/{operation}', 'access': 'authenticated',
                           'type': 'authenticated', 'prompt': ''})

    return {'routes': routes, 'revision': 0, 'entities': names}


@log_function
def save_endpoints(payload: dict) -> dict:
    """Validate and compare revisions before replacing the endpoint snapshot."""
    names = [item.name for item in db.session.scalars(select(ProjectEntityName).where(ProjectEntityName.project_id == g.project_id))]
    validate_endpoint_payload(payload, names)
    row = db.session.get(ProjectEndpoints, g.project_id)

    if row is None:
        row = ProjectEndpoints(project_id=g.project_id, revision=0, document=[])
        db.session.add(row)
        db.session.flush()

    result = db.session.execute(update(ProjectEndpoints).where(
        ProjectEndpoints.project_id == g.project_id, ProjectEndpoints.revision == payload['revision']
    ).values(revision=payload['revision'] + 1, document=payload['routes']))

    if result.rowcount != 1:
        raise Conflict('Endpoints changed. Reload before saving.')

    db.session.commit()

    return read_endpoints()


@log_function
def delete_entity_configuration(entity: ProjectEntityName) -> None:
    """Remove dependent schema and routes inside the caller's transaction."""
    definition = db.session.get(ProjectEntityDefinition, entity.id)

    if definition:
        db.session.delete(definition)

    endpoints = db.session.get(ProjectEndpoints, entity.project_id)

    if endpoints:
        endpoints.document = [route for route in endpoints.document if route['entity'] != entity.name]
        endpoints.revision += 1


@log_function
def rename_entity_endpoints(entity: ProjectEntityName, name: str) -> None:
    """Preserve configured paths while updating the referenced display name."""
    endpoints = db.session.get(ProjectEndpoints, entity.project_id)

    if endpoints:
        endpoints.document = [{**route, 'entity': name} if route['entity'] == entity.name else route for route in endpoints.document]
        endpoints.revision += 1


@log_function
def add_entity_endpoints(entity: ProjectEntityName) -> None:
    """Append defaults for a newly created entity to an already saved catalog."""
    row = db.session.get(ProjectEndpoints, entity.project_id)

    if row is None:
        return

    slug = re.sub(r'[^a-z0-9_-]+', '-', entity.name.strip().lower()).strip('-') or f'entity-{entity.id}'
    routes = list(row.document)
    next_id = max((route['id'] for route in routes), default=0) + 1

    for operation, method in METHODS.items():
        if operation == 'sell':
            continue

        path = f'/{slug}/{operation}'

        if any(route['path'] == path for route in routes):
            raise Conflict('Entity name conflicts with existing endpoint paths.')

        routes.append({'id': next_id, 'entity': entity.name, 'operation': operation, 'method': method,
                       'path': path, 'access': 'authenticated', 'type': 'authenticated', 'prompt': ''})
        next_id += 1

    row.document = routes
    row.revision += 1


@log_function
def save_attributes(entity_id: int, payload: dict) -> dict:
    """Persist reviewed attribute edits without generating implementation code."""
    owned_entity(entity_id)
    validate(payload, {'type': 'object', 'additionalProperties': False, 'required': ['revision', 'attributes'],
        'properties': {'revision': {'type': 'integer', 'minimum': 0},
                       'attributes': AGENTS['entity-builder'].load_schema()['properties']['attributes']}})
    row = db.session.get(ProjectEntityDefinition, entity_id)
    if row is None or row.revision != payload['revision']:
        raise Conflict('Entity changed. Reload its configuration before saving edits.')

    document = {**row.document, 'attributes': payload['attributes']}
    validate_attribute_names(document)
    result = db.session.execute(update(ProjectEntityDefinition).where(
        ProjectEntityDefinition.entity_id == entity_id, ProjectEntityDefinition.revision == payload['revision']
    ).values(revision=payload['revision'] + 1, document=document))
    if result.rowcount != 1:
        raise Conflict('Entity changed during editing. Reload and retry.')

    db.session.commit()
    log_event('entity.attributes_updated', entity_id=entity_id, project_id=g.project_id, count=len(payload['attributes']))

    return read_definition(entity_id)

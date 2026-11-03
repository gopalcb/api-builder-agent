"""Render project configuration as Markdown and persist revision-checked document edits."""

import hashlib
import json

from flask import g
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest, Conflict, NotFound

from models import Project, ProjectEntityName, ProjectRbacConfiguration, ProjectCachingConfiguration, ProjectDocument, db

from services.logger_service import log_function, log_event, LogStep


@log_function
def generated_documents() -> dict:
    """Build documentation only from the selected project's persisted configuration."""
    project = db.session.get(Project, g.project_id)
    entities = list(db.session.scalars(select(ProjectEntityName).where(
        ProjectEntityName.project_id == g.project_id).order_by(ProjectEntityName.id)))
    documents = {
        'overview': ('README.md', 'Project', f'# {project.name}\n\n{project.summary}\n'),
        'entities': ('entities.md', 'Entities', '# Entities\n\n' + (
            '\n'.join(f'- {entity.name}' for entity in entities) if entities else 'No saved entities yet.') +
            '\n\nThis catalog contains saved entity names. Attribute drafts are not part of this saved configuration.\n'),
        'swagger': ('swagger.md', 'API reference', f'# Swagger API reference\n\nOpen the project Swagger page from the toolbar to explore the generated OpenAPI contract.\n\n```mermaid\nflowchart LR\n    Builder[API Builder] --> Spec[OpenAPI specification]\n    Spec --> Swagger[Swagger UI]\n    Swagger --> API[Local generated API]\n```\n'),
        'implementation-plan': ('implementation-plan.md', 'Implementation', '# Implementation plan\n\n1. Create the reviewed API plan.\n2. Validate the saved entity and endpoint configuration.\n3. Build and test the generated container API.\n4. Document the API contract and publish the tested artifact.\n'),
        'implementation-summary': ('implementation-summary.md', 'Implementation', '# Implementation summary\n\nThe current project configuration is packaged as a tested local container API. Review the build logs for execution details and use Swagger for the endpoint contract.\n'),
    }
    for key, title, model in [('rbac', 'Role permissions', ProjectRbacConfiguration), ('caching', 'Caching', ProjectCachingConfiguration)]:
        row = db.session.get(model, g.project_id)
        if row:
            content = f'# {title}\n\nSaved configuration, revision {row.revision}.\n\n```json\n{json.dumps(row.document, indent=2)}\n```\n'
            documents[key] = (f'{key}.md', title, content)
    return documents


@log_function
def read_documents() -> list:
    """Overlay saved edits without overwriting them when configuration changes."""
    saved = {row.slug: row for row in db.session.scalars(select(ProjectDocument).where(ProjectDocument.project_id == g.project_id))}
    result = []
    for slug, (filename, category, content) in generated_documents().items():
        row = saved.get(slug)
        if row:
            content = row.content
        result.append({'id': slug, 'filename': filename, 'category': category, 'content': content,
                       'revision': row.revision if row else 0,
                       'etag': hashlib.sha256(content.encode()).hexdigest()})
    return result


@log_function
def save_document(slug: str, payload: dict) -> dict:
    """Reject stale saves and store edits under the selected project only."""
    if not isinstance(payload, dict) or not isinstance(payload.get('content'), str) or len(payload['content'].encode()) > 48000:
        raise BadRequest('Document content must be at most 48 KB.')
    if type(payload.get('revision')) is not int or not isinstance(payload.get('etag'), str):
        raise BadRequest('A document revision and etag are required.')
    current = next((document for document in read_documents() if document['id'] == slug), None)
    if current is None:
        raise NotFound('Document not found.')
    if current['revision'] != payload['revision'] or current['etag'] != payload['etag']:
        raise Conflict('This document changed. Reopen it before saving your edits.')
    try:
        if current['revision'] == 0:
            db.session.add(ProjectDocument(project_id=g.project_id, slug=slug, content=payload['content'], revision=1))
        else:
            result = db.session.execute(update(ProjectDocument).where(
                ProjectDocument.project_id == g.project_id, ProjectDocument.slug == slug,
                ProjectDocument.revision == current['revision']).values(content=payload['content'], revision=current['revision'] + 1))
            if result.rowcount != 1:
                raise Conflict('This document changed. Reopen it before saving your edits.')
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise Conflict('This document changed. Reopen it before saving your edits.') from error
    return next(document for document in read_documents() if document['id'] == slug)

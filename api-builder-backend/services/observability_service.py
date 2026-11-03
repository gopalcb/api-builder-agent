"""Persist revisioned project tracing settings and expose the shared localhost runtime."""

from flask import g
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import Conflict

from models import ProjectObservabilityConfiguration, db
from shared.telemetry_service import DEFAULT_CONFIGURATION


def read_observability() -> dict:
    """Return defaults without creating a row for an unconfigured project."""
    row = db.session.get(ProjectObservabilityConfiguration, g.project_id)

    return {'revision': row.revision if row else 0,
            'configuration': row.document if row else dict(DEFAULT_CONFIGURATION)}


def save_observability(payload: dict) -> dict:
    """Apply a validated policy with atomic optimistic locking."""
    revision = payload['revision']

    if revision == 0:
        db.session.add(ProjectObservabilityConfiguration(project_id=g.project_id, revision=1,
                                                        document=payload['configuration']))
    else:
        result = db.session.execute(update(ProjectObservabilityConfiguration).where(
            ProjectObservabilityConfiguration.project_id == g.project_id,
            ProjectObservabilityConfiguration.revision == revision,
        ).values(revision=revision + 1, document=payload['configuration']))

        if result.rowcount != 1:
            raise Conflict('Configuration changed. Reload before saving.')

    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise Conflict('Configuration changed. Reload before saving.') from error

    return read_observability()

"""Run the entity agent and atomically persist validated generated metadata."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from jsonschema import ValidationError, validate
from sqlalchemy import delete, select, update

from models import Entity, EntityAttribute, EntityRelationship, db
from validation import validate_attribute_names

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from runtime.registry import AGENTS

from services.logger_service import log_function, log_event, LogStep, worker_environment

OUTPUT_SCHEMA = AGENTS["entity-builder"].load_schema()


class GenerationError(Exception):
    """A caller-safe generation failure with an appropriate HTTP status."""

    def __init__(self, message: str, status: int = 502) -> None:
        """Attach the HTTP status while keeping provider internals private."""
        super().__init__(message)
        self.status = status


@log_function
def run_entity_agent(context: dict, timeout: int) -> dict:
    """Run the SDK worker with a deadline and reap its process group on timeout."""
    try:
        with subprocess.Popen(
            [sys.executable, str(ROOT / "runtime" / "runner.py"), "entity-builder"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True, env=worker_environment(),
        ) as process:
            try:
                output, stderr = process.communicate(json.dumps(context), timeout=timeout)
            except subprocess.TimeoutExpired as error:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                raise GenerationError("Entity generation timed out; existing data was preserved", 504) from error

            if process.returncode:
                raise GenerationError("Codex generation failed; check the local Codex sign-in and runtime")
    except OSError as error:
        raise GenerationError("Unable to start the entity agent") from error

    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise GenerationError("Codex returned invalid JSON") from error


@log_function
def generate_entity_attributes(payload: dict, timeout: int) -> dict:
    """Generate outside the database transaction, then replace one schema atomically."""
    entity = db.session.get(Entity, payload["entity_id"])

    if entity is None:
        raise GenerationError("Entity not found", 404)

    revision = entity.revision
    context = {
        **payload, "entity": entity.to_dict(),
        "existing_entities": [item.to_dict() for item in db.session.scalars(select(Entity).order_by(Entity.id))],
    }
    # Release the read transaction during the potentially long model request.
    db.session.rollback()
    definition = run_entity_agent(context, timeout)

    try:
        validate(definition, OUTPUT_SCHEMA)
    except ValidationError as error:
        raise GenerationError("Codex returned an invalid entity definition; existing data was preserved") from error

    try:
        validate_attribute_names(definition)
    except ValueError as error:
        raise GenerationError(str(error)) from error

    result = db.session.execute(
        update(Entity).where(Entity.id == payload["entity_id"], Entity.revision == revision)
        .values(revision=revision + 1)
    )

    if result.rowcount != 1:
        raise GenerationError("Entity changed during generation; retry with the latest definition", 409)

    for model in (EntityAttribute, EntityRelationship):
        db.session.execute(delete(model).where(model.entity_id == payload["entity_id"]))

    db.session.add_all([
        EntityAttribute(entity_id=payload["entity_id"], **item) for item in definition["attributes"]
    ])
    db.session.add_all([
        EntityRelationship(entity_id=payload["entity_id"], **item) for item in definition["relationships"]
    ])
    db.session.commit()
    db.session.expire_all()

    return db.session.get(Entity, payload["entity_id"]).to_dict()

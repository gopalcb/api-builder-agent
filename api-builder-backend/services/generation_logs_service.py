"""Expose safe incremental execution events for one owned entity generation."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from flask import current_app, g
from werkzeug.exceptions import Conflict

from shared import logging_service

RUN_PATTERN = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
PUBLIC_FIELDS = ('timestamp', 'level', 'event', 'function', 'step', 'agent', 'duration_ms', 'error_type')


def state_path(entity_id: int, run_id: str) -> Path:
    """Resolve only a validated run identifier beneath the selected project."""
    if not re.fullmatch(RUN_PATTERN, run_id):
        raise ValueError('Invalid generation run ID.')

    directory = Path(current_app.config.get('GENERATION_LOG_ROOT', Path(current_app.instance_path) / 'entity-generations')) / str(g.project_id) / str(entity_id)
    directory.mkdir(parents=True, exist_ok=True)

    return directory / f'{run_id}.json'


@contextmanager
def generation_log_context(entity_id: int, run_id: str | None, event: str = 'entity.generation'):
    """Propagate correlation into worker logs and retain the start offset/status."""
    run_id = run_id or str(uuid4())
    state_file = state_path(entity_id, run_id)
    log_file = logging_service.configure_logging()
    state = {'file': str(log_file), 'offset': log_file.stat().st_size, 'status': 'running'}
    pending = state_file.with_suffix('.' + uuid4().hex + '.tmp')
    pending.write_text(json.dumps(state))
    try:
        os.link(pending, state_file)
    except FileExistsError as error:
        raise Conflict('This generation run already exists. Start a new generation.') from error
    finally:
        pending.unlink()

    token = logging_service.LOG_CONTEXT.set({**logging_service.LOG_CONTEXT.get(),
        'generation_id': run_id, 'entity_id': entity_id, 'project_id': g.project_id})
    try:
        with logging_service.LogStep(event):
            logging_service.log_event(event + '.started')
            yield
            state['status'] = 'completed'
            logging_service.log_event(event + '.completed')
    finally:
        if state['status'] == 'running':
            state['status'] = 'failed'

        logging_service.LOG_CONTEXT.reset(token)
        temporary = state_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(state))
        temporary.replace(state_file)


def read_generation_logs(entity_id: int, run_id: str, cursor: int) -> dict:
    """Page only matching safe fields; cursors are relative to the run's start."""
    if cursor < 0:
        raise ValueError('Invalid log cursor.')

    state_file = state_path(entity_id, run_id)
    if not state_file.exists():
        return {'entries': [], 'cursor': 0, 'status': 'pending', 'more': False}

    state = json.loads(state_file.read_text())
    entries = []
    with Path(state['file']).open('rb') as stream:
        start = state['offset']
        stream.seek(min(start + cursor, Path(state['file']).stat().st_size))
        end = stream.tell() + 65536
        while stream.tell() < end:
            position = stream.tell()
            line = stream.readline()
            if not line or not line.endswith(b'\n'):
                stream.seek(position)
                break

            event = json.loads(line)
            if (event.get('generation_id') == run_id and event.get('entity_id') == entity_id
                    and event.get('project_id') == g.project_id):
                entries.append({key: event[key] for key in PUBLIC_FIELDS if key in event})

        cursor = stream.tell() - start
        more = stream.tell() < Path(state['file']).stat().st_size

    return {'entries': entries, 'cursor': cursor, 'status': state['status'], 'more': more}

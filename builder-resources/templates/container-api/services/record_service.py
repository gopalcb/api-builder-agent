"""Execute CRUD and atomic stock sales against the configured entity schema."""

import json
import sqlite3
from uuid import uuid4

from werkzeug.exceptions import BadRequest, Conflict, NotFound

from models import connection
from validation import validate_record, validate_sale

from services.logger_service import log_function, log_event, LogStep


@log_function
def execute(database_path: str, entity: dict, operation: str, payload: dict, record_id: str | None) -> tuple:
    """Run one transaction; concurrent sales cannot oversell the same inventory."""
    name = entity['name']

    with connection(database_path) as database:
        if operation == 'list':
            rows = database.execute('SELECT document FROM records WHERE entity=? ORDER BY id', (name,)).fetchall()

            return {'items': [json.loads(row['document']) for row in rows]}, 200

        if operation == 'create':
            document = {**validate_record(payload, entity['attributes']), 'id': payload.get('id') or str(uuid4())}

            try:
                database.execute('INSERT INTO records VALUES (?, ?, ?)', (name, document['id'], json.dumps(document)))
            except sqlite3.IntegrityError as error:
                raise Conflict('Record already exists.') from error

            return document, 201

        if not record_id:
            raise BadRequest('Provide id in the path, query or JSON body.')

        database.execute('BEGIN IMMEDIATE')
        row = database.execute('SELECT document FROM records WHERE entity=? AND id=?', (name, record_id)).fetchone()

        if row is None:
            raise NotFound('Record not found.')

        document = json.loads(row['document'])

        if operation == 'get':
            return document, 200

        if operation == 'delete':
            database.execute('DELETE FROM records WHERE entity=? AND id=?', (name, record_id))

            return {'deleted': True, 'id': record_id}, 200

        if operation == 'update':
            values = validate_record(payload, entity['attributes'], partial=True)

            if 'id' in values and values['id'] != record_id:
                raise BadRequest('id cannot be changed.')

            document.update(values)
        elif operation == 'sell':
            quantity = validate_sale(payload)
            field = next((key for key in ('stock', 'quantity') if type(document.get(key)) is int), None)

            if field is None:
                raise BadRequest('Sell requires an integer stock or quantity attribute.')

            if document[field] < quantity:
                raise Conflict('Insufficient stock.')

            document[field] -= quantity
        else:
            raise BadRequest('Unsupported operation.')

        database.execute('UPDATE records SET document=? WHERE entity=? AND id=?', (json.dumps(document), name, record_id))

        return document, 200

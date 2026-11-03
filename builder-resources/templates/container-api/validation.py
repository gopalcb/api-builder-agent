"""Validate generated entity values and stock-sale requests at the HTTP boundary."""

from datetime import date, datetime
import math
from uuid import UUID

from werkzeug.exceptions import BadRequest

from services.logger_service import log_function, log_event, LogStep


@log_function
def validate_record(payload: object, attributes: list, partial: bool = False) -> dict:
    """Enforce field names, required values and schema types before persistence."""
    if not isinstance(payload, dict):
        raise BadRequest('Send a JSON object.')

    fields = {attribute['name']: attribute for attribute in attributes}

    if set(payload) - fields.keys() - {'id'}:
        raise BadRequest('Unknown attributes: ' + ', '.join(sorted(set(payload) - fields.keys() - {'id'})))

    for name, attribute in fields.items():
        if name == 'id' or (partial and name not in payload):
            continue

        value = payload.get(name)

        if value is None:
            if not attribute['nullable']:
                raise BadRequest(f'{name} is required.')

            continue

        kind = attribute['data_type']
        valid = True

        if kind in {'integer', 'float', 'decimal'}:
            valid = type(value) is int if kind == 'integer' else type(value) in (int, float)
            valid = valid and math.isfinite(value)
        elif kind == 'boolean':
            valid = type(value) is bool
        elif kind in {'string', 'text', 'uuid', 'date', 'datetime'}:
            valid = isinstance(value, str)

        if not valid:
            raise BadRequest(f'{name} must have type {kind}.')

        try:
            if kind == 'uuid':
                UUID(value)
            elif kind == 'date':
                date.fromisoformat(value)
            elif kind == 'datetime':
                datetime.fromisoformat(value)
        except ValueError as error:
            raise BadRequest(f'{name} must have type {kind}.') from error

        if name in {'price', 'stock', 'quantity'} and type(value) in (int, float) and value < 0:
            raise BadRequest(f'{name} cannot be negative.')

    if 'id' in payload and (not isinstance(payload['id'], str) or not payload['id'] or len(payload['id']) > 100):
        raise BadRequest('id must be a non-empty string up to 100 characters.')

    return payload


@log_function
def validate_sale(payload: object) -> int:
    """Require a positive integral quantity; reject silently ignored fields."""
    if not isinstance(payload, dict) or set(payload) - {'id', 'quantity'} or type(payload.get('quantity')) is not int or payload['quantity'] <= 0:
        raise BadRequest('Sell requires a positive integer quantity.')

    return payload['quantity']

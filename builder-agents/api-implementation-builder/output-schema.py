"""Allow implementation changes only to existing application service/validation modules."""

OUTPUT_SCHEMA = {
    'description': 'Complete application service and validation source for the reviewed API configuration.',
    'title': 'ApiImplementation', 'type': 'object', 'additionalProperties': False,
    'required': ['record_service', 'validation'],
    'properties': {
        'record_service': {'type': 'string', 'minLength': 100, 'maxLength': 60000},
        'validation': {'type': 'string', 'minLength': 100, 'maxLength': 40000},
    },
}

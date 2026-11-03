"""Output contract for generated entity attributes and relationships."""

OUTPUT_SCHEMA = {
    "title": "EntityDefinition",
    "description": "Generated attributes and outgoing relationships for one existing entity.",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "entity_id",
        "attributes",
        "relationships"
    ],
    "properties": {
        "entity_id": {
            "type": "integer",
            "minimum": 1
        },
        "attributes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name",
                    "data_type",
                    "nullable",
                    "description"
                ],
                "properties": {
                    "name": {
                        "type": "string",
                        "pattern": "^[A-Za-z][A-Za-z0-9_]{0,99}$"
                    },
                    "data_type": {
                        "type": "string",
                        "enum": [
                            "string",
                            "text",
                            "integer",
                            "float",
                            "decimal",
                            "boolean",
                            "date",
                            "datetime",
                            "uuid",
                            "json"
                        ]
                    },
                    "nullable": {
                        "type": "boolean"
                    },
                    "description": {
                        "type": "string",
                        "maxLength": 4000
                    }
                }
            }
        },
        "relationships": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name",
                    "target_entity_id",
                    "relationship_type",
                    "description"
                ],
                "properties": {
                    "name": {
                        "type": "string",
                        "pattern": "^[A-Za-z][A-Za-z0-9_]{0,99}$"
                    },
                    "target_entity_id": {
                        "type": "integer",
                        "minimum": 1
                    },
                    "relationship_type": {
                        "type": "string",
                        "enum": [
                            "one_to_one",
                            "one_to_many",
                            "many_to_one",
                            "many_to_many"
                        ]
                    },
                    "description": {
                        "type": "string",
                        "maxLength": 4000
                    }
                }
            }
        }
    }
}

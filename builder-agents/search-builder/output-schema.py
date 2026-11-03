"""Reviewable search route proposals; no executable code or credentials."""

TEXT = {"type": "string", "minLength": 1, "maxLength": 2000}
TEXTS = {"type": "array", "maxItems": 20, "items": TEXT}
OUTPUT_SCHEMA = {
    "title": "SearchConfiguration",
    "description": "A proposed route configuration with explicit unresolved requirements.",
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "source", "fields", "embedding", "ranking", "request", "response", "steps", "requirements"],
    "properties": {
        "summary": TEXT,
        "source": TEXT,
        "fields": TEXTS,
        "embedding": {"anyOf": [
            {"type": "null"},
            {"type": "object", "additionalProperties": False,
             "required": ["model", "dimensions", "chunking"],
             "properties": {"model": TEXT, "dimensions": TEXT, "chunking": TEXT}},
        ]},
        "ranking": {"type": "string", "enum": ["none", "lexical", "vector", "rrf"]},
        "request": TEXT,
        "response": TEXT,
        "steps": {**TEXTS, "minItems": 1},
        "requirements": TEXTS,
    },
}

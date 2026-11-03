"""Structured RBAC proposals consumed by the runtime and configuration API."""

ROLE = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,39}$"},
        "description": {"type": "string", "maxLength": 500},
        "group": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,64}$"},
        "create_group": {"type": "boolean"},
    },
    "required": ["id", "description", "group", "create_group"],
}
GRANT = {
    "type": "object", "additionalProperties": False,
    "properties": {"role": {"type": "string"}, "route": {"type": "string"}},
    "required": ["role", "route"],
}
CASE = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "roles": {"type": "array", "items": {"type": "string"}, "maxItems": 20, "uniqueItems": True},
        "route": {"type": "string"}, "expected": {"enum": ["allow", "deny"]},
    },
    "required": ["roles", "route", "expected"],
}
OUTPUT_SCHEMA = {
    "title": "RbacProposal", "description": "Explicit role grants for supplied API routes.",
    "type": "object", "additionalProperties": False,
    "properties": {
        "roles": {"type": "array", "items": ROLE, "maxItems": 20},
        "grants": {"type": "array", "items": GRANT, "maxItems": 500, "uniqueItems": True},
        "notes": {"type": "string", "maxLength": 4000},
        "questions": {"type": "array", "items": {"type": "string", "maxLength": 500}, "maxItems": 20},
        "cases": {"type": "array", "items": CASE, "maxItems": 50},
    },
    "required": ["roles", "grants", "notes", "questions", "cases"],
}

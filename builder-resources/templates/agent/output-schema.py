"""Define a minimal proposal envelope to specialize for a registered agent."""

OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "requirements"],
    "properties": {
        "summary": {"type": "string", "maxLength": 4000},
        "requirements": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 500}},
    },
}

"""Constrain infrastructure proposals to reviewable recommendations, never executable code."""

TEXT = {"type": "string", "minLength": 1, "maxLength": 2000}
OUTPUT_SCHEMA = {
    "title": "InfrastructureProposal",
    "description": "An AWS serverless proposal and conditional service decisions for review.",
    "type": "object", "additionalProperties": False,
    "required": ["summary", "services", "recommendations", "requirements"],
    "properties": {
        "summary": TEXT,
        "services": {
            "type": "object", "additionalProperties": False,
            "required": ["sqs", "sns", "redis"],
            "properties": {name: {"type": "boolean"} for name in ("sqs", "sns", "redis")},
        },
        "recommendations": {"type": "array", "minItems": 1, "maxItems": 12, "items": TEXT},
        "requirements": {"type": "array", "maxItems": 12, "items": TEXT},
    },
}

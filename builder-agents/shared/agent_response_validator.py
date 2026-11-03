"""Validate agent data at its boundaries using JSON Schema.

Configuration and model consumers can trust validated data without repeating
manual shape checks. Pydantic continues to own deployment settings validation.
"""

from jsonschema import Draft202012Validator, validate

from shared.logging_service import log_function, log_event, LogStep


OUTPUT_SCHEMA_METADATA = {
    "type": "object",
    "properties": {
        "type": {"const": "object"},
        "title": {"type": "string", "pattern": r"\S"},
        "description": {"type": "string", "pattern": r"\S"},
    },
    "required": ["type", "title", "description"],
}


@log_function
def validate_agent_response(response: object, schema: dict) -> object:
    """Validate a decoded response against its schema and return it unchanged."""
    validate(response, schema)

    return response


@log_function
def validate_agent_assets(prompt: str, schema: object) -> None:
    """Require a usable prompt and a valid object schema with model metadata."""
    validate_agent_response(prompt, {"type": "string", "pattern": r"\S"})
    validate_agent_response(schema, OUTPUT_SCHEMA_METADATA)
    Draft202012Validator.check_schema(schema)


@log_function
def validate_agent_tools(names: tuple, registry: dict, output_name: str) -> list:
    """Resolve registered tools and reject missing, ambiguous or shadowed names."""
    missing = set(names) - registry.keys()

    if missing:
        raise ValueError(f"Unregistered agent tools: {', '.join(sorted(missing))}")

    tools = [registry[name] for name in names]
    tool_names = [getattr(tool, "name", None) for tool in tools]
    validate_agent_response(tool_names, {
        "type": "array", "uniqueItems": True,
        "items": {"type": "string", "minLength": 1, "not": {"const": output_name}},
    })

    return tools

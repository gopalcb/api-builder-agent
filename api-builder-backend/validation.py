"""Validate entity envelopes and the explicit RBAC configuration contract."""

import math
from pathlib import Path
import re
from runpy import run_path
from urllib.parse import urlsplit

from jsonschema import validate

from services.logger_service import log_function

PROPOSAL_SCHEMA = run_path(str(Path(__file__).resolve().parents[1] / "builder-agents/rbac-builder/output-schema.py"))["OUTPUT_SCHEMA"]
CONFIGURATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        **PROPOSAL_SCHEMA["properties"],
        "schema_version": {"const": 1},
        "identity": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "provider": {"const": "cognito"},
                "user_pool_id": {"type": "string", "pattern": "^$|^[a-z]{2}(-[a-z]+)+-[0-9]+_[A-Za-z0-9]+$"},
                "client_id": {"type": "string", "pattern": "^[a-z0-9]{0,128}$"},
            },
            "required": ["provider", "user_pool_id", "client_id"],
        },
        "routes": {"type": "array", "maxItems": 100, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "key": {"type": "string", "maxLength": 300},
                "method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]},
                "path": {"type": "string", "maxLength": 250, "pattern": "^/(?:[A-Za-z0-9._~-]+|\\{[A-Za-z_][A-Za-z0-9_]*\\})?(?:/(?:[A-Za-z0-9._~-]+|\\{[A-Za-z_][A-Za-z0-9_]*\\}))*$"},
                "access": {"enum": ["public", "authenticated"]},
            },
            "required": ["key", "method", "path", "access"],
        }},
    },
    "required": [*PROPOSAL_SCHEMA["required"], "schema_version", "identity", "routes"],
}


@log_function
def validate_payload(payload: object) -> dict:
    """Reject non-object payloads and return dictionaries unchanged."""
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")

    return payload


@log_function
def is_local_connection_origin(origin: str, server_url: str) -> bool:
    """Allow a valid browser origin on the server's loopback host and scheme."""
    match = re.fullmatch(r"(https?)://(localhost|127\.0\.0\.1|\[::1\])(?::([0-9]{1,5}))?", origin)

    if match is None or (match[3] is not None and not 1 <= int(match[3]) <= 65535):
        return False

    server = urlsplit(server_url)

    return match[1] == server.scheme and match[2].strip("[]") == server.hostname


SEARCH_REQUEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["type", "path", "prompt"],
    "properties": {
        "type": {"enum": ["embedding", "semantic", "regular", "hybrid"]},
        "path": {"type": "string", "maxLength": 250,
                 "pattern": r"^/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+$"},
        "prompt": {"type": "string", "minLength": 1, "maxLength": 4000, "pattern": r"\S"},
    },
}

INFRASTRUCTURE_REQUEST_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["platform", "deployment_mode", "environment", "requirements"],
    "properties": {
        "platform": {"const": "aws"},
        "deployment_mode": {"const": "serverless"},
        "environment": {"enum": ["dev", "staging", "prod"]},
        "requirements": {"type": "string", "maxLength": 4000},
    },
}


# RBAC has a stricter boundary than the existing entity endpoints.
@log_function
def validate_rbac_request(payload: object, operation: str) -> dict:
    """Validate an HTTP request once, then check configuration relationships."""
    properties = {"revision": {"type": "integer", "minimum": 0}}
    required = ["revision"]

    if operation != "export":
        properties["configuration"] = CONFIGURATION_SCHEMA
        required.append("configuration")

    if operation == "generate":
        properties["prompt"] = {"type": "string", "minLength": 1, "maxLength": 4000, "pattern": r"\S"}
        required.append("prompt")

    if operation == "preview":
        properties.update({"roles": {"type": "array", "maxItems": 20, "items": {"type": "string"}}, "route": {"type": "string", "maxLength": 300}})
        required.extend(["roles", "route"])

    validate(payload, {"type": "object", "additionalProperties": False, "properties": properties, "required": required})

    if operation != "export":
        validate_rbac_semantics(payload["configuration"])

    return payload


@log_function
def validate_rbac_semantics(configuration: dict) -> None:
    """Check references and canonical routes after structural validation."""
    roles = {role["id"] for role in configuration["roles"]}
    groups = {role["group"] for role in configuration["roles"]}

    if len(roles) != len(configuration["roles"]) or len(groups) != len(configuration["roles"]):
        raise ValueError("Role IDs and group names must be unique.")

    routes = {}
    shapes = set()

    for route in configuration["routes"]:
        key = route["method"] + " " + route["path"]
        shape = re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", "{}", key)

        if route["key"] != key or shape in shapes or any(part in (".", "..") for part in route["path"].split("/")):
            raise ValueError("Routes need unique canonical method/path keys without dot segments.")

        routes[key] = route
        shapes.add(shape)

    for grant in configuration["grants"]:
        if grant["role"] not in roles or grant["route"] not in routes:
            raise ValueError("Every grant must reference an existing role and route.")

        if routes[grant["route"]]["access"] == "public":
            raise ValueError("Public routes cannot have restricted role grants.")

    for case in configuration["cases"]:
        if not set(case["roles"]) <= roles or case["route"] not in routes:
            raise ValueError("Suggested cases must reference existing roles and routes.")


@log_function
def validate_project_payload(payload: object) -> dict:
    """Validate a project's bounded name and summary before persistence."""
    if not isinstance(payload, dict) or set(payload) != {"name", "summary"}:
        raise ValueError("Provide a project name and summary.")
    result = {}
    for field, limit in (("name", 100), ("summary", 4000)):
        value = payload[field]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f"Project {field} must contain 1–{limit} characters.")
        result[field] = value.strip()
    return result


CACHING_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["kind", "path", "method", "access", "ttl_seconds", "api_type", "query_keys"],
    "properties": {
        "kind": {"enum": ["route", "redis", "gateway"]},
        "path": {"type": "string", "maxLength": 200, "pattern": "^/(?:[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*)?$"},
        "method": {"const": "GET"}, "access": {"const": "public"},
        "ttl_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
        "api_type": {"enum": ["http", "rest"]},
        "query_keys": {"type": "array", "maxItems": 10, "uniqueItems": True,
                       "items": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]{0,39}$"}},
    },
}


@log_function
def validate_caching_request(payload: object, export: bool = False) -> dict:
    """Validate the cache envelope and supported combinations at the boundary."""
    schema = {
        "type": "object", "additionalProperties": False,
        "required": ["revision"] if export else ["revision", "configuration"],
        "properties": {"revision": {"type": "integer", "minimum": 0}},
    }

    if not export:
        schema["properties"]["configuration"] = CACHING_SCHEMA

    validate(payload, schema)

    if not export and payload["configuration"]["kind"] == "gateway" and payload["configuration"]["api_type"] != "rest":
        raise ValueError("API Gateway response caching requires a REST API, not an HTTP API.")

    return payload


@log_function
def validate_entity_name(payload: object) -> str:
    """Normalize a required entity name at the HTTP boundary."""
    name = validate_payload(payload).get("name")

    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError("Entity name must contain 1–100 characters.")

    return name.strip()


@log_function
def validate_attribute_names(definition: dict) -> None:
    """Reject duplicate attribute names within one generated entity."""
    names = [item["name"].strip().casefold() for item in definition["attributes"]]

    if len(names) != len(set(names)):
        raise ValueError("Duplicate attribute names are not allowed; existing data was preserved")


@log_function
def validate_endpoint_payload(payload: dict, entities: list) -> None:
    """Validate executable route contracts and reject ambiguous path shapes."""
    methods = {'list': 'GET', 'get': 'GET', 'create': 'POST', 'update': 'PATCH', 'delete': 'DELETE', 'sell': 'POST'}
    validate(payload, {'type': 'object', 'additionalProperties': False, 'required': ['revision', 'routes'], 'properties': {
        'entities': {'type': 'array', 'items': {'type': 'string'}},
        'revision': {'type': 'integer', 'minimum': 0}, 'routes': {'type': 'array', 'maxItems': 100, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['id', 'operation', 'method', 'path', 'entity', 'access', 'type', 'prompt'],
            'properties': {
                'id': {'type': 'integer', 'minimum': 1}, 'operation': {'enum': [*methods, None]},
                'method': {'enum': ['GET', 'POST', 'PATCH', 'DELETE', None]},
                'path': {'type': 'string', 'maxLength': 250, 'pattern': r'^/(?:[A-Za-z0-9_-]+|\{id\})(?:/(?:[A-Za-z0-9_-]+|\{id\}))*$'},
                'entity': {'type': 'string'}, 'access': {'enum': ['public', 'authenticated']},
                'type': {'enum': ['public', 'authenticated', 'embedding', 'semantic', 'hybrid', 'regular']},
                'prompt': {'type': 'string', 'maxLength': 4000},
            }}}}})
    shapes = set()
    identifiers = set()

    for route in payload['routes']:
        shape = route['path'].replace('{id}', '{}')

        if route['path'].count('{id}') > 1 or shape in shapes or route['id'] in identifiers or route['path'] in {'/health', '/auth/token'}:
            raise ValueError('Duplicate or reserved endpoint.')

        if route['entity'] not in entities or (route['operation'] and route['method'] != methods[route['operation']]):
            raise ValueError('Choose an existing entity and a matching operation/method.')

        shapes.add(shape)
        identifiers.add(route['id'])


def validate_observability_request(payload: dict) -> dict:
    """Restrict OTLP configuration to local HTTP trace receivers and bounded resources."""
    validate(payload, {
        'type': 'object', 'additionalProperties': False, 'required': ['revision', 'configuration'],
        'properties': {
            'revision': {'type': 'integer', 'minimum': 0},
            'configuration': {
                'type': 'object', 'additionalProperties': False,
                'required': ['enabled', 'service_name', 'service_namespace', 'environment', 'endpoint', 'sample_ratio', 'exclude_health'],
                'properties': {
                    'enabled': {'type': 'boolean'}, 'exclude_health': {'type': 'boolean'},
                    'service_name': {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_.-]{0,79}$'},
                    'service_namespace': {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_.-]{0,79}$'},
                    'environment': {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_.-]{0,39}$'},
                    'sample_ratio': {'type': 'number', 'minimum': 0, 'maximum': 1},
                    'endpoint': {'type': 'string', 'pattern': r'^http://(?:localhost|127\.0\.0\.1|\[::1\]):[0-9]{1,5}/v1/traces$'},
                },
            },
        },
    })
    port = int(payload['configuration']['endpoint'].rsplit(':', 1)[1].split('/')[0])

    if not math.isfinite(payload['configuration']['sample_ratio']):
        raise ValueError('Sampling ratio must be finite.')

    if not 1 <= port <= 65535:
        raise ValueError('Collector port must be between 1 and 65535.')

    return payload

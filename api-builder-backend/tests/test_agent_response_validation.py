"""Regression coverage for centralized agent validation and configuration boundaries."""

from importlib import import_module
import json
from pathlib import Path

import pytest
from jsonschema import SchemaError, ValidationError
from pydantic import ValidationError as SettingsValidationError

AGENT_DIR = Path(__file__).resolve().parents[2] / "builder-agents" / "entity-builder"


def test_agent_validation_boundaries(tmp_path, monkeypatch) -> None:
    """Reject malformed input before consumption and preserve valid settings/assets."""
    monkeypatch.syspath_prepend(str(AGENT_DIR))
    monkeypatch.syspath_prepend(str(AGENT_DIR.parent))

    for key in ("AGENT_CONFIG", "AGENT_MODEL", "AGENT_RECURSION_LIMIT"):
        monkeypatch.delenv(key, raising=False)

    validator = import_module("shared.agent_response_validator")
    configuration = import_module("shared.configuration")
    transport = import_module("runtime.codex_model")
    schema = import_module("runtime.registry").AGENTS["entity-builder"].load_schema()
    payload = {"content": "Done", "tool_calls": []}

    assert validator.validate_agent_response(payload, transport.ENVELOPE_SCHEMA) is payload

    for invalid in (None, [], {}, {"content": "Done", "tool_calls": "invalid"}):
        with pytest.raises(ValidationError):
            validator.validate_agent_response(invalid, transport.ENVELOPE_SCHEMA)

    path = tmp_path / "agent-config.json"

    for invalid in (None, [], "config", {"tools": ["lookup", "lookup"]}):
        path.write_text(json.dumps(invalid))

        with pytest.raises(ValidationError):
            configuration.load_agent_settings(path)

    for invalid in ({"recursion_limit": 1}, {"planning": "yes"}, {"output_schema_file": "old.json"}):
        path.write_text(json.dumps(invalid))

        with pytest.raises(SettingsValidationError):
            configuration.load_agent_settings(path)

    path.write_text("{}")

    assert configuration.load_agent_settings(path).name == "builder-agent"

    monkeypatch.setenv("SECOND_AGENT_MODEL", "second-model")
    monkeypatch.setenv("ENTITY_AGENT_MODEL", "unrelated-model")
    second = configuration.load_agent_settings(
        path, {"name": "second-agent"}, "SECOND_AGENT",
    )

    assert second.name == "second-agent"
    assert second.model_name == "second-model"
    overridden = configuration.load_agent_settings(path, {"model_name": "explicit"}, "SECOND_AGENT")

    assert overridden.model_name == "explicit"

    with pytest.raises(ValidationError):
        validator.validate_agent_assets(" \n ", schema)

    for invalid in ([], {**schema, "type": "array"}, {**schema, "title": " "}, {**schema, "description": None}):
        with pytest.raises(ValidationError):
            validator.validate_agent_assets("Prompt", invalid)

    with pytest.raises(SchemaError):
        validator.validate_agent_assets("Prompt", {**schema, "properties": {"bad": {"type": "invalid"}}})

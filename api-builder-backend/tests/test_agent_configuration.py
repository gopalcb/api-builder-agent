"""One end-to-end configuration, harness, tool and Codex-adapter workflow."""

from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from langchain_core.tools import tool

AGENT_DIR = Path(__file__).resolve().parents[2] / "builder-agents" / "entity-builder"


def test_agent_builder_end_to_end(tmp_path, monkeypatch) -> None:
    """Load overrides, build the real graph, execute a tool and return structured output."""
    monkeypatch.syspath_prepend(str(AGENT_DIR))
    monkeypatch.syspath_prepend(str(AGENT_DIR.parent))

    for key in ("ENTITY_AGENT_CONFIG", "ENTITY_AGENT_MODEL", "ENTITY_AGENT_RECURSION_LIMIT"):
        monkeypatch.delenv(key, raising=False)

    configuration = import_module("shared.configuration")
    builder = import_module("shared.agent_builder")
    transport = import_module("runtime.codex_model")
    schema = {
        "title": "Summary", "description": "An entity summary", "type": "object",
        "properties": {"summary": {"type": "string"}}, "required": ["summary"],
        "additionalProperties": False,
    }
    path = tmp_path / "agent-config.json"
    path.write_text(json.dumps({"model_name": "file-model", "tools": ["lookup"], "planning": False}))
    monkeypatch.setenv("ENTITY_AGENT_CONFIG", str(path))
    monkeypatch.setenv("ENTITY_AGENT_MODEL", "environment-model")
    settings = configuration.load_agent_settings(
        path,
        overrides={"recursion_limit": 18}, env_prefix="ENTITY_AGENT",
    )

    assert settings.model_name == "environment-model", "Environment override was ignored"
    assert settings.recursion_limit == 18

    executed = []

    @tool
    def lookup_entity(entity_id: int) -> str:
        """Read an entity name from the application catalog."""
        executed.append(entity_id)

        return "Order"

    # Mock only the external SDK: configuration, adapter, harness and tool are real.
    thread = MagicMock()
    thread.run.side_effect = [
        SimpleNamespace(error=None, final_response=json.dumps({
            "content": "", "tool_calls": [{"name": "lookup_entity", "arguments_json": '{"entity_id": 7}'}],
        })),
        SimpleNamespace(error=None, final_response=json.dumps({
            "content": "", "tool_calls": [{"name": "Summary", "arguments_json": '{"summary": "Order"}'}],
        })),
    ]
    codex = MagicMock()
    codex.__enter__.return_value = codex
    codex.thread_start.return_value = thread
    factory = MagicMock(return_value=codex)
    monkeypatch.setattr(transport, "Codex", factory)
    factory_builder = builder.AgentBuilder(
        transport.CodexChatModel(model_name=settings.model_name), {"lookup": lookup_entity},
    )
    graph = factory_builder.build(settings, "Look up the entity, then submit Summary.", schema)
    second_graph = factory_builder.build(settings, "Summarize another entity.", schema)

    assert second_graph is not graph

    assert graph.config["recursion_limit"] == 18

    result = graph.invoke({"messages": [{"role": "user", "content": "Look up entity 7"}]})

    assert result["structured_response"] == {"summary": "Order"}, "Structured result was not returned"
    assert executed == [7] and thread.run.call_count == 2, "Harness did not execute the tool round trip"

    start = codex.thread_start.call_args.kwargs

    assert start["model"] == "environment-model" and start["sandbox"] == transport.Sandbox.read_only
    assert 'forced_login_method="chatgpt"' in factory.call_args.kwargs["config"].config_overrides

    forwarded = json.loads(thread.run.call_args.args[0].content)

    assert any(message["type"] == "tool" and message["data"]["content"] == "Order" for message in forwarded["messages"]), "Tool result was not forwarded to Codex"

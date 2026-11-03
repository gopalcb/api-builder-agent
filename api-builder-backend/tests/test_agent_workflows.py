"""Exercise composed workflows through the real harness and shared CLI."""

from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from jsonschema import ValidationError

from runtime.agent_runtime import AgentRuntime
from runtime import codex_model, runner
from runtime.registry import AGENTS, AgentRegistration
from shared.agent_builder import AgentBuilder
from shared.configuration import AgentSettings
from workflows.prompt_chain import PromptChain

ROOT = Path(__file__).resolve().parents[2]


def test_entity_chain_through_codex_adapter(monkeypatch) -> None:
    """Draft/review preserves context, isolates requests and stops on invalid drafts."""
    registration = AGENTS["entity-builder"]
    workflow = registration.create_workflow()
    draft = {"entity_id": 7, "attributes": [], "relationships": []}
    reviewed = {**draft, "attributes": [
        {"name": "total", "data_type": "decimal", "nullable": False, "description": "Total"},
    ]}
    other = {"entity_id": 8, "attributes": [], "relationships": []}
    outputs = [draft, reviewed, other, other, {"entity_id": "invalid"}]
    thread = MagicMock()
    thread.run.side_effect = [
        SimpleNamespace(error=None, final_response=json.dumps({
            "content": "", "tool_calls": [{
                "name": "EntityDefinition", "arguments_json": json.dumps(output),
            }],
        })) for output in outputs
    ]
    codex = MagicMock()
    codex.__enter__.return_value = codex
    codex.thread_start.return_value = thread
    factory = MagicMock(return_value=codex)
    monkeypatch.setattr(codex_model, "Codex", factory)
    runtime = AgentRuntime(
        AgentBuilder(codex_model.CodexChatModel()), AgentSettings(planning=False), registration.load_schema(),
    )
    context = {"entity_id": 7, "prompt": "Add total", "entity": {}, "existing_entities": []}
    original = deepcopy(context)

    assert workflow.run(context, runtime) == reviewed
    assert context == original

    request = json.loads(thread.run.call_args_list[1].args[0].content)
    human = next(message for message in request["messages"] if message["type"] == "human")

    assert json.loads(human["data"]["content"]) == {"context": context, "draft": draft}
    assert workflow.run({**context, "entity_id": 8}, runtime) == other

    fresh_request = json.loads(thread.run.call_args_list[2].args[0].content)
    fresh_humans = [message for message in fresh_request["messages"] if message["type"] == "human"]

    assert len(fresh_humans) == 1
    assert json.loads(fresh_humans[0]["data"]["content"])["entity_id"] == 8

    with pytest.raises(ValidationError):
        workflow.run(context, runtime)

    assert thread.run.call_count == 5, "An invalid draft must not start review"


def test_plugin_registration_and_intermediate_schema(tmp_path) -> None:
    """A two-file plugin composes a one-step workflow with an injected runtime."""
    (tmp_path / "output-schema.py").write_text('OUTPUT_SCHEMA = {"type": "object"}\n')
    (tmp_path / "agent.py").write_text('''from workflows.prompt_chain import PromptChain

def summarize(context, previous, runtime):
    return runtime.run("Summarize the input.", context)

def create_workflow():
    return PromptChain(summarize)
''')
    plugin = AgentRegistration(tmp_path)
    fake_runtime = MagicMock()
    fake_runtime.run.return_value = {"summary": "Ready"}

    assert plugin.load_schema() == {"type": "object"}
    assert plugin.create_workflow().run({"text": "Ready"}, fake_runtime) == {"summary": "Ready"}
    fake_runtime.run.assert_called_once_with("Summarize the input.", {"text": "Ready"})

    schema = {"title": "Summary", "description": "Summary", "type": "object",
              "properties": {"summary": {"type": "string"}}, "required": ["summary"]}
    builder = MagicMock()
    builder.build.return_value.invoke.return_value = {"structured_response": {"summary": "Ready"}}
    runtime = AgentRuntime(builder, AgentSettings(), plugin.load_schema())

    assert runtime.run("Summarize.", {}, schema) == {"summary": "Ready"}
    assert builder.build.call_args.args[2] == schema

    builder.build.return_value.invoke.return_value = {"structured_response": {"summary": False}}

    with pytest.raises(ValidationError):
        runtime.run("Summarize.", {}, schema)


def test_chain_protects_original_input() -> None:
    """A step's local changes cannot mutate caller context or the next step's input."""
    context = {"items": ["original"]}

    def first_step(context: dict, previous: dict | None, runtime: object) -> dict:
        """Mutate local context to exercise the workflow isolation boundary."""
        context["items"].append("local")

        return {"draft": "ready"}

    def second_step(context: dict, previous: dict, runtime: object) -> dict:
        """Verify original input and the explicit previous result are available."""
        assert context == {"items": ["original"]}
        assert previous == {"draft": "ready"}

        return previous

    workflow = PromptChain(first_step, second_step)

    assert workflow.run(context, None) == {"draft": "ready"}
    assert context == {"items": ["original"]}


def test_shared_worker_cli(tmp_path, monkeypatch, capsys) -> None:
    """CLI dispatches a registered workflow and rejects unknown agents/config safely."""
    fake_runtime = MagicMock()
    fake_runtime.run.side_effect = [
        {"entity_id": 7, "attributes": [], "relationships": []},
        {"entity_id": 7, "attributes": [], "relationships": []},
    ]
    monkeypatch.setattr(runner, "AgentRuntime", MagicMock(return_value=fake_runtime))
    monkeypatch.setattr(sys, "argv", ["runner.py", "entity-builder"])
    monkeypatch.setattr(sys, "stdin", StringIO('{"entity_id": 7}'))

    for key in ("ENTITY_AGENT_CONFIG", "ENTITY_AGENT_MODEL", "ENTITY_AGENT_RECURSION_LIMIT"):
        monkeypatch.delenv(key, raising=False)

    assert runner.main() == 0
    assert json.loads(capsys.readouterr().out)["entity_id"] == 7
    assert fake_runtime.run.call_count == 2

    worker = ROOT / "runtime" / "runner.py"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]")
    result = subprocess.run(
        [sys.executable, str(worker), "entity-builder"], input="{}", text=True,
        capture_output=True, cwd=tmp_path, env={**os.environ, "ENTITY_AGENT_CONFIG": str(invalid)},
    )

    assert result.returncode == 1 and not result.stdout
    assert "Agent generation failed." in result.stderr and "Traceback" not in result.stderr

    unknown = subprocess.run(
        [sys.executable, str(worker), "../untrusted"], input="{}", text=True,
        capture_output=True, cwd=tmp_path,
    )

    assert unknown.returncode == 2 and "invalid choice" in unknown.stderr

"""Run a registered agent workflow using the common stdin/stdout worker contract."""

import argparse
import json
from pathlib import Path
import sys

# Support direct script execution from backend workers and arbitrary directories.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import SchemaError, ValidationError
from langchain.agents.structured_output import StructuredOutputError
from langgraph.errors import GraphRecursionError
from openai_codex import CodexError

from runtime.agent_runtime import AgentRuntime
from runtime.codex_model import CodexChatModel
from runtime.registry import AGENTS
from shared.agent_builder import AgentBuilder
from shared.configuration import load_agent_settings
from shared.logging_service import configure_worker, LogStep, log_event


def main() -> int:
    """Resolve a registered workflow, run it and emit JSON or a safe error."""
    configure_worker()
    parser = argparse.ArgumentParser(description="Run a registered builder agent.")
    parser.add_argument("agent", choices=AGENTS)
    args = parser.parse_args()

    try:
        registration = AGENTS[args.agent]
        settings = load_agent_settings(registration.config_path, env_prefix=registration.env_prefix)
        builder = AgentBuilder(CodexChatModel(model_name=settings.model_name))
        runtime = AgentRuntime(builder, settings, registration.load_schema())
        workflow = registration.create_workflow()
        with LogStep('runner.workflow', agent=args.agent):
            result = workflow.run(json.load(sys.stdin), runtime)
    except (CodexError, ValueError, ValidationError, SchemaError, OSError, GraphRecursionError, StructuredOutputError) as error:
        log_event('agent.failed', 40, agent=args.agent, error_type=type(error).__name__)
        print("Agent generation failed. Check configuration, Codex sign-in and runtime.", file=sys.stderr)

        return 1

    print(json.dumps(result))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

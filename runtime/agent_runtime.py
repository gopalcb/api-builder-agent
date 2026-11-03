"""Invoke one prompt step through an injected builder and validate its result."""

import json

from shared.agent_builder import AgentBuilder
from shared.agent_response_validator import validate_agent_response
from shared.configuration import AgentSettings

from shared.logging_service import log_function, log_event, LogStep


class AgentRuntime:
    """Hold a workflow's dependencies without retaining request messages or results."""

    def __init__(self, builder: AgentBuilder, settings: AgentSettings, output_schema: dict) -> None:
        """Bind construction dependencies and the agent's default output contract."""
        self.builder = builder
        self.settings = settings
        self.output_schema = output_schema

    @log_function
    def run(self, prompt: str, context: dict, schema: dict | None = None) -> dict:
        """Run a fresh graph; optional schemas allow different intermediate results."""
        output_schema = self.output_schema if schema is None else schema
        graph = self.builder.build(self.settings, prompt, output_schema)
        result = graph.invoke({"messages": [{"role": "user", "content": json.dumps(context)}]})

        return validate_agent_response(result.get("structured_response"), output_schema)

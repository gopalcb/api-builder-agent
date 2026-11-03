"""Build fresh Deep Agents graphs with injected model and application tools."""

from copy import deepcopy

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware import TodoListMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from shared.configuration import AgentSettings
from shared.agent_response_validator import validate_agent_assets, validate_agent_tools

from shared.logging_service import log_function, log_event, LogStep


class AgentBuilder:
    """Reuse construction dependencies while isolating each graph's state."""

    def __init__(self, model: BaseChatModel, tool_registry: dict | None = None) -> None:
        """Inject a compatible chat model and already-constructed application tools."""
        self.model = model
        self.tool_registry = dict(tool_registry or {})

    @log_function
    def build(self, settings: AgentSettings, prompt: str, schema: dict) -> CompiledStateGraph:
        """Create one bounded graph with fresh middleware and in-memory storage."""
        validate_agent_assets(prompt, schema)
        tools = validate_agent_tools(settings.tools, self.tool_registry, schema["title"])
        middleware = [TodoListMiddleware()] if settings.planning else []
        harness = create_deep_agent(
            name=settings.name,
            model=self.model,
            system_prompt=prompt,
            tools=tools,
            backend=StateBackend(),
            middleware=middleware,
            response_format=ToolStrategy(schema=deepcopy(schema), handle_errors=False),
        )

        return harness.with_config(recursion_limit=settings.recursion_limit, run_name=settings.name)

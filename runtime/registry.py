"""Load only explicitly registered, trusted local agent code and schemas."""

from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

from shared.logging_service import log_function, log_event, LogStep

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AgentRegistration:
    """Locate an agent and its optional deployment settings without importing it."""

    directory: Path
    config_path: Path | None = None
    env_prefix: str = "AGENT"

    @log_function
    def load_schema(self) -> dict:
        """Read the trusted Python output contract shared by runner and backend."""
        return run_path(str(self.directory / "output-schema.py"))["OUTPUT_SCHEMA"]

    @log_function
    def create_workflow(self) -> object:
        """Load prompt functions and call the agent's workflow factory."""
        module = run_path(str(self.directory / "agent.py"))

        return module["create_workflow"]()


AGENTS = {
    "api-implementation-builder": AgentRegistration(
        ROOT / "builder-agents" / "api-implementation-builder",
        ROOT / ".codex" / "config" / "agents" / "api-implementation-builder.json",
        "API_IMPLEMENTATION_AGENT",
    ),
    "infrastructure-builder": AgentRegistration(
        ROOT / "builder-agents" / "infrastructure-builder", env_prefix="INFRASTRUCTURE_AGENT",
    ),
    "rbac-builder": AgentRegistration(
        ROOT / "builder-agents" / "rbac-builder",
        ROOT / ".codex" / "config" / "agents" / "rbac-builder.json",
        "RBAC_AGENT",
    ),
    "search-builder": AgentRegistration(
        ROOT / "builder-agents" / "search-builder", env_prefix="SEARCH_AGENT",
    ),
    "entity-builder": AgentRegistration(
        ROOT / "builder-agents" / "entity-builder",
        ROOT / ".codex" / "config" / "agents" / "entity-builder.json",
        "ENTITY_AGENT",
    ),
}

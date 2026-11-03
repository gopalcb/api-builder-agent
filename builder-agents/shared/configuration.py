"""Resolve deployment settings once; prompts and schemas stay in agent code."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from shared.agent_response_validator import validate_agent_response

from shared.logging_service import log_function, log_event, LogStep


class AgentSettings(BaseModel):
    """Immutable construction settings shared by all prompt steps."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: StrictStr = Field(default="builder-agent", min_length=1, max_length=100)
    model_name: StrictStr | None = Field(default=None, min_length=1)
    planning: StrictBool = True
    recursion_limit: StrictInt = Field(default=20, ge=2, le=100)
    tools: tuple[StrictStr, ...] = ()


@log_function
def load_agent_settings(
    path: str | Path | None = None, overrides: dict | None = None, env_prefix: str = "AGENT",
) -> AgentSettings:
    """Apply defaults < optional JSON < environment < explicit overrides."""
    config_path = os.environ.get(f"{env_prefix}_CONFIG") or path
    payload = validate_agent_response(
        json.loads(Path(config_path).read_text()) if config_path else {}, {"type": "object"},
    )

    if f"{env_prefix}_MODEL" in os.environ:
        payload["model_name"] = os.environ[f"{env_prefix}_MODEL"].strip() or None

    if f"{env_prefix}_RECURSION_LIMIT" in os.environ and "recursion_limit" not in (overrides or {}):
        payload["recursion_limit"] = int(os.environ[f"{env_prefix}_RECURSION_LIMIT"])

    if overrides is not None:
        payload.update(overrides)

    settings = AgentSettings.model_validate(payload)
    validate_agent_response(list(settings.tools), {"uniqueItems": True})

    return settings

"""Run prompt functions in order, retaining original input for every step."""

from collections.abc import Callable
from copy import deepcopy

from runtime.agent_runtime import AgentRuntime

from shared.logging_service import log_function, log_event, LogStep


class PromptChain:
    """Compose one or more functions accepting context, previous result and runtime."""

    def __init__(self, first_step: Callable, *next_steps: Callable) -> None:
        """Require a first step so an empty workflow cannot succeed accidentally."""
        self.steps = (first_step, *next_steps)

    @log_function
    def run(self, context: dict, runtime: AgentRuntime) -> dict:
        """Stop on errors; keep inputs and per-request results isolated."""
        result = None

        for step in self.steps:
            with LogStep('workflow.step', step=step.__name__):
                result = step(deepcopy(context), deepcopy(result), runtime)

        return result

"""Execute registered agent workers with a deadline and process-group cleanup."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from runtime.registry import AGENTS

from shared.logging_service import log_function, log_event, worker_environment

WORKFLOW_START_DELAY_SECONDS = 30


@log_function
def run_agent_worker(agent: str, context: dict, timeout: int) -> dict:
    """Delay, then return the runner's validated output and clean up timeouts."""
    if agent not in AGENTS:
        raise ValueError("Unknown agent")

    time.sleep(WORKFLOW_START_DELAY_SECONDS)
    log_event('agent.worker.started', agent=agent, timeout_seconds=timeout)
    runner = Path(__file__).with_name("runner.py")

    with subprocess.Popen(
        [sys.executable, str(runner), agent], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, env=worker_environment(),
    ) as process:
        try:
            output, _ = process.communicate(json.dumps(context), timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise

        log_event('agent.worker.exited', agent=agent, returncode=process.returncode)

        if process.returncode:
            raise RuntimeError("Agent generation failed; check local Codex sign-in and runtime.")

    return json.loads(output)

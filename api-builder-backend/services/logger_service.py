"""Expose the shared application logger to backend services and HTTP entrypoints."""

import runtime
from shared.logging_service import (
    LogStep, configure_logging, install_request_logging, log_event, log_function, worker_environment,
)

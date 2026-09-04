"""Somewhere for this module to speak: uvicorn configures its own loggers and leaves the root alone,
so every `log.info` here went nowhere until this was called. Deliberately a copy of market-data's."""

from __future__ import annotations

import logging
import os
import sys

# Libraries whose INFO is traffic rather than information: `httpx` narrates every request, which at ten a second
# is the whole log, and `websockets` narrates frames. `azure` is the exporter logging each upload — a line that is
# telemetry, uploaded, logged: 1.3 million of them in two weeks. Their warnings still come through.
NOISY_LOGGERS = ("azure", "httpx", "httpcore", "websockets")

# The instrumentation records every WebSocket frame `/ws/stream` sends as a dependency — 8.8 million rows, 84% of
# the workspace's ingest, measured 4 September 2026. Read once, when the FastAPI instrumentor is first imported.
EXCLUDED_URLS_SETTING = "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS"
UNTRACED_PATHS = "/ws/stream"


def configure() -> None:
    """Wire up logging, and Application Insights when there is one. Called at import time in `app.py`
    before `from fastapi import FastAPI`: the instrumentation patches the class attribute."""
    configure_logging()
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        # Every local run: without a connection string there is nothing to export to, and
        # stdout is what a developer is reading anyway.
        return
    os.environ.setdefault(EXCLUDED_URLS_SETTING, UNTRACED_PATHS)
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()


def configure_logging() -> None:
    """Give the root logger a level and somewhere to write. `basicConfig` is a no-op once a handler
    exists, which is wanted: a caller that configured logging itself keeps its own."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

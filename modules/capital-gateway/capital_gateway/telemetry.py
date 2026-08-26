"""Somewhere for this module to speak: uvicorn configures its own loggers and leaves the root alone,
so every `log.info` here went nowhere until this was called. Deliberately a copy of market-data's."""

from __future__ import annotations

import logging
import os
import sys

# Libraries whose INFO is traffic rather than information. `httpx` narrates every request
# this module makes, which at ten a second is the whole log; `websockets` narrates frames.
# Their warnings still come through, which is the part worth hearing.
NOISY_LOGGERS = ("httpx", "httpcore", "websockets", "azure.core.pipeline.policies.http_logging_policy")


def configure() -> None:
    """Wire up logging, and Application Insights when there is one. Called at import time in `app.py`
    before `from fastapi import FastAPI`: the instrumentation patches the class attribute."""
    configure_logging()
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        # Every local run: without a connection string there is nothing to export to, and
        # stdout is what a developer is reading anyway.
        return
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

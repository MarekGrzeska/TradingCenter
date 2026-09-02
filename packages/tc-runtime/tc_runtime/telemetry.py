"""Logging and Application Insights, wired the same way in every module that has either.

Called at import time in a module's `app.py`, before `from fastapi import FastAPI`: the Azure
instrumentation patches the class attribute, so a FastAPI imported first is a FastAPI not
instrumented. That ordering is the whole reason this is a function and not a lifespan step.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence

# The one logger every module here wants quiet, and not merely for volume: the exporter logs each
# upload, and that line is telemetry, uploaded, logged. 165 entries in fifteen quiet minutes.
ALWAYS_QUIET = ("azure",)

# Deliberately *not* a default. `httpx` at INFO is noise in four modules and evidence in the fifth:
# telegram-gateway's redaction filter exists to take the bot token out of exactly that line, and a
# package that silenced it would have removed the thing under test. Each module names its own.


def configure(*, quiet: Sequence[str] = ()) -> None:
    """Logging always; Application Insights only where there is a connection string. Its absence is
    every local run, and exporting to nowhere is not an error state."""
    configure_logging(quiet=quiet)
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()


def configure_logging(*, quiet: Sequence[str] = ()) -> None:
    """Give the root logger a level and somewhere to write, because nothing else does. A deployed
    container printed uvicorn's lines and none of its module's — not silent, just never told where."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for name in (*ALWAYS_QUIET, *quiet):
        logging.getLogger(name).setLevel(logging.WARNING)

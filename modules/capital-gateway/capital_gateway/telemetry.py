"""Somewhere for this module to speak, because nothing else gives it one.

Uvicorn configures its own three loggers and leaves the root alone. The root's default
level is WARNING and it has no handler, so every `log.info` this module writes — a room
opening, a boundary read, a reconnect, a subscription refused — went nowhere at all, and
warnings reached stderr only through logging's last-resort handler, unformatted and
untimestamped.

What that cost, measured on 10 August: an hour spent diagnosing a stalled feed by reading
the *archive's* database, because the module that actually talks to the provider had no
record of what it had done. Application Insights held 314 entries from `market-data` over
the same window and not one from here — the connection string was configured on this app
all along, and nobody had called the line that uses it.

Deliberately not shared with `market-data`, which has the same twenty lines. There is no
library between modules and there is not going to be one (`docs/architecture.md`, "Why no
shared library"); two copies of a logging setup is the price, and it is smaller than the
coupling.
"""

from __future__ import annotations

import logging
import os
import sys

# Libraries whose INFO is traffic rather than information. `httpx` narrates every request
# this module makes, which at ten a second is the whole log; `websockets` narrates frames.
# Their warnings still come through, which is the part worth hearing.
NOISY_LOGGERS = ("httpx", "httpcore", "websockets", "azure.core.pipeline.policies.http_logging_policy")


def configure() -> None:
    """Wire up logging, and Application Insights when there is one to wire to.

    Called once, at import time in `app.py`, before `from fastapi import FastAPI` — not
    merely before `FastAPI(...)` is called, and not from `lifespan`.
    `configure_azure_monitor()`'s FastAPI auto-instrumentation patches the `fastapi.FastAPI`
    class *attribute*; a `from fastapi import FastAPI` that already ran binds a name to
    whatever the attribute held at that moment, and no later call repoints it. Ordering
    matters for logging too: the root logger needs its level before Azure Monitor attaches a
    handler to it, because that handler is gated by the same level — configured after, an
    `INFO` line reaches stdout and still never reaches Application Insights.
    """
    configure_logging()
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        # Every local run. Not a special case worth branching further on: without a
        # connection string there is nothing to export to, and stdout is what a developer
        # is reading anyway.
        return
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()


def configure_logging() -> None:
    """Give the root logger a level and somewhere to write.

    `LOG_LEVEL` overrides, for turning the volume down without a deploy. `basicConfig` is
    a no-op when the root logger already has a handler, which is the behaviour wanted: a
    caller that configured logging itself keeps its own configuration, and a test that
    captures logs is not fought over.
    """
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

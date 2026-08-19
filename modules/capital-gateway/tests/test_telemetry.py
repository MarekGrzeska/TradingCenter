"""Logging setup in isolation — no Azure, no exporter, no socket."""

from __future__ import annotations

import logging

import pytest

from capital_gateway import telemetry


@pytest.fixture(autouse=True)
def _root_logger_restored():
    """`basicConfig` mutates the root logger, which every other test shares."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    levels = {name: logging.getLogger(name).level for name in telemetry.NOISY_LOGGERS}
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    for name, restored in levels.items():
        logging.getLogger(name).setLevel(restored)


def test_this_module_gets_somewhere_to_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """The defect: uvicorn configures its own loggers and leaves the root alone, so every
    line this module wrote about a room, a boundary or a refused subscription went
    nowhere — and an hour was spent diagnosing a stalled feed from another module's
    database."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging.getLogger().handlers.clear()

    telemetry.configure_logging()

    root = logging.getLogger()
    assert root.handlers, "the root logger still has nowhere to write"
    assert root.level == logging.INFO
    assert logging.getLogger("capital_gateway.stream.hub").isEnabledFor(logging.INFO)


def test_no_connection_string_means_no_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every local run. `configure` must still set logging up and must not reach for
    Azure — importing the exporter without one is a slow failure at startup."""
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging.getLogger().handlers.clear()
    reached = False

    def _explode() -> None:
        nonlocal reached
        reached = True

    monkeypatch.setattr(telemetry, "configure_logging", lambda: _explode())

    telemetry.configure()

    assert reached, "logging must be configured with or without Application Insights"

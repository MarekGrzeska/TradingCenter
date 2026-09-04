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
    """The defect: uvicorn configures its own loggers and leaves the root alone, so every line this module
    wrote went nowhere — and an hour was spent diagnosing a stalled feed from another module's database."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging.getLogger().handlers.clear()

    telemetry.configure_logging()

    root = logging.getLogger()
    assert root.handlers, "the root logger still has nowhere to write"
    assert root.level == logging.INFO
    assert logging.getLogger("capital_gateway.stream.hub").isEnabledFor(logging.INFO)


def test_the_exporter_does_not_log_its_own_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The defect: the exporter says "Transmission succeeded" at INFO, that line is exported, and the
    loop was 1.3 million rows in two weeks — a tenth of everything the workspace billed."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging.getLogger().handlers.clear()

    telemetry.configure_logging()

    assert not logging.getLogger("azure.monitor.opentelemetry.exporter").isEnabledFor(logging.INFO)


def test_the_stream_is_kept_out_of_the_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every frame `/ws/stream` sends was one dependency row — 84% of the workspace's ingest. The
    instrumentor reads its exclusions once, from the environment, so they must be there before it is."""
    import os
    import sys
    import types

    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test")
    monkeypatch.delenv(telemetry.EXCLUDED_URLS_SETTING, raising=False)
    seen: dict[str, str | None] = {}
    stub = types.ModuleType("azure.monitor.opentelemetry")
    stub.configure_azure_monitor = lambda: seen.update(  # type: ignore[attr-defined]
        excluded=os.environ.get(telemetry.EXCLUDED_URLS_SETTING)
    )
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", stub)
    monkeypatch.setattr(telemetry, "configure_logging", lambda: None)

    telemetry.configure()

    assert seen["excluded"] == "/ws/stream"


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

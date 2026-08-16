"""specs/trading-mcp-transport, "Moduł wystawia jeden transport i jest nim transport
sieciowy" — there is no `stdio` choice to make, unlike market-mcp's `__main__.py`."""

from __future__ import annotations

import inspect

from trading_mcp import __main__ as entrypoint


def test_the_entrypoint_takes_no_transport_argument() -> None:
    signature = inspect.signature(entrypoint.main)
    assert not signature.parameters


def test_the_entrypoint_never_runs_the_stdio_transport() -> None:
    source = inspect.getsource(entrypoint)
    assert "run_stdio_async" not in source
    assert "argparse" not in source

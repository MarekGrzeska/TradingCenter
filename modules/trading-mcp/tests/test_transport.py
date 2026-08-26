"""specs/trading-mcp-transport, "Moduł wystawia jeden transport i jest nim transport
sieciowy" — there is no `stdio` choice to make, unlike market-mcp's `__main__.py`."""

from __future__ import annotations

import inspect

import httpx
import pytest
import respx
import uvicorn

from trading_mcp import __main__ as entrypoint
from trading_mcp.errors import GatewayUnavailable, NotDemoEnvironment

BASE = "http://127.0.0.1:8010"


def test_the_entrypoint_takes_no_transport_argument() -> None:
    signature = inspect.signature(entrypoint.main)
    assert not signature.parameters


def test_the_entrypoint_never_runs_the_stdio_transport() -> None:
    source = inspect.getsource(entrypoint)
    assert "run_stdio_async" not in source
    assert "argparse" not in source


@respx.mock
async def test_the_process_does_not_listen_when_the_account_is_not_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole guard, now that the re-check in front of every write is gone: a process that never
    opens a port cannot be reached by anything."""
    monkeypatch.setenv("CAPITAL_GATEWAY_URL", BASE)
    monkeypatch.setenv("CAPITAL_GATEWAY_API_KEY", "k")
    respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "live"})
    )

    served = False

    async def _serve_called(self) -> None:
        nonlocal served
        served = True

    monkeypatch.setattr(uvicorn.Server, "serve", _serve_called)

    with pytest.raises(NotDemoEnvironment):
        await entrypoint._serve()

    assert served is False


@respx.mock
async def test_the_process_does_not_listen_when_the_gateway_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CAPITAL_GATEWAY_URL", BASE)
    monkeypatch.setenv("CAPITAL_GATEWAY_API_KEY", "k")
    respx.get(f"{BASE}/capabilities").mock(side_effect=httpx.ConnectError("dropped"))

    served = False

    async def _serve_called(self) -> None:
        nonlocal served
        served = True

    monkeypatch.setattr(uvicorn.Server, "serve", _serve_called)

    with pytest.raises(GatewayUnavailable):
        await entrypoint._serve()

    assert served is False

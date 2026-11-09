"""specs/capital-live-account — the gateway on the live account: when it starts at all, the one account it stands on,
the limits an order must fit, the routes it does not serve, close-all, and the trace every write leaves.

Not to be confused with `test_live.py`, which is the demo API read for real behind `--run-live`."""

from __future__ import annotations

import importlib
import json
import logging
import sys

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from capital_gateway.caller_access import browser_caller_may_reach
from capital_gateway.config import (
    API_KEY_HEADER,
    DEMO_BASE_URL,
    LIVE_BASE_URL,
    Settings,
    environment_of,
)

API = f"{LIVE_BASE_URL}/api/v1"
GATEWAY_KEY = "live-gateway-key"
ACCOUNT = "L1"
KEY = {API_KEY_HEADER: GATEWAY_KEY}

LIVE_ENV = {
    "GATEWAY_ENV": "production",
    "SERVER_MODE": "true",
    "ENTRA_TENANT_ID": "11111111-2222-3333-4444-555555555555",
    "ENTRA_AUDIENCES": "api://tradingcenter-capital-gateway",
    "CAPITAL_ENVIRONMENT": "live",
    "CAPITAL_BASE_URL": LIVE_BASE_URL,
    "LIVE_ACCOUNT_ID": ACCOUNT,
    "LIVE_ORDER_LIMITS": '{"US100": "0.5"}',
}


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPITAL_API_KEY", "super-secret-key")
    monkeypatch.setenv("CAPITAL_IDENTIFIER", "me@example.com")
    monkeypatch.setenv("CAPITAL_PASSWORD", "hunter2")
    monkeypatch.setenv("GATEWAY_API_KEY", GATEWAY_KEY)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in {**LIVE_ENV, **env}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_the_live_settings_build_on_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    assert settings.capital_environment == "live"
    assert str(settings.live_order_limits["US100"]) == "0.5"


@pytest.mark.parametrize(
    ("env", "named"),
    [
        ({"GATEWAY_ENV": ""}, "GATEWAY_ENV"),
        ({"SERVER_MODE": "false"}, "server"),
        ({"CAPITAL_BASE_URL": DEMO_BASE_URL}, LIVE_BASE_URL),
        ({"CAPITAL_BASE_URL": None}, LIVE_BASE_URL),
        ({"LIVE_ACCOUNT_ID": " "}, "LIVE_ACCOUNT_ID"),
        ({"LIVE_ORDER_LIMITS": "{}"}, "LIVE_ORDER_LIMITS"),
        ({"LIVE_ORDER_LIMITS": None}, "LIVE_ORDER_LIMITS"),
        ({"LIVE_ORDER_LIMITS": '{"US100": "0"}'}, "US100"),
        ({"LIVE_ORDER_LIMITS": '{"US100": "-1", "GOLD": "1"}'}, "US100"),
    ],
    ids=[
        "off-production",
        "no-server-mode",
        "demo-host",
        "no-host",
        "no-account",
        "empty-limits",
        "no-limits",
        "zero-size",
        "negative-size",
    ],
)
def test_live_without_what_it_needs_refuses_to_start(monkeypatch, env, named) -> None:
    with pytest.raises(ValidationError) as refused:
        _settings(monkeypatch, **env)
    assert named in str(refused.value)


def test_an_unknown_environment_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as refused:
        _settings(monkeypatch, CAPITAL_ENVIRONMENT="paper")
    assert "demo" in str(refused.value) and "live" in str(refused.value)


def test_environment_is_read_from_the_host() -> None:
    assert environment_of(LIVE_BASE_URL) == "live"
    assert environment_of("https://example.test") == "unknown"


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch):
    for name, value in LIVE_ENV.items():
        monkeypatch.setenv(name, value)
    importlib.import_module("capital_gateway.app")
    module = importlib.reload(sys.modules["capital_gateway.app"])
    with TestClient(module.app) as client:
        yield client
    for name in LIVE_ENV:
        monkeypatch.delenv(name, raising=False)
    importlib.reload(sys.modules["capital_gateway.app"])


def _logged_in() -> None:
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(
            200, headers={"CST": "c", "X-SECURITY-TOKEN": "s"}, json={"currentAccountId": ACCOUNT}
        )
    )
    respx.get(f"{API}/session").mock(return_value=httpx.Response(200, json={"accountId": ACCOUNT}))


def _order(**overrides) -> dict:
    return {"symbol": "US100", "direction": "BUY", "size": 0.5, "order_type": "MARKET", **overrides}


def _filled() -> None:
    respx.post(f"{API}/positions").mock(
        return_value=httpx.Response(200, json={"dealReference": "r1"})
    )
    respx.get(f"{API}/confirms/r1").mock(
        return_value=httpx.Response(
            200,
            json={
                "dealStatus": "ACCEPTED",
                "dealId": "d1",
                "epic": "US100",
                "direction": "BUY",
                "size": 0.5,
            },
        )
    )


@respx.mock
def test_capabilities_name_the_live_environment(live: TestClient) -> None:
    _logged_in()
    body = live.get("/capabilities", headers=KEY).json()
    assert body["environment"] == "live"
    assert body["has_streaming"] is False


@pytest.mark.parametrize(
    ("order", "said"),
    [
        (_order(symbol="GOLD"), "GOLD is not an instrument"),
        (_order(size=0.6), "over the limit of 0.5"),
    ],
    ids=["symbol-not-allowed", "over-the-size"],
)
@respx.mock
def test_an_order_outside_the_limits_never_reaches_the_provider(
    live: TestClient, order, said
) -> None:
    _logged_in()
    route = respx.post(f"{API}/positions")
    response = live.post("/orders", json=order, headers=KEY)
    assert response.status_code == 422
    assert said in response.json()["detail"]
    assert not route.called


@respx.mock
def test_a_pending_order_is_held_to_the_same_limit(live: TestClient) -> None:
    _logged_in()
    route = respx.post(f"{API}/workingorders")
    response = live.post(
        "/orders", json=_order(size=1, order_type="LIMIT", level=20000), headers=KEY
    )
    assert response.status_code == 422
    assert not route.called


@respx.mock
def test_an_order_within_the_limits_is_sent_with_its_own_size(live: TestClient) -> None:
    _logged_in()
    _filled()
    response = live.post("/orders", json=_order(), headers=KEY)
    assert response.status_code == 200
    assert response.json()["status"] == "FILLED"
    assert json.loads(_sent_order().content)["size"] == 0.5


def _sent_order() -> httpx.Request:
    return next(
        call.request for call in respx.calls if call.request.url.path.endswith("/positions")
    )


@respx.mock
def test_closing_is_not_held_to_the_limits(live: TestClient) -> None:
    _logged_in()
    respx.delete(f"{API}/positions/old-gold").mock(
        return_value=httpx.Response(200, json={"dealReference": "r2"})
    )
    respx.get(f"{API}/confirms/r2").mock(
        return_value=httpx.Response(200, json={"dealStatus": "ACCEPTED"})
    )
    assert live.delete("/positions/old-gold", headers=KEY).json()["status"] == "CLOSED"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/instruments/US100/candles"),
        ("GET", "/instruments/US100/history"),
        ("GET", "/instruments"),
        ("GET", "/asset-classes"),
        ("POST", "/accounts/top-up"),
        ("PUT", "/accounts/active"),
    ],
)
@respx.mock
def test_the_market_and_the_balance_are_not_served(
    live: TestClient, method: str, path: str
) -> None:
    response = live.request(method, path, headers=KEY, json={"amount": 1, "account_id": "L2"})
    assert response.status_code == 404
    assert not respx.calls


def test_the_stream_is_not_served(live: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        live.websocket_connect("/ws/stream?symbol=US100", headers=KEY),
    ):
        pass
    assert closed.value.code == 4404


@respx.mock
def test_another_account_is_refused_before_the_provider(live: TestClient) -> None:
    route = respx.post(f"{API}/positions")
    response = live.post("/orders", json=_order(), headers={**KEY, "X-Capital-Account": "L2"})
    assert response.status_code == 400
    assert ACCOUNT in response.json()["detail"]
    assert not route.called


@respx.mock
def test_the_accounts_list_is_the_one_account_this_process_trades(live: TestClient) -> None:
    _logged_in()
    accounts = [{"accountId": ACCOUNT, "accountName": "USD"}, {"accountId": "L2", "accountName": "PLN"}]
    respx.get(f"{API}/accounts").mock(return_value=httpx.Response(200, json={"accounts": accounts}))
    assert [a["id"] for a in live.get("/accounts", headers=KEY).json()] == [ACCOUNT]


@respx.mock
def test_close_all_names_the_outcome_of_each(live: TestClient) -> None:
    _logged_in()
    positions = [
        {
            "position": {"dealId": "p1", "direction": "BUY", "size": 0.1},
            "market": {"epic": "US100"},
        },
        {
            "position": {"dealId": "p2", "direction": "SELL", "size": 0.1},
            "market": {"epic": "US100"},
        },
    ]
    respx.get(f"{API}/positions").mock(
        return_value=httpx.Response(200, json={"positions": positions})
    )
    respx.delete(f"{API}/positions/p1").mock(
        return_value=httpx.Response(200, json={"dealReference": "c1"})
    )
    respx.get(f"{API}/confirms/c1").mock(
        return_value=httpx.Response(200, json={"dealStatus": "ACCEPTED"})
    )
    respx.delete(f"{API}/positions/p2").mock(
        return_value=httpx.Response(400, json={"errorCode": "error.market.closed"})
    )
    orders = [
        {
            "workingOrderData": {
                "dealId": "w1",
                "epic": "US100",
                "direction": "BUY",
                "orderSize": 0.1,
                "orderType": "LIMIT",
                "orderLevel": 20000,
            }
        }
    ]
    respx.get(f"{API}/workingorders").mock(
        return_value=httpx.Response(200, json={"workingOrders": orders})
    )
    respx.delete(f"{API}/workingorders/w1").mock(
        return_value=httpx.Response(200, json={"dealReference": "c3"})
    )
    respx.get(f"{API}/confirms/c3").mock(
        return_value=httpx.Response(200, json={"dealStatus": "ACCEPTED"})
    )

    items = live.post("/positions/close-all", headers=KEY).json()["items"]

    # Orders first: one filling after the positions closed would open a position nothing closes.
    assert [(i["id"], i["status"]) for i in items] == [
        ("w1", "CANCELLED"),
        ("p1", "CLOSED"),
        ("p2", "REJECTED"),
    ]
    assert "error.market.closed" in items[2]["reason"]


@respx.mock
def test_close_all_that_fails_half_way_still_traces_what_it_did(
    live: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    _logged_in()
    order = {"dealId": "w1", "epic": "US100", "direction": "BUY", "orderSize": 0.1, "orderType": "LIMIT", "orderLevel": 1}
    respx.get(f"{API}/workingorders").mock(
        return_value=httpx.Response(200, json={"workingOrders": [{"workingOrderData": order}]})
    )
    respx.delete(f"{API}/workingorders/w1").mock(return_value=httpx.Response(200, json={"dealReference": "c3"}))
    respx.get(f"{API}/confirms/c3").mock(return_value=httpx.Response(200, json={"dealStatus": "ACCEPTED"}))
    respx.get(f"{API}/positions").mock(side_effect=httpx.ConnectTimeout("no answer"))

    with caplog.at_level(logging.INFO, logger="capital_gateway.live_trace"), pytest.raises(httpx.ConnectTimeout):
        live.post("/positions/close-all", headers=KEY)

    lines = [r.getMessage() for r in caplog.records if r.name == "capital_gateway.live_trace"]
    assert any("working_order w1" in line and "CANCELLED" in line for line in lines)
    assert any("stopped" in line for line in lines)


@respx.mock
def test_close_all_on_an_empty_account_succeeds_with_nothing(live: TestClient) -> None:
    _logged_in()
    respx.get(f"{API}/positions").mock(return_value=httpx.Response(200, json={"positions": []}))
    respx.get(f"{API}/workingorders").mock(
        return_value=httpx.Response(200, json={"workingOrders": []})
    )
    response = live.post("/positions/close-all", headers=KEY)
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_close_all_does_not_exist_on_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    from capital_gateway.app import app

    with TestClient(app) as demo:
        assert demo.post("/positions/close-all", headers=KEY).status_code == 404


def test_the_screen_reaches_close_all_and_no_order() -> None:
    assert browser_caller_may_reach("/positions/close-all")
    assert not browser_caller_may_reach("/orders")


@respx.mock
def test_the_live_trace_names_the_caller_before_and_after(
    live: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    _logged_in()
    _filled()
    with caplog.at_level(logging.INFO, logger="capital_gateway.live_trace"):
        live.post("/orders", json=_order(), headers=KEY)
        live.post("/orders", json=_order(size=5), headers=KEY)

    lines = [r.getMessage() for r in caplog.records if r.name == "capital_gateway.live_trace"]
    assert any(
        "sending" in line and "size=0.5" in line and f"account={ACCOUNT}" in line for line in lines
    )
    assert any("settled" in line and "status=FILLED" in line for line in lines)
    assert any("refused by limits" in line and "over the limit" in line for line in lines)
    assert all("caller=" in line for line in lines)
    for secret in (GATEWAY_KEY, "super-secret-key", "hunter2"):
        assert secret not in caplog.text

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from capital_gateway.client import CapitalClient
from capital_gateway.config import DEMO_BASE_URL, Settings
from capital_gateway.rategate import RateGate

SESSION = f"{DEMO_BASE_URL}/api/v1/session"
ACCOUNTS = f"{DEMO_BASE_URL}/api/v1/accounts"


@pytest.fixture
def client() -> CapitalClient:
    return CapitalClient(
        Settings(
            capital_api_key="k",
            capital_identifier="me@example.com",
            capital_password="p",
            gateway_api_key="g",
            _env_file=None,
        )
    )


def login_response(cst: str = "cst-1", token: str = "tok-1") -> httpx.Response:
    return httpx.Response(200, headers={"CST": cst, "X-SECURITY-TOKEN": token}, json={})


@respx.mock
async def test_the_first_call_logs_in_and_carries_the_tokens(client: CapitalClient) -> None:
    respx.post(SESSION).mock(return_value=login_response())
    accounts = respx.get(ACCOUNTS).mock(return_value=httpx.Response(200, json={"accounts": []}))

    await client.accounts()

    sent = accounts.calls[0].request
    assert sent.headers["CST"] == "cst-1"
    assert sent.headers["X-SECURITY-TOKEN"] == "tok-1"
    await client.aclose()


@respx.mock
async def test_an_expired_session_re_authenticates_and_retries_once(
    client: CapitalClient,
) -> None:
    session = respx.post(SESSION).mock(
        side_effect=[login_response("cst-1", "tok-1"), login_response("cst-2", "tok-2")]
    )
    accounts = respx.get(ACCOUNTS).mock(
        side_effect=[
            httpx.Response(401, json={"errorCode": "error.invalid.session.token"}),
            httpx.Response(200, json={"accounts": []}),
        ]
    )

    resp = await client.accounts()

    assert resp.status_code == 200
    assert session.call_count == 2
    # The retry carries the new tokens, not the dead ones — that is the whole point.
    assert accounts.calls[1].request.headers["CST"] == "cst-2"
    await client.aclose()


@respx.mock
async def test_a_second_401_is_not_retried_again(client: CapitalClient) -> None:
    respx.post(SESSION).mock(return_value=login_response())
    accounts = respx.get(ACCOUNTS).mock(return_value=httpx.Response(401, json={}))

    resp = await client.accounts()

    # One retry, then the 401 is handed back. Retrying a persistent 401 in a loop is how
    # a wrong password becomes a lockout.
    assert resp.status_code == 401
    assert accounts.call_count == 2
    await client.aclose()


@respx.mock
async def test_concurrent_callers_trigger_exactly_one_login(client: CapitalClient) -> None:
    session = respx.post(SESSION).mock(return_value=login_response())
    respx.get(ACCOUNTS).mock(return_value=httpx.Response(200, json={"accounts": []}))

    await asyncio.gather(*(client.accounts() for _ in range(8)))

    # capital.com invalidates the previous session on every new login, so eight logins
    # would leave seven callers holding tokens that were already killed.
    assert session.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_login_is_shared_not_serialised(client: CapitalClient) -> None:
    # A lock would also produce one login here if the second caller re-checked the
    # session; it would not if it simply logged in again in turn. Proving the waiters
    # got the *same* result is what separates sharing from serialising.
    respx.post(SESSION).mock(return_value=login_response())
    respx.get(ACCOUNTS).mock(return_value=httpx.Response(200, json={"accounts": []}))

    results = await asyncio.gather(client.login(), client.login(), client.login())

    assert all(r is results[0] for r in results)
    await client.aclose()


@respx.mock
async def test_the_gate_bounds_the_request_rate(client: CapitalClient) -> None:
    respx.post(SESSION).mock(return_value=login_response())
    respx.get(ACCOUNTS).mock(return_value=httpx.Response(200, json={"accounts": []}))

    # The login spends one slot, so 10 further calls need a second window.
    started = time.monotonic()
    await asyncio.gather(*(client.accounts() for _ in range(10)))
    elapsed = time.monotonic() - started

    assert elapsed >= 1.0
    await client.aclose()


async def test_the_gate_lets_a_burst_through_up_to_its_limit() -> None:
    gate = RateGate(limit=5, per_seconds=1.0)

    started = time.monotonic()
    await asyncio.gather(*(gate.acquire() for _ in range(5)))
    elapsed = time.monotonic() - started

    # Under the limit nothing waits — a gate that paced every request would turn a
    # 30-request deep read into a 3-second one for no reason.
    assert elapsed < 0.2


def test_stream_tokens_refuse_to_answer_before_a_session(client: CapitalClient) -> None:
    with pytest.raises(RuntimeError):
        client.stream_tokens()

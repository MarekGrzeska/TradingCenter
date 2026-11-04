from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from capital_gateway.app import stream_tokens_for
from capital_gateway.client import CapitalClient
from capital_gateway.config import DEMO_BASE_URL, Settings
from capital_gateway.errors import GatewayError
from capital_gateway.rategate import RateGate

SESSION = f"{DEMO_BASE_URL}/api/v1/session"
ACCOUNTS = f"{DEMO_BASE_URL}/api/v1/accounts"


def on_account(account_id: str | None = None) -> CapitalClient:
    return CapitalClient(
        Settings(
            capital_api_key="k",
            capital_identifier="me@example.com",
            capital_password="p",
            gateway_api_key="g",
            _env_file=None,
        ),
        account_id=account_id,
    )


@pytest.fixture
def client() -> CapitalClient:
    return on_account()


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

    # Eight logins would be seven wasted requests against the account's shared 10/second budget,
    # and eight sessions expiring on eight schedules. Not seven dead ones: they coexist.
    assert session.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_login_is_shared_not_serialised(client: CapitalClient) -> None:
    # A lock would also produce one login here if the second caller re-checked. Proving the
    # waiters got the *same* result is what separates sharing from serialising.
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


@respx.mock
async def test_stream_tokens_prove_the_session_still_answers(client: CapitalClient) -> None:
    """A websocket never receives a 401, so the stream cannot notice its session died. Checking
    costs one request per connection and stops a reconnect loop retrying with dead tokens."""
    respx.post(SESSION).mock(return_value=login_response())
    check = respx.get(SESSION).mock(return_value=httpx.Response(200, json={}))

    cst, token = await stream_tokens_for(client)

    assert (cst, token) == ("cst-1", "tok-1")
    assert check.called
    await client.aclose()


@respx.mock
async def test_a_session_invalidated_elsewhere_is_replaced_before_the_stream_uses_it(
    client: CapitalClient,
) -> None:
    """A session can stop being honoured while the tokens sit there — a stream makes no REST calls,
    so its borrowed session expires from disuse, and the pair is then present and wrong."""
    login = respx.post(SESSION)
    login.side_effect = [login_response(), login_response("cst-2", "tok-2")]
    check = respx.get(SESSION)
    check.side_effect = [
        httpx.Response(401, json={}),  # the session died while nobody was looking
        httpx.Response(200, json={}),
    ]

    await client.login()
    cst, token = await stream_tokens_for(client)

    assert (cst, token) == ("cst-2", "tok-2"), "the stream must not carry the dead pair"
    assert login.call_count == 2
    await client.aclose()


@respx.mock
async def test_a_session_the_provider_will_not_confirm_stops_the_subscription(
    client: CapitalClient,
) -> None:
    """The failure this defence did not cover until 18 August 2026: the check was made and its
    answer dropped, so a login that fails for good let `Upstream` subscribe with a dead pair."""
    respx.post(SESSION).mock(return_value=login_response())
    check = respx.get(SESSION).mock(return_value=httpx.Response(403, json={}))

    with pytest.raises(GatewayError) as raised:
        await stream_tokens_for(client)

    assert "403" in str(raised.value)
    # Twice: `request()` does not retry a 403, so this is the check plus nothing.
    assert check.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_session_that_cannot_be_renewed_stops_the_subscription(
    client: CapitalClient,
) -> None:
    """The same thing by the route that actually happens: 401, one more login, 401 again.
    `request()` has spent its retry, and the tokens it holds are the dead ones."""
    respx.post(SESSION).mock(return_value=login_response())
    check = respx.get(SESSION).mock(return_value=httpx.Response(401, json={}))

    with pytest.raises(GatewayError):
        await stream_tokens_for(client)

    assert check.call_count == 2
    await client.aclose()


@respx.mock
async def test_the_first_connection_logs_in_before_asking_for_tokens(
    client: CapitalClient,
) -> None:
    """The behaviour this replaced, kept: with no session at all there is nothing to
    check and a login is what produces one."""
    login = respx.post(SESSION).mock(return_value=login_response())
    respx.get(SESSION).mock(return_value=httpx.Response(200, json={}))

    cst, token = await stream_tokens_for(client)

    assert login.called
    assert (cst, token) == ("cst-1", "tok-1")
    await client.aclose()


def opened_on(account_id: str, cst: str = "cst-1", token: str = "tok-1") -> httpx.Response:
    return httpx.Response(
        200, headers={"CST": cst, "X-SECURITY-TOKEN": token}, json={"currentAccountId": account_id}
    )


@respx.mock
async def test_a_renewed_session_is_put_back_on_its_account_before_the_retry(
    client: CapitalClient,
) -> None:
    respx.post(SESSION).mock(
        side_effect=[opened_on("preferred"), opened_on("preferred", "cst-2", "tok-2")]
    )
    switch = respx.put(SESSION).mock(return_value=httpx.Response(200, json={}))
    positions = respx.get(f"{DEMO_BASE_URL}/api/v1/positions").mock(
        side_effect=[
            httpx.Response(200, json={"positions": []}),
            httpx.Response(401, json={"errorCode": "error.invalid.session.token"}),
            httpx.Response(200, json={"positions": []}),
        ]
    )
    await client.switch_account("other")
    await client.positions()

    await client.positions()

    # Logged in on "preferred" twice; each time put back on "other" before anything else went out.
    assert [c.request.read() for c in switch.calls] == [b'{"accountId":"other"}'] * 2
    assert switch.calls[1].request.headers["CST"] == "cst-2"
    assert positions.calls[2].request.headers["CST"] == "cst-2"
    await client.aclose()


@respx.mock
async def test_waiters_on_one_login_all_get_the_restored_account() -> None:
    client = on_account("other")
    session = respx.post(SESSION).mock(return_value=opened_on("preferred"))
    switch = respx.put(SESSION).mock(return_value=httpx.Response(200, json={}))
    respx.get(ACCOUNTS).mock(return_value=httpx.Response(200, json={"accounts": []}))

    await asyncio.gather(*(client.accounts() for _ in range(5)))

    assert session.call_count == 1
    assert switch.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_refused_restore_fails_the_call_instead_of_running_it_elsewhere() -> None:
    client = on_account("gone")
    respx.post(SESSION).mock(return_value=opened_on("preferred"))
    respx.put(SESSION).mock(
        return_value=httpx.Response(400, json={"errorCode": "error.invalid.accountId"})
    )
    orders = respx.post(f"{DEMO_BASE_URL}/api/v1/positions").mock(
        return_value=httpx.Response(200, json={})
    )

    with pytest.raises(GatewayError, match="gone") as refused:
        await client.create_position({"epic": "US100"})

    assert refused.value.status_code == 400
    assert not orders.called
    assert not client.authenticated
    await client.aclose()


@respx.mock
async def test_a_login_body_naming_no_account_on_the_right_one_is_not_a_refusal() -> None:
    client = on_account("other")
    respx.post(SESSION).mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "t"}, json={})
    )
    respx.put(SESSION).mock(
        return_value=httpx.Response(400, json={"errorCode": "error.not-different.accountId"})
    )
    respx.get(ACCOUNTS).mock(return_value=httpx.Response(200, json={"accounts": []}))

    assert (await client.accounts()).status_code == 200
    assert client.authenticated
    await client.aclose()


@respx.mock
async def test_a_rate_limited_restore_waits_and_tries_once_more() -> None:
    client = on_account("other")
    respx.post(SESSION).mock(return_value=opened_on("preferred"))
    switch = respx.put(SESSION).mock(
        side_effect=[
            httpx.Response(429, json={"errorCode": "error.too-many.requests"}),
            httpx.Response(200, json={}),
        ]
    )
    respx.get(ACCOUNTS).mock(return_value=httpx.Response(200, json={"accounts": []}))

    assert (await client.accounts()).status_code == 200
    assert switch.call_count == 2
    await client.aclose()


@respx.mock
async def test_a_restore_still_rate_limited_reads_as_unavailable_not_refused() -> None:
    client = on_account("other")
    respx.post(SESSION).mock(return_value=opened_on("preferred"))
    respx.put(SESSION).mock(
        return_value=httpx.Response(429, json={"errorCode": "error.too-many.requests"})
    )

    with pytest.raises(GatewayError) as failed:
        await client.accounts()

    assert failed.value.status_code == 503
    await client.aclose()

"""The seam to `teams` — three outcomes, one retry rule, and one credential.

specs/teams-mcp-upstream-access. Everything here goes through `respx`, so what is being
checked is what leaves this process and what it makes of what comes back — not that
`teams` behaves, which is `teams`' own suite's job.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from teams_mcp.client import TeamsClient
from teams_mcp.errors import ToolRefusal, UpstreamUnavailable

from .conftest import BASE, OPERATOR_TOKEN


@respx.mock
async def test_a_read_carries_the_operators_token_not_the_modules_own(
    teams: TeamsClient,
) -> None:
    route = respx.get(f"{BASE}/teams").mock(return_value=httpx.Response(200, json=[]))

    await teams.get("/teams", token=OPERATOR_TOKEN)

    assert route.called
    assert route.calls.last.request.headers["authorization"] == f"Bearer {OPERATOR_TOKEN}"


@respx.mock
async def test_a_refusal_travels_with_teams_own_words(teams: TeamsClient) -> None:
    respx.post(f"{BASE}/teams").mock(
        return_value=httpx.Response(
            422, json={"detail": "agent 'scout' names model 'gpt-9', which is not in the catalogue"}
        )
    )

    with pytest.raises(ToolRefusal) as err:
        await teams.post("/teams", token=OPERATOR_TOKEN, json={})

    assert "scout" in str(err.value)
    assert "gpt-9" in str(err.value)


@respx.mock
async def test_a_validation_list_is_flattened_rather_than_dropped(teams: TeamsClient) -> None:
    respx.post(f"{BASE}/teams").mock(
        return_value=httpx.Response(
            422, json={"detail": [{"loc": ["body", "name"], "msg": "field required"}]}
        )
    )

    with pytest.raises(ToolRefusal) as err:
        await teams.post("/teams", token=OPERATOR_TOKEN, json={})

    assert "field required" in str(err.value)


@respx.mock
async def test_a_404_reads_as_both_answers_at_once(teams: TeamsClient) -> None:
    """Somebody else's team and a team that never existed are the same answer by design
    (teams-browser-access), and the sentence says so rather than picking one."""
    respx.get(f"{BASE}/teams/7").mock(return_value=httpx.Response(404))

    with pytest.raises(ToolRefusal) as err:
        await teams.get("/teams/7", token=OPERATOR_TOKEN)

    assert "somebody else" in str(err.value)


@respx.mock
async def test_an_expired_operator_credential_is_unavailability_naming_itself(
    teams: TeamsClient,
) -> None:
    respx.get(f"{BASE}/teams").mock(return_value=httpx.Response(401))

    with pytest.raises(UpstreamUnavailable) as err:
        await teams.get("/teams", token=OPERATOR_TOKEN)

    assert "expired" in str(err.value)
    assert "signing in again" in str(err.value).lower()


@respx.mock
async def test_a_read_is_retried_once_on_a_server_error(teams: TeamsClient) -> None:
    route = respx.get(f"{BASE}/teams").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=[{"id": 1}])]
    )

    answer = await teams.get("/teams", token=OPERATOR_TOKEN)

    assert route.call_count == 2
    assert answer == [{"id": 1}]


@respx.mock
async def test_a_write_is_never_retried(teams: TeamsClient) -> None:
    """A repeated create_team is a second team and a repeated run_team a second bill —
    so a 5xx on a write is left where it fell, named as unknown rather than as failed."""
    route = respx.post(f"{BASE}/teams").mock(return_value=httpx.Response(503))

    with pytest.raises(UpstreamUnavailable) as err:
        await teams.post("/teams", token=OPERATOR_TOKEN, json={"name": "desk"})

    assert route.call_count == 1
    assert "unknown" in str(err.value)


@respx.mock
async def test_a_timeout_on_a_write_says_the_effect_is_unknown(teams: TeamsClient) -> None:
    respx.post(f"{BASE}/teams").mock(side_effect=httpx.ReadTimeout("too slow"))

    with pytest.raises(UpstreamUnavailable) as err:
        await teams.post("/teams", token=OPERATOR_TOKEN, json={})

    assert "may or may not" in str(err.value)


@respx.mock
async def test_a_timeout_on_a_read_says_nothing_was_read(teams: TeamsClient) -> None:
    respx.get(f"{BASE}/teams").mock(side_effect=httpx.ReadTimeout("too slow"))

    with pytest.raises(UpstreamUnavailable) as err:
        await teams.get("/teams", token=OPERATOR_TOKEN)

    assert "Nothing was read" in str(err.value)


@respx.mock
async def test_an_unreachable_teams_is_unavailability_not_a_refusal(teams: TeamsClient) -> None:
    respx.get(f"{BASE}/teams").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(UpstreamUnavailable):
        await teams.get("/teams", token=OPERATOR_TOKEN)


@respx.mock
async def test_an_empty_body_is_none_rather_than_an_error(teams: TeamsClient) -> None:
    respx.post(f"{BASE}/runs/3/cancel").mock(return_value=httpx.Response(202))

    assert await teams.post("/runs/3/cancel", token=OPERATOR_TOKEN) is None

"""Whose request this is, and what happens when nobody can say.

Its own file because every other test in this suite puts an operator in place through
`signed_in`, and something has to check the thing being put in place.

What is read changed with the merge and is worth stating: not a bearer token out of a
header, but the operator's own principal out of a context variable the adapter sets. There
is no authenticator between the chat request and these tools any more — the identity has
already been through one, and it is the identity that travels rather than the credential.
"""

from __future__ import annotations

import pytest

from teams_tools.errors import ToolRefusal
from teams_tools.operator import carrying, operator_principal, redacted


def test_the_operator_is_read_from_what_the_adapter_put_in_place() -> None:
    with carrying("some-operator"):
        assert operator_principal() == "some-operator"


def test_a_call_with_no_operator_is_refused_naming_the_absence() -> None:
    with pytest.raises(ToolRefusal) as err:
        operator_principal()

    assert "no operator identity" in str(err.value)
    assert "nothing was written" in str(err.value).lower()


def test_a_blank_principal_counts_as_absent() -> None:
    with carrying("   "), pytest.raises(ToolRefusal):
        operator_principal()


def test_the_identity_does_not_outlive_the_call_it_was_set_for() -> None:
    """The bug this rules out is the expensive one: a principal left behind on a task that
    is reused, so the next operator's turn acts as the last one."""
    with carrying("some-operator"):
        assert operator_principal() == "some-operator"

    with pytest.raises(ToolRefusal):
        operator_principal()


def test_it_is_reset_even_when_a_tool_raises() -> None:
    with pytest.raises(RuntimeError), carrying("some-operator"):
        raise RuntimeError("a tool failed")

    with pytest.raises(ToolRefusal):
        operator_principal()


def test_an_absent_operator_answers_nothing_when_nobody_could_have_been_identified() -> None:
    """The local carve-out: `None`, not a substituted identity and not a refusal
    ("Maszyna deweloperska, gdzie nikt nie może być uwierzytelniony")."""
    assert operator_principal(optional=True) is None


def test_a_blank_principal_answers_the_same_as_none_under_the_carve_out() -> None:
    with carrying("  "):
        assert operator_principal(optional=True) is None


def test_a_present_operator_is_still_carried_when_an_absent_one_would_be_tolerated() -> None:
    """The carve-out tolerates an absence; it does not stop reading an identity that is
    there, which is what would quietly turn a signed-in local operator into an anonymous
    one."""
    with carrying("some-operator"):
        assert operator_principal(optional=True) == "some-operator"


def test_requiring_an_operator_is_what_happens_by_default() -> None:
    # The keyword exists for exactly one caller, and nothing reaches this function's
    # tolerant branch by forgetting to pass anything.
    with pytest.raises(ToolRefusal):
        operator_principal()


def test_redacted_says_whether_there_was_one_and_nothing_else() -> None:
    assert redacted("a-real-looking-principal") == "present"
    assert redacted(None) == "absent"
    assert "a-real-looking-principal" not in redacted("a-real-looking-principal")


async def test_the_operators_identity_never_reaches_a_log_line(caplog) -> None:
    """It passes through the tool seam and the client, and neither may write it down.
    Checked at DEBUG, where a library that logs request headers would show up."""
    import logging

    import httpx
    import respx

    from teams_tools.client import BASE_URL, TeamsClient

    secret = "operator-principal-that-must-not-be-logged"
    client = TeamsClient(_never_reached, operator_identity_optional=False)

    with caplog.at_level(logging.DEBUG), respx.mock:
        respx.get(f"{BASE_URL}/teams").mock(return_value=httpx.Response(200, json=[]))
        await client.get("/teams", token=secret)

    await client.aclose()
    assert secret not in caplog.text
    assert secret not in "".join(record.getMessage() for record in caplog.records)


async def _never_reached(scope, receive, send):  # pragma: no cover - intercepted above
    raise AssertionError("the request should have been intercepted above the transport")

"""Fixtures for the team tools, and the one thing about them that had to change.

These tools reach the teams routes through `httpx.ASGITransport` now — no socket, no
server. respx's default mocker patches httpcore, which an ASGI transport never touches, so
every route in this suite would be bypassed and every test would hit a real application
object. Its other mocker patches `httpx` one layer higher, above the transport, and that
one intercepts regardless of which transport the client was built with. Selecting it here
is what keeps the rest of this suite written the way it was.
"""

from __future__ import annotations

import pytest
import respx.mocks

from teams_tools.client import BASE_URL, TeamsClient
from teams_tools.operator import carrying
from teams_tools.server import build_server

# Patch above the transport, not below it. Without this line every `respx.get(...)` in this
# directory registers a route nothing routes through.
respx.mocks.DEFAULT_MOCKER = "httpx"

BASE = BASE_URL

# Not a real principal and not shaped like one on purpose: nothing here parses it, and a
# test carrying something that looks like a credential invites somebody to paste a real one
# in its place.
OPERATOR = "operator-principal-for-tests"


class _NeverReached:
    """The application the client is built over. Every test in this suite intercepts above
    the transport, so this is called only if an interception was forgotten — where failing
    loudly is the point."""

    async def __call__(self, scope, receive, send):  # pragma: no cover - see the docstring
        raise AssertionError(
            "a tool call reached the application object: this test meant to intercept it"
        )


@pytest.fixture
def teams() -> TeamsClient:
    """The local shape, and that is load-bearing rather than incidental: with nothing
    authenticating in front of the process, a missing operator is a desk rather than a
    broken chain. Tests wanting the other side of that boundary take `guarded_teams`."""
    return TeamsClient(_NeverReached(), operator_identity_optional=True)


@pytest.fixture
def guarded_teams() -> TeamsClient:
    """The deployed shape: an authenticator in front, so a missing operator identity is a
    broken chain and every tool refuses."""
    return TeamsClient(_NeverReached(), operator_identity_optional=False)


@pytest.fixture
def server(teams: TeamsClient):
    """The tool registry and the client it was built with, so a test can mock the exact
    requests it will make."""
    return build_server(teams), teams


@pytest.fixture
def guarded_server(guarded_teams: TeamsClient):
    """A registry built on the deployed shape, for the tests that check what happens when
    nobody is behind a call there. Deliberately not paired with `signed_in`."""
    return build_server(guarded_teams), guarded_teams


@pytest.fixture
def signed_in():
    """Every tool asks `operator.py` who this call acts for before it touches a route.
    Calling a tool through `mcp.call_tool` has no chat request behind it, so the identity is
    put in place here — through the same context manager the adapter uses, rather than by
    stubbing the function that reads it, which would leave nothing tested."""
    with carrying(OPERATOR):
        yield OPERATOR

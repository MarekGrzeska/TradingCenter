"""Easy Auth's headers, read the same way by both surfaces.

`agent/auth.py` and `teams/auth.py` were two modules' files and are byte-identical apart
from the namespace they read their settings out of (`app.state.agent` against
`app.state.teams`). Two copies of these tests meant a rule fixed on one surface could rot
on the other with nothing to say so; one parameterised file cannot.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import Headers

from agent import auth as agent_auth
from teams import auth as teams_auth

SURFACES = [
    pytest.param(agent_auth, "agent", id="agent"),
    pytest.param(teams_auth, "teams", id="teams"),
]


class _FakeSettings:
    def __init__(self, require_authenticated_principal: bool) -> None:
        self.require_authenticated_principal = require_authenticated_principal


class _FakeSurfaceState:
    def __init__(self, require_authenticated_principal: bool) -> None:
        self.settings = _FakeSettings(require_authenticated_principal)


class _FakeAppState:
    """`app.state.<surface>`, not `app.state` — the two surfaces keep their own namespace
    on the one application they share."""

    def __init__(self, namespace: str, require_authenticated_principal: bool) -> None:
        setattr(self, namespace, _FakeSurfaceState(require_authenticated_principal))


class _FakeApp:
    def __init__(self, namespace: str, require_authenticated_principal: bool) -> None:
        self.state = _FakeAppState(namespace, require_authenticated_principal)


def _request(
    headers: dict[str, str], namespace: str, *, require_authenticated_principal: bool
) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "app": _FakeApp(namespace, require_authenticated_principal),
    }
    return Request(scope)


@pytest.mark.parametrize(("auth", "namespace"), SURFACES)
def test_the_principal_id_header_is_used_when_present(auth, namespace: str) -> None:
    request = _request(
        {"X-MS-CLIENT-PRINCIPAL-ID": "abc-123"}, namespace, require_authenticated_principal=True
    )
    assert auth.current_principal(request) == "abc-123"


@pytest.mark.parametrize(("auth", "namespace"), SURFACES)
def test_the_name_header_is_a_fallback(auth, namespace: str) -> None:
    request = _request(
        {"X-MS-CLIENT-PRINCIPAL-NAME": "operator@example.com"},
        namespace,
        require_authenticated_principal=True,
    )
    assert auth.current_principal(request) == "operator@example.com"


@pytest.mark.parametrize(("auth", "namespace"), SURFACES)
def test_no_identity_and_no_requirement_is_the_local_identity(auth, namespace: str) -> None:
    request = _request({}, namespace, require_authenticated_principal=False)
    assert auth.current_principal(request) == auth.UNAUTHENTICATED


@pytest.mark.parametrize(("auth", "namespace"), SURFACES)
def test_no_identity_with_the_requirement_on_is_refused(auth, namespace: str) -> None:
    # specs/{agent,teams}-browser-access, "Moduł nie bierze na wiarę warstwy przed sobą"
    request = _request({}, namespace, require_authenticated_principal=True)
    with pytest.raises(HTTPException) as err:
        auth.current_principal(request)
    assert err.value.status_code == 401


@pytest.mark.parametrize(("auth", "namespace"), SURFACES)
def test_headers_arrive_however_starlette_normalises_them(auth, namespace: str) -> None:
    # Belt and braces: Headers() lower-cases lookups regardless of wire case.
    request = _request(
        {"x-ms-client-principal-id": "abc-123"}, namespace, require_authenticated_principal=True
    )
    assert Headers(scope=request.scope)["X-MS-CLIENT-PRINCIPAL-ID"] == "abc-123"
    assert auth.current_principal(request) == "abc-123"

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import Headers

from agent.auth import UNAUTHENTICATED, current_principal


class _FakeSettings:
    def __init__(self, require_authenticated_principal: bool) -> None:
        self.require_authenticated_principal = require_authenticated_principal


class _FakeAppState:
    """`app.state.agent`, not `app.state` — the two surfaces keep their own namespace on
    the one application they share."""

    def __init__(self, require_authenticated_principal: bool) -> None:
        self.agent = _FakeSurfaceState(require_authenticated_principal)


class _FakeSurfaceState:
    def __init__(self, require_authenticated_principal: bool) -> None:
        self.settings = _FakeSettings(require_authenticated_principal)


class _FakeApp:
    def __init__(self, require_authenticated_principal: bool) -> None:
        self.state = _FakeAppState(require_authenticated_principal)


def _request(headers: dict[str, str], *, require_authenticated_principal: bool) -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "app": _FakeApp(require_authenticated_principal),
    }
    return Request(scope)


def test_the_principal_id_header_is_used_when_present() -> None:
    request = _request({"X-MS-CLIENT-PRINCIPAL-ID": "abc-123"}, require_authenticated_principal=True)
    assert current_principal(request) == "abc-123"


def test_the_name_header_is_a_fallback() -> None:
    request = _request(
        {"X-MS-CLIENT-PRINCIPAL-NAME": "operator@example.com"},
        require_authenticated_principal=True,
    )
    assert current_principal(request) == "operator@example.com"


def test_no_identity_and_no_requirement_is_the_local_identity() -> None:
    request = _request({}, require_authenticated_principal=False)
    assert current_principal(request) == UNAUTHENTICATED


def test_no_identity_with_the_requirement_on_is_refused() -> None:
    # specs/agent-browser-access, "Moduł nie bierze na wiarę warstwy przed sobą"
    request = _request({}, require_authenticated_principal=True)
    with pytest.raises(HTTPException) as err:
        current_principal(request)
    assert err.value.status_code == 401


def test_headers_arrive_however_starlette_normalises_them() -> None:
    # Belt and braces: Headers() lower-cases lookups regardless of wire case.
    request = _request({"x-ms-client-principal-id": "abc-123"}, require_authenticated_principal=True)
    assert Headers(scope=request.scope)["X-MS-CLIENT-PRINCIPAL-ID"] == "abc-123"
    assert current_principal(request) == "abc-123"

"""specs/teams-mcp-authorship — whose request this is, and what happens when nobody can
say. Header extraction gets its own file because every other test in this suite stubs it
out, and something has to check the thing being stubbed."""

from __future__ import annotations

import pytest

from teams_mcp.errors import ToolRefusal
from teams_mcp.operator import OPERATOR_TOKEN_HEADER, operator_token, redacted


class _Headers(dict):
    """Starlette's own headers read case-insensitively, and the header this looks for is
    written in mixed case by whoever sends it."""

    def get(self, key, default=None):
        return super().get(key.lower(), default)


class _Request:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = _Headers({k.lower(): v for k, v in headers.items()})


class _RequestContext:
    def __init__(self, request) -> None:
        self.request = request


class _Context:
    def __init__(self, request) -> None:
        self.request_context = _RequestContext(request)


class _ContextOutsideARequest:
    @property
    def request_context(self):
        raise ValueError("Context is not available outside of a request")


def test_the_token_is_read_from_its_own_header() -> None:
    context = _Context(_Request({OPERATOR_TOKEN_HEADER: "operator-token"}))
    assert operator_token(context) == "operator-token"


def test_a_call_with_no_operator_header_is_refused_naming_the_absence() -> None:
    with pytest.raises(ToolRefusal) as err:
        operator_token(_Context(_Request({})))

    assert "no operator identity" in str(err.value)
    assert "nothing was written" in str(err.value).lower()


def test_a_blank_header_counts_as_absent() -> None:
    with pytest.raises(ToolRefusal):
        operator_token(_Context(_Request({OPERATOR_TOKEN_HEADER: "   "})))


def test_a_tool_running_outside_a_request_is_refused_rather_than_crashing() -> None:
    with pytest.raises(ToolRefusal):
        operator_token(_ContextOutsideARequest())


def test_the_modules_own_authorization_header_is_not_mistaken_for_the_operators() -> None:
    """`Authorization` carries agent's identity to this module's own authenticator. It is
    a different credential answering a different question and must never be borrowed."""
    context = _Context(_Request({"authorization": "Bearer agents-own-managed-identity"}))

    with pytest.raises(ToolRefusal):
        operator_token(context)


def test_redacted_says_whether_there_was_one_and_nothing_else() -> None:
    assert redacted("a-real-looking-token") == "present"
    assert redacted(None) == "absent"
    assert "a-real-looking-token" not in redacted("a-real-looking-token")

"""Each surface prints its own OpenAPI document, and the terminal generates a contract from each. One file for
both rather than a twin per surface — the rule is the same rule twice: a document describes its surface alone."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from agent import openapi as agent_openapi
from teams import openapi as teams_openapi

# (the printer, a path only this surface serves, a path only the other one serves)
SURFACES: dict[str, tuple[Callable[[], dict[str, Any]], str, str]] = {
    "agent": (agent_openapi.document, "/sessions", "/teams"),
    "teams": (teams_openapi.document, "/teams", "/sessions"),
}


@pytest.fixture(params=sorted(SURFACES))
def surface(request: pytest.FixtureRequest) -> str:
    return request.param


def test_document_is_a_valid_looking_openapi_object(surface: str) -> None:
    schema = SURFACES[surface][0]()
    assert schema["openapi"].startswith("3.")
    assert SURFACES[surface][1] in schema["paths"]


def test_the_document_describes_this_surface_and_not_the_one_beside_it(surface: str) -> None:
    """`/health` belongs to the process rather than to either surface, and the other surface's routes
    belong to the other file the terminal generates."""
    _, own, other = SURFACES[surface]
    paths = SURFACES[surface][0]()["paths"]
    assert "/health" not in paths
    assert other not in paths
    assert own in paths


def test_where_the_two_collided_the_teams_surface_moved() -> None:
    paths = teams_openapi.document()["paths"]
    assert "/teams/models" in paths
    assert "/teams/usage" in paths
    assert "/models" in agent_openapi.document()["paths"]

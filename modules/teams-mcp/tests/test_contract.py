"""The committed snapshot of teams' wire — the thing that catches a change on the other
side before it reaches a tool call (specs/teams-mcp-upstream-access, "Kontrakt modułu
`teams` jest sprawdzany, nie zakładany").

Marked `contract` because generating the fresh document runs `uv` against the teams
module, which is slower than the rest of this suite and needs that module's environment.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).resolve().parent.parent / "contract" / "teams.openapi.json"

# Every route this module's tools reach. A route disappearing from teams' document is
# the failure this list exists to turn into a red test rather than a 404 at run time.
USED_PATHS = (
    "/teams",
    "/teams/{team_id}",
    "/teams/{team_id}/revisions",
    "/teams/{team_id}/revisions/latest",
    "/teams/{team_id}/runs",
    "/teams/{team_id}/schedules",
    "/teams/{team_id}/triggers",
    "/runs/{run_id}",
    "/runs/{run_id}/steps",
    "/runs/{run_id}/tool-calls",
    "/schedules/{schedule_id}/fires",
    "/triggers/{trigger_id}/fires",
    "/models",
    "/tools",
)


def test_the_snapshot_is_committed_and_parses() -> None:
    assert SNAPSHOT.exists(), "run `uv run python scripts/contract.py generate`"
    json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_every_route_the_tools_use_is_in_the_snapshot() -> None:
    document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    missing = [path for path in USED_PATHS if path not in document["paths"]]
    assert not missing, f"teams no longer publishes: {missing}"


@pytest.mark.contract
def test_the_snapshot_matches_what_teams_publishes_right_now() -> None:
    # Imported here rather than at module scope: it shells out to the teams module,
    # and the unmarked tests in this file must not pay for that.
    from scripts import contract

    assert SNAPSHOT.read_text(encoding="utf-8") == contract.schema_text()

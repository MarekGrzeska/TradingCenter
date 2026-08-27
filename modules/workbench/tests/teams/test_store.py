"""The catalogue's queries against a real PostgreSQL. Against the container rather than a fake: what is
under test is append-only-ness, the owner filter and what survives retiring a team."""

from __future__ import annotations

import asyncpg
import pytest

from teams import store
from teams.contract import AgentDefinition, TeamDefinition, TeamEdge, TeamOut, TeamRevisionOut

pytestmark = pytest.mark.db

OWNER = "operator-1"
STRANGER = "operator-2"


def _definition(*, prompt: str = "read the chart") -> TeamDefinition:
    return TeamDefinition(
        agents=[
            AgentDefinition(key="scout", role="scout", prompt=prompt, model_id="luna"),
            AgentDefinition(key="judge", role="judge", prompt="weigh it", model_id="luna"),
        ],
        edges=[TeamEdge(from_="scout", to="judge")],
    )


async def _team(db: asyncpg.Connection, *, owner: str = OWNER, name: str = "morning desk"):
    return await store.create_team(
        db, owner_principal=owner, name=name, description="", definition=_definition()
    )


async def test_a_new_team_arrives_with_its_first_revision(db: asyncpg.Connection) -> None:
    team, revision = await _team(db)

    assert revision["team_id"] == team["id"]
    assert revision["version"] == 1
    # The blob round-trips through JSONB unchanged, `from` alias included.
    assert TeamRevisionOut.from_row(revision).definition == _definition()


async def test_saving_a_revision_leaves_the_previous_one_as_it_was(db: asyncpg.Connection) -> None:
    # specs/teams-catalogue, "Rewizja raz zapisana się nie zmienia".
    team, first = await _team(db)

    second = await store.save_revision(
        db,
        team_id=team["id"],
        owner_principal=OWNER,
        definition=_definition(prompt="read the chart, twice"),
    )
    assert second is not None
    assert second["version"] == 2

    reread = await store.get_revision(db, team_id=team["id"], owner_principal=OWNER, version=1)
    assert reread is not None
    assert reread["id"] == first["id"]
    assert TeamRevisionOut.from_row(reread).definition == _definition()
    assert TeamRevisionOut.from_row(reread).definition.agents[0].prompt == "read the chart"


async def test_the_latest_revision_is_the_newest_one_saved(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)
    await store.save_revision(
        db, team_id=team["id"], owner_principal=OWNER, definition=_definition(prompt="v2")
    )

    latest = await store.get_latest_revision(db, team_id=team["id"], owner_principal=OWNER)
    assert latest is not None
    assert latest["version"] == 2


async def test_the_catalogue_carries_the_latest_version_without_any_definition(
    db: asyncpg.Connection,
) -> None:
    # specs/teams-catalogue, "Katalog wystarcza, żeby wybrać zespół bez otwierania go".
    team, _ = await _team(db)
    await store.save_revision(
        db, team_id=team["id"], owner_principal=OWNER, definition=_definition(prompt="v2")
    )

    rows = await store.list_teams(db, owner_principal=OWNER)

    assert [row["id"] for row in rows] == [team["id"]]
    assert TeamOut.from_row(rows[0]).latest_revision == 2
    assert "definition" not in rows[0]


async def test_a_team_belonging_to_someone_else_reads_as_missing(db: asyncpg.Connection) -> None:
    # specs/teams-browser-access: the two answers MUST NOT be told apart.
    team, _ = await _team(db)

    assert await store.get_team(db, team_id=team["id"], owner_principal=STRANGER) is None
    assert await store.get_team(db, team_id=team["id"] + 1000, owner_principal=OWNER) is None
    assert await store.list_teams(db, owner_principal=STRANGER) == []
    assert (
        await store.get_revision(
            db, team_id=team["id"], owner_principal=STRANGER, version=1
        )
        is None
    )


async def test_a_stranger_cannot_append_a_revision(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)

    assert (
        await store.save_revision(
            db, team_id=team["id"], owner_principal=STRANGER, definition=_definition()
        )
        is None
    )
    latest = await store.get_latest_revision(db, team_id=team["id"], owner_principal=OWNER)
    assert latest is not None and latest["version"] == 1


async def test_retiring_a_team_takes_it_off_the_catalogue_and_leaves_its_runs(
    db: asyncpg.Connection,
) -> None:
    # specs/teams-catalogue, "Zespół wycofany z katalogu nie zabiera ze sobą przebiegów".
    team, revision = await _team(db)
    # `finished_at` in the same statement as `status`: the CHECK refuses a completed run without one, so a
    # row written any other way is a shape only this test could produce.
    run_id = await db.fetchval(
        "INSERT INTO runs (team_revision_id, owner_principal, status, finished_at) "
        "VALUES ($1, $2, 'completed', now()) RETURNING id",
        revision["id"],
        OWNER,
    )

    assert await store.archive_team(db, team_id=team["id"], owner_principal=OWNER) is True

    assert await store.list_teams(db, owner_principal=OWNER) == []
    assert await store.get_team(db, team_id=team["id"], owner_principal=OWNER) is None
    # The trace and what it points at: both still there.
    assert await db.fetchval("SELECT count(*) FROM runs WHERE id = $1", run_id) == 1
    kept = await store.get_revision(db, team_id=team["id"], owner_principal=OWNER, version=1)
    assert kept is not None
    assert TeamRevisionOut.from_row(kept).definition == _definition()


async def test_retiring_a_retired_team_changes_nothing(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)
    assert await store.archive_team(db, team_id=team["id"], owner_principal=OWNER) is True

    assert await store.archive_team(db, team_id=team["id"], owner_principal=OWNER) is False
    assert (
        await store.save_revision(
            db, team_id=team["id"], owner_principal=OWNER, definition=_definition()
        )
        is None
    )


async def test_a_stranger_cannot_retire_a_team(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)

    assert await store.archive_team(db, team_id=team["id"], owner_principal=STRANGER) is False
    assert await store.get_team(db, team_id=team["id"], owner_principal=OWNER) is not None

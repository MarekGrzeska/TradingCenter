"""Teams and their revisions — the catalogue itself.

`team_revisions` is only ever inserted into. There is no UPDATE statement against it in
this file and there should never be one: a run points at a revision, and a revision edited
underneath a finished run turns its trace into a claim about a team that no longer exists
(specs/teams-catalogue, "Rewizja raz zapisana się nie zmienia").
"""

from __future__ import annotations

import json

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..contract import TeamDefinition

# `latest_revision` is derived rather than stored on `teams`. The correlated subquery
# reads one row from `ix_team_revisions_team_version` per team — a catalogue is tens of
# rows, not millions — and the alternative is a denormalized column that two writers
# could disagree about. The listing still loads no definition, which is the property
# specs/teams-catalogue actually asks for ("lista powstaje bez pobierania definicji").
_LATEST_REVISION = """
    (SELECT max(r.version) FROM team_revisions r WHERE r.team_id = t.id) AS latest_revision
"""

_INSERT_TEAM = """
    INSERT INTO teams (owner_principal, name, description)
    VALUES ($1, $2, $3)
    RETURNING id, name, description, created_at, updated_at
"""

_INSERT_REVISION = """
    INSERT INTO team_revisions (team_id, version, definition)
    VALUES ($1, $2, $3)
    RETURNING id, team_id, version, definition, created_at
"""

# `archived_at IS NULL` rides on every read of a team, here and below: a retired team is
# gone from the catalogue an operator picks a run from, and answers a direct read the way
# a deleted one would — while its revisions stay readable through the statements further
# down (specs/teams-catalogue, "Zespół wycofany z katalogu nie zabiera ze sobą przebiegów").
_SELECT_TEAM = f"""
    SELECT t.id, t.name, t.description, t.created_at, t.updated_at, {_LATEST_REVISION}
      FROM teams t
     WHERE t.id = $1 AND t.owner_principal = $2 AND t.archived_at IS NULL
"""

_SELECT_TEAMS_FOR_OWNER = f"""
    SELECT t.id, t.name, t.description, t.created_at, t.updated_at, {_LATEST_REVISION}
      FROM teams t
     WHERE t.owner_principal = $1 AND t.archived_at IS NULL
     ORDER BY t.updated_at DESC, t.id DESC
"""

# `FOR UPDATE` on the team row, not on `team_revisions`: two saves arriving together
# would otherwise both read the same `max(version)` and one would lose to the unique
# constraint. The lock is held for the length of one insert on a single-operator table.
_LOCK_TEAM_FOR_WRITE = """
    SELECT id FROM teams
     WHERE id = $1 AND owner_principal = $2 AND archived_at IS NULL
       FOR UPDATE
"""

_NEXT_VERSION = """
    SELECT coalesce(max(version), 0) + 1 AS version FROM team_revisions WHERE team_id = $1
"""

# "Moment ostatniej zmiany" in the catalogue listing — bumped by the application because
# nothing else writes to the row when a revision lands.
_TOUCH_TEAM = """
    UPDATE teams SET updated_at = now() WHERE id = $1
"""

# Ownership through the join rather than through `archived_at`: a revision belongs to
# whoever owns the team, and stays readable after that team is retired, because a run
# points at it.
_SELECT_REVISION = """
    SELECT r.id, r.team_id, r.version, r.definition, r.created_at
      FROM team_revisions r
      JOIN teams t ON t.id = r.team_id
     WHERE r.team_id = $1 AND t.owner_principal = $2 AND r.version = $3
"""

# By id rather than by team and version: this is what a *run* names (`runs.team_revision_id`),
# and a viewer watching one has the run in hand and nothing else. Going through the version
# would mean asking the run's team which version this is — a question whose only honest
# answer is this row.
_SELECT_REVISION_BY_ID = """
    SELECT r.id, r.team_id, r.version, r.definition, r.created_at
      FROM team_revisions r
      JOIN teams t ON t.id = r.team_id
     WHERE r.id = $1 AND t.owner_principal = $2
"""

_SELECT_LATEST_REVISION = """
    SELECT r.id, r.team_id, r.version, r.definition, r.created_at
      FROM team_revisions r
      JOIN teams t ON t.id = r.team_id
     WHERE r.team_id = $1 AND t.owner_principal = $2
     ORDER BY r.version DESC
     LIMIT 1
"""

# `archived_at IS NULL` in the WHERE, not only in the stamp: retiring twice returns no
# row, so the route answers 404 the second time rather than quietly moving the timestamp.
# An UPDATE, never a DELETE — the runs and revisions hanging off this team are the result
# of the experiment this module exists to keep.
_ARCHIVE_TEAM = """
    UPDATE teams SET archived_at = now()
     WHERE id = $1 AND owner_principal = $2 AND archived_at IS NULL
    RETURNING id
"""


def _as_jsonb(definition: TeamDefinition) -> str:
    """`by_alias=True` is load-bearing: `TeamEdge.from_` is written `from` on the wire and
    MUST be written `from` in storage too, so that a revision read back parses through the
    same alias rather than through the populate-by-name fallback."""
    return json.dumps(definition.model_dump(mode="json", by_alias=True))


async def create_team(
    conn: Conn,
    *,
    owner_principal: str,
    name: str,
    description: str,
    definition: TeamDefinition,
) -> tuple[asyncpg.Record, asyncpg.Record]:
    """The team and its first revision, in one transaction. A team with no revision would
    be a catalogue entry that cannot be opened or run, and `TeamOut.latest_revision` has
    nowhere to get a value from — so the two rows are written together or not at all."""
    async with conn.transaction():
        team = await fetch_one(conn, _INSERT_TEAM, owner_principal, name, description)
        revision = await fetch_one(conn, _INSERT_REVISION, team["id"], 1, _as_jsonb(definition))
    return team, revision


async def save_revision(
    conn: Conn, *, team_id: int, owner_principal: str, definition: TeamDefinition
) -> asyncpg.Record | None:
    """The next revision of a team, or `None` for one that does not exist, belongs to
    somebody else, or was retired. Nothing about the previous revision is touched."""
    async with conn.transaction():
        locked = await conn.fetchrow(_LOCK_TEAM_FOR_WRITE, team_id, owner_principal)
        if locked is None:
            return None
        version = await fetch_one(conn, _NEXT_VERSION, team_id)
        revision = await fetch_one(
            conn, _INSERT_REVISION, team_id, version["version"], _as_jsonb(definition)
        )
        await conn.execute(_TOUCH_TEAM, team_id)
    return revision


async def get_team(conn: Conn, *, team_id: int, owner_principal: str) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT_TEAM, team_id, owner_principal)


async def list_teams(conn: Conn, *, owner_principal: str) -> list[asyncpg.Record]:
    return list(await conn.fetch(_SELECT_TEAMS_FOR_OWNER, owner_principal))


async def get_revision(
    conn: Conn, *, team_id: int, owner_principal: str, version: int
) -> asyncpg.Record | None:
    """A revision exactly as it was saved, including one of a team since retired — that is
    what makes an old run's trace mean anything (specs/teams-catalogue)."""
    return await conn.fetchrow(_SELECT_REVISION, team_id, owner_principal, version)


async def get_revision_by_id(
    conn: Conn, *, revision_id: int, owner_principal: str
) -> asyncpg.Record | None:
    """The revision a run points at, fetched the way the run names it."""
    return await conn.fetchrow(_SELECT_REVISION_BY_ID, revision_id, owner_principal)


async def get_latest_revision(
    conn: Conn, *, team_id: int, owner_principal: str
) -> asyncpg.Record | None:
    return await conn.fetchrow(_SELECT_LATEST_REVISION, team_id, owner_principal)


async def archive_team(conn: Conn, *, team_id: int, owner_principal: str) -> bool:
    """Retires a team from the catalogue. Its revisions and every run that pointed at
    them stay exactly where they were — see `_ARCHIVE_TEAM`."""
    row = await conn.fetchrow(_ARCHIVE_TEAM, team_id, owner_principal)
    return row is not None

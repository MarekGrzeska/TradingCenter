"""The catalogue: teams, their revisions, and retiring one. Every route hands `current_principal` to the
store, which puts the owner into the statement — a stranger's team answers 404, like one that never existed."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import store
from ..auth import current_principal
from ..contract import (
    CreateTeamIn,
    SaveLayoutIn,
    SaveRevisionIn,
    TeamDefinition,
    TeamLayoutOut,
    TeamOut,
    TeamRevisionOut,
)
from ..tools import announced_snapshot
from ..validation import DefinitionRefused, check_definition

log = logging.getLogger(__name__)

router = APIRouter()


async def _check(request: Request, definition: TeamDefinition) -> None:
    """The surroundings half of the save-time check. 422 rather than 400, so a refusal over an unknown
    model reads to the terminal exactly like one over a cycle.

    The tool names are asked of every configured server here rather than read from a list, so a server
    that reworded a tool is answered correctly without a restart. The models are the other way round: that
    catalogue is this module's own configuration, checked once at start-up."""
    try:
        check_definition(
            definition,
            model_ids=request.app.state.teams.catalogue.ids(),
            announced=await announced_snapshot(request.app.state.teams.settings),
        )
    except DefinitionRefused as err:
        raise HTTPException(422, detail=str(err)) from err


@router.post("/teams", status_code=201)
async def create_team(
    body: CreateTeamIn, request: Request, owner: str = Depends(current_principal)
) -> TeamOut:
    await _check(request, body.definition)
    async with request.app.state.teams.pool.acquire() as conn:
        team, revision = await store.create_team(
            conn,
            owner_principal=owner,
            name=body.name,
            description=body.description,
            definition=body.definition,
        )
    return TeamOut.from_row({**dict(team), "latest_revision": revision["version"]})


@router.get("/teams")
async def list_teams(request: Request, owner: str = Depends(current_principal)) -> list[TeamOut]:
    """The whole of what a picker needs, and no definition — see `store.catalogue._LATEST_REVISION`."""
    async with request.app.state.teams.pool.acquire() as conn:
        rows = await store.list_teams(conn, owner_principal=owner)
    # `dict(row)`, here and below: asyncpg's Record forwards mapping access at
    # runtime but is not a Mapping to a type checker, and `from_row` takes one.
    return [TeamOut.from_row(dict(row)) for row in rows]


@router.get("/teams/{team_id}")
async def get_team(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> TeamOut:
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_team(conn, team_id=team_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such team")
    return TeamOut.from_row(dict(row))


@router.post("/teams/{team_id}/revisions", status_code=201)
async def save_revision(
    team_id: int,
    body: SaveRevisionIn,
    request: Request,
    owner: str = Depends(current_principal),
) -> TeamRevisionOut:
    """Appends. The previous revision is not read, not touched and not made obsolete —
    a run already pointing at it keeps meaning what it meant."""
    await _check(request, body.definition)
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.save_revision(
            conn, team_id=team_id, owner_principal=owner, definition=body.definition
        )
    if row is None:
        raise HTTPException(404, detail="no such team")
    return TeamRevisionOut.from_row(dict(row))


@router.get("/teams/{team_id}/revisions/latest")
async def get_latest_revision(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> TeamRevisionOut:
    """What the canvas opens on. Declared before the `{version}` route below, or FastAPI
    would try to parse "latest" as an int and answer 422."""
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_latest_revision(conn, team_id=team_id, owner_principal=owner)
    if row is None:
        raise HTTPException(404, detail="no such team")
    return TeamRevisionOut.from_row(dict(row))


@router.get("/teams/{team_id}/revisions/{version}")
async def get_revision(
    team_id: int, version: int, request: Request, owner: str = Depends(current_principal)
) -> TeamRevisionOut:
    """Including a revision of a retired team: a run points at a revision, and a trace
    that cannot be opened is not a trace (specs/teams-catalogue)."""
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_revision(
            conn, team_id=team_id, owner_principal=owner, version=version
        )
    if row is None:
        raise HTTPException(404, detail="no such revision")
    return TeamRevisionOut.from_row(dict(row))


@router.get("/revisions/{revision_id}")
async def get_revision_by_id(
    revision_id: int, request: Request, owner: str = Depends(current_principal)
) -> TeamRevisionOut:
    """The definition a run is working on, reached the way a run names it — by id rather than by a version
    the watcher would first have to look up. The team's latest would show a graph the run is not running."""
    async with request.app.state.teams.pool.acquire() as conn:
        row = await store.get_revision_by_id(
            conn, revision_id=revision_id, owner_principal=owner
        )
    if row is None:
        raise HTTPException(404, detail="no such revision")
    return TeamRevisionOut.from_row(dict(row))


@router.get("/teams/{team_id}/layout")
async def get_layout(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> TeamLayoutOut:
    """Where the operator left each agent. A team with nothing saved answers with an empty layout rather
    than a 404: never having been arranged is the ordinary state."""
    async with request.app.state.teams.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows = await store.get_layout(conn, team_id=team_id, owner_principal=owner)
    return TeamLayoutOut.from_rows(dict(row) for row in rows)


@router.put("/teams/{team_id}/layout")
async def save_layout(
    team_id: int,
    body: SaveLayoutIn,
    request: Request,
    owner: str = Depends(current_principal),
) -> TeamLayoutOut:
    """Replaces the layout. Not a revision and not a change to one, which is the whole reason the table it
    writes exists. Agent keys are not checked against any revision: the canvas sends what it drew."""
    async with request.app.state.teams.pool.acquire() as conn:
        saved = await store.save_layout(
            conn,
            team_id=team_id,
            owner_principal=owner,
            places=[(place.agent_key, place.x, place.y) for place in body.places],
        )
    if not saved:
        raise HTTPException(404, detail="no such team")
    return TeamLayoutOut(places=body.places)


@router.delete("/teams/{team_id}", status_code=204)
async def archive_team(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> None:
    """Retires the team from the catalogue. Its runs and the revisions they name stay —
    see `store.catalogue._ARCHIVE_TEAM`."""
    async with request.app.state.teams.pool.acquire() as conn:
        retired = await store.archive_team(conn, team_id=team_id, owner_principal=owner)
    if not retired:
        raise HTTPException(404, detail="no such team")

"""What a team remembers, for the operator who owns it. Two routes and no third: an entry is written by an
agent deciding to write it and is never changed, so the operator's part is seeing and removing.

The read is capped at the same ceiling the tool reads under and carries the total: showing the operator
less than there is without saying so is the same fault as handing a model a truncated memory."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import store
from ..auth import current_principal
from ..contract import MEMORY_READ_LIMIT, TeamMemoryOut

router = APIRouter()


@router.get("/teams/{team_id}/memory")
async def get_memory(
    team_id: int, request: Request, owner: str = Depends(current_principal)
) -> TeamMemoryOut:
    """A team that has remembered nothing answers with an empty memory rather than a 404 — and for a team
    whose agents carry no memory tools that is the only state there is."""
    async with request.app.state.teams.pool.acquire() as conn:
        team = await store.get_team(conn, team_id=team_id, owner_principal=owner)
        if team is None:
            raise HTTPException(404, detail="no such team")
        rows, total = await store.list_memories(
            conn, team_id=team_id, owner_principal=owner, limit=MEMORY_READ_LIMIT
        )
    return TeamMemoryOut.from_rows((dict(row) for row in rows), total=total)


@router.delete("/teams/{team_id}/memory/{entry_id}", status_code=204)
async def delete_memory(
    team_id: int,
    entry_id: int,
    request: Request,
    owner: str = Depends(current_principal),
) -> None:
    """Removes one entry, so it stops reaching later runs. The runs that read or wrote it keep their trace:
    deleting the note does not make it untrue that the run had it."""
    async with request.app.state.teams.pool.acquire() as conn:
        deleted = await store.delete_memory(
            conn, entry_id=entry_id, team_id=team_id, owner_principal=owner
        )
    if not deleted:
        raise HTTPException(404, detail="no such memory entry")

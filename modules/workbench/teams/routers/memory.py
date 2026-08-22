"""What a team remembers, for the operator who owns it.

Two routes and no third: read the entries, delete one. There is deliberately no route
that writes and none that edits — an entry is written by an agent deciding to write it
(`tools/memory.py`) and is never changed afterwards, so the operator's part is seeing what
their team has learned and removing what it got wrong (specs/teams-memory, "Pamięć jest
widoczna dla operatora i usuwana wyłącznie przez niego").

The read is capped at the same ceiling the tool reads under, and carries the total, so a
panel showing twenty of ninety entries can say so. Showing the operator less than there is
without saying so is the same fault as handing a model a truncated memory.
"""

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
    """A team that has remembered nothing answers with an empty memory rather than a 404 —
    never having written a note is the ordinary state, and for a team whose agents carry no
    memory tools it is the only one."""
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
    """Removes one entry, so it stops reaching later runs. The runs that read or wrote it
    keep their trace: what a team was told at the time is part of how that run came out,
    and deleting the note does not make it untrue that the run had it."""
    async with request.app.state.teams.pool.acquire() as conn:
        deleted = await store.delete_memory(
            conn, entry_id=entry_id, team_id=team_id, owner_principal=owner
        )
    if not deleted:
        raise HTTPException(404, detail="no such memory entry")
